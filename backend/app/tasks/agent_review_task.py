"""由 AI Agent 执行 PR Code Review 的 Celery task。

worker 读取 Review 与 Installation，拉取 PR 上下文并创建 Sandbox，随后由 ReviewAgent
通过只读 Tool、验证 Tool 和发布 Tool 完成审查，最后回写 Review 状态并释放 Sandbox。
"""

import asyncio
import logging

from sqlalchemy import and_, select

from app.agents.implementation.review_agent import ReviewAgent
from app.agents.loop import AgentLoop
from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.manager import get_reviewer_tools
from app.core.celery_app import BaseTask, celery_app
from app.core.client import get_llm_client
from app.db.base import AsyncSessionLocal, engine
from app.models.installation import Installation
from app.models.review import Review
from app.repositories.review import ReviewRepository
from app.services.github import GitHubService

logger = logging.getLogger(__name__)
INT32_MAX = 2_147_483_647


def _to_int32_or_none(value: object) -> int | None:
    """在可行时把数值转换为 int32。"""
    if value is None:
        return None
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= int_value <= INT32_MAX:
        return int_value
    return None


@celery_app.task(bind=True, base=BaseTask, time_limit=3600)
def process_pr_review_with_agent(
    self,
    review_id: str,
    installation_id: int,
    repository: str,
    pr_number: int,
):
    """Celery 同步入口：使用 AI Agent 处理 PR Review。

    Args:
        self: Celery Task 实例
        review_id: Review UUID
        installation_id: GitHub Installation ID
        repository: Repository 全名（owner/repo）
        pr_number: PR 编号
    """
    return asyncio.run(
        _process_pr_review_with_agent_async(self, review_id, installation_id, repository, pr_number)
    )


async def _process_pr_review_with_agent_async(
    task_self,
    review_id: str,
    installation_id: int,
    repository: str,
    pr_number: int,
):
    """Agent 驱动 PR Review 的异步编排实现。

    Args:
        task_self: Celery Task 实例
        review_id: Review UUID
        installation_id: GitHub Installation ID
        repository: Repository 全名（owner/repo）
        pr_number: PR 编号
    """
    sandbox = None
    sandbox_manager = None
    review = None

    async with AsyncSessionLocal() as db:
        review_repo = ReviewRepository()
        github = GitHubService()

        try:
            # 1. 读取 Review 与 Installation，建立本次审查的数据库上下文。
            logger.info(f"Loading review {review_id}")

            review_query = await db.execute(select(Review).where(Review.id == review_id))
            review = review_query.scalar_one_or_none()

            if not review:
                logger.warning(f"Review {review_id} not found; skipping task without retry")
                return {
                    "status": "ignored",
                    "reason": "review_not_found",
                    "review_id": review_id,
                }

            installation_query = await db.execute(
                select(Installation).where(
                    and_(
                        Installation.github_installation_id == installation_id,
                        Installation.repository == repository,
                    )
                )
            )
            installation = installation_query.scalar_one_or_none()

            if not installation:
                review.status = "FAILED"
                review.error = f"Installation not found for {repository}"
                await db.commit()
                return {
                    "status": "failed",
                    "reason": "installation_not_found",
                    "review_id": review_id,
                }

            # 先提交 PROCESSING，使前端轮询能看到 worker 已开始执行。
            review.status = "PROCESSING"
            await db.commit()

            # 2. 从 GitHub 获取 PR diff，并读取 webhook 阶段保存的元数据。
            logger.info(f"Fetching PR #{pr_number} diff from {repository}")

            owner, repo = repository.split("/")
            diff = await github.get_pr_diff(owner, repo, pr_number, installation_id)

            # Branch 与语言来自 webhook 保存的 PR metadata。
            head_branch = review.pr_metadata.get("head_branch", "main")
            base_branch = review.pr_metadata.get("base_branch", "main")
            pr_language = review.pr_metadata.get("language", "Python")

            logger.info(f"PR: {head_branch} → {base_branch}, language: {pr_language}")

            # 3. 获取 GitHub Installation token，供 Sandbox clone 和发布评论认证。
            logger.info("Getting installation token for git authentication")
            installation_token = await github.get_installation_token(installation_id)

            # 4. 加载用户配置的敏感度、自定义指令和忽略模式。
            config_dict = installation.config or {}
            sensitivity = config_dict.get("sensitivity", "MEDIUM")
            custom_instructions = config_dict.get("custom_instructions", "")
            ignore_patterns = config_dict.get("ignore_patterns", [])

            logger.info(
                f"Review config: sensitivity={sensitivity}, ignore_patterns={ignore_patterns}"
            )

            # 5. 初始化 Daytona SandboxManager。
            logger.info("Creating Daytona sandbox")

            sandbox_manager = SandboxManager(
                git_username="x-access-token", git_token=installation_token
            )

            # Sandbox 创建时直接 clone PR Branch，确保 Review 针对待审代码。
            repo_url = f"https://github.com/{repository}.git"

            # 根据 Repository 主语言选择 Sandbox Runtime，默认使用 Python。
            sandbox_language = "python"  # 默认值。
            if pr_language:
            # 将 GitHub 语言名映射到 Daytona Runtime 标识。
                language_map = {
                    "Python": "python",
                    "TypeScript": "typescript",
                    "JavaScript": "javascript",
                }
                sandbox_language = language_map.get(pr_language, "python")

            logger.info(f"Creating sandbox with language: {sandbox_language}")

            sandbox = sandbox_manager.acquire(
                agent_id=review_id,
                repository_url=repo_url,
                branch=head_branch,  # 直接 clone PR Branch，确保是待审版本。
                language=sandbox_language,
            )

            logger.info(f"Sandbox created: {sandbox.id}")

            # 6. 组装 Review Agent 的只读、验证、发布与完成 Tool。
            tools = get_reviewer_tools(
                sandbox=sandbox,
                review_id=review_id,
                installation_token=installation_token,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                commit_sha=review.commit_sha,
            )

            logger.info(f"Registered {len(tools.list_tool_names())} tools for reviewer")

            # 7. 初始化 LLM 客户端。
            llm_client = get_llm_client()

            # 8. 用 PR 上下文和 Review 配置创建 ReviewAgent。
            logger.info("Creating ReviewAgent")

            agent = ReviewAgent(
                agent_id=review_id,
                pr_title=review.pr_metadata.get("title", ""),
                pr_description=review.pr_metadata.get("description", ""),
                pr_diff=diff,
                sensitivity=sensitivity,
                custom_instructions=custom_instructions,
                ignore_patterns=ignore_patterns,
                tools=tools,
                llm_client=llm_client,
                max_iterations=50,
                max_tokens=1_000_000,
                max_tool_calls=100,
                max_duration_seconds=6000,
            )

            # 9. 运行 AgentLoop，直到 finish_review、失败或达到资源上限。
            logger.info("Starting agent loop")

            loop = AgentLoop(agent)
            final_state = await loop.execute()

            logger.info(
                f"Agent finished: status={final_state.status}, "
                f"iterations={final_state.iteration}, "
                f"tokens={final_state.tokens_used}"
            )

            # 10. 从 Completion Tool 的结果提取最终 summary 与 verdict。
            if final_state.status == "completed" and final_state.result:
                summary = final_state.result.get("summary")
                verdict = final_state.result.get("verdict", "COMMENT")
                overall_severity = final_state.result.get("overall_severity", "medium")

                if not summary:
                    reason = final_state.result.get("reason") or "missing_summary"
                    review.status = "FAILED"
                    review.error = f"Agent completed without finish_review output (reason={reason})"
                    await db.commit()
                    logger.error(review.error)
                    return {
                        "status": "failed",
                        "reason": "missing_summary",
                        "review_id": review_id,
                    }

                logger.info(
                    f"Review summary generated: {len(summary)} chars, verdict={verdict}, severity={overall_severity}"
                )

            # 11. 将最终汇总 Review 发布到 GitHub。
                logger.info("Posting review to GitHub")

                gh_review = await github.create_pr_review(
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    review_body=summary,
                    event=verdict,
                    installation_id=installation_id,
                )

            # 12. 回写 Review 完成状态和 Agent 执行指标。
                review.status = "COMPLETED"
                review.review_text = summary
                review.github_review_id = _to_int32_or_none(gh_review.get("id"))
                review.pr_metadata = {
                    **(review.pr_metadata or {}),
                    "overall_severity": overall_severity,
                    "verdict": verdict,
                    "github_review_id_raw": gh_review.get("id"),
                    "iterations": final_state.iteration,
                    "tokens_used": final_state.tokens_used,
                    "tool_calls": final_state.tool_calls_made,
                }
                await db.commit()

                logger.info(f"Review {review_id} completed successfully")

            else:
            # Agent 未正常完成或触发资源上限时进入失败分支。
                error_msg = final_state.error or "Agent did not complete review"
                logger.error(f"Agent failed: {error_msg}")

                review.status = "FAILED"
                review.error = error_msg
                await db.commit()

        except Exception as e:
            logger.error(f"Review task failed: {e}", exc_info=True)
            await db.rollback()

            # 尽量把异常状态持久化，避免 Review 长期停留在 PROCESSING。
            if review:
                review.status = "FAILED"
                review.error = str(e)
                await db.commit()

            raise

        finally:
            # finally 始终释放远程 Sandbox，避免资源泄漏。
            if sandbox_manager and review_id:
                try:
                    logger.info(f"Cleaning up sandbox for {review_id}")
                    sandbox_manager.release(review_id)
                except Exception as e:
                    logger.error(f"Sandbox cleanup failed: {e}")
            # Celery 重试可能在同一 worker 进程的新 event loop 中运行；释放连接池可避免
            # 跨 event loop 复用异步数据库连接。
            try:
                await engine.dispose()
            except Exception as e:
                logger.error(f"Engine dispose failed: {e}")
