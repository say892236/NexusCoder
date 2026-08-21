"""Issue -> AgentRun -> Celery -> Sandbox -> AgentLoop -> Tool -> PR 主任务。

这是学习 Metis 后台 Coding Agent 的首要入口。Celery worker 根据 AgentRun 恢复上下文，
创建并配置 Sandbox，组装 Tool 与 AgentLoop；Agent 在循环中修改代码、Commit、Push，
编排层确认远端 Branch 存在后创建 PR，最后把完整轨迹和结果写回 AgentRun。
"""

import asyncio
import logging
import shlex
from datetime import datetime, timezone

from sqlalchemy import and_, select

from app.agents.implementation.background_agent import BackgroundAgent
from app.agents.loop import AgentLoop
from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.manager import get_coder_tools
from app.core.celery_app import BaseTask, celery_app
from app.core.client import get_llm_client
from app.db.base import AsyncSessionLocal, engine
from app.models.agent_run import AgentRun
from app.models.installation import Installation
from app.services.github import GitHubService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_changed_files_from_diff_output(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def _build_pr_payload(issue_number: int, issue_title: str, summary: str) -> tuple[str, str]:
    """根据 Issue 上下文与 Agent 总结构造 PR 标题和正文。"""
    title = f"Fix: issue #{issue_number} - {issue_title}".strip()
    body = f"## Summary\n\n{summary.strip()}\n\n---\nCloses #{issue_number}"
    return title, body


@celery_app.task(bind=True, base=BaseTask, time_limit=7200)
def process_issue_with_agent(
    self,
    agent_run_id: str,
):
    """Celery 的同步入口：为指定 AgentRun 启动异步 Issue -> PR 流程。"""
    return asyncio.run(_process_issue_with_agent_async(self, agent_run_id))


async def _process_issue_with_agent_async(
    task_self,
    agent_run_id: str,
):
    """编排一次完整的异步 Issue -> PR 执行。"""
    sandbox = None
    sandbox_manager = None
    agent_run = None
    agent = None

    async with AsyncSessionLocal() as db:
        github = GitHubService()

        try:
            # 1) 读取 AgentRun 与 Installation，确认任务仍有有效的执行上下文。
            run_query = await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))
            agent_run = run_query.scalar_one_or_none()
            if not agent_run:
                logger.warning("AgentRun %s not found", agent_run_id)
                return {
                    "status": "ignored",
                    "reason": "agent_run_not_found",
                    "agent_run_id": agent_run_id,
                }

            installation_query = await db.execute(
                select(Installation).where(
                    and_(
                        Installation.id == agent_run.installation_id,
                        Installation.repository == agent_run.repository,
                        Installation.is_active == True,  # noqa: E712；SQLAlchemy 表达式
                    )
                )
            )
            installation = installation_query.scalar_one_or_none()
            if not installation:
                agent_run.status = "FAILED"
                agent_run.error = "installation_not_found_or_inactive"
                agent_run.completed_at = _utcnow()
                await db.commit()
                return {
                    "status": "failed",
                    "reason": "installation_not_found_or_inactive",
                }

            started_at = _utcnow()
            agent_run.status = "RUNNING"
            agent_run.started_at = started_at
            agent_run.error = None
            # Celery 重试或人工重跑时，先清理上一次遗留的完成字段。
            agent_run.completed_at = None
            agent_run.elapsed_seconds = None
            agent_run.pr_number = None
            agent_run.pr_url = None
            agent_run.branch_name = None
            agent_run.final_summary = None
            agent_run.celery_task_id = agent_run.celery_task_id or task_self.request.id
            await db.commit()

            owner, repo = agent_run.repository.split("/")

            # 2) 从 GitHub 拉取最新 Issue 与 Repository 元数据，并刷新 AgentRun 快照。
            issue_data = await github.get_issue(
                owner=owner,
                repo=repo,
                issue_number=agent_run.issue_number,
                installation_id=installation.github_installation_id,
            )
            repo_data = await github.get_repository(
                owner=owner,
                repo=repo,
                installation_id=installation.github_installation_id,
            )

            issue_title = issue_data.get("title") or (agent_run.issue_title_snapshot or "").strip()
            issue_body = issue_data.get("body") or (agent_run.issue_body_snapshot or "")
            issue_url = issue_data.get("html_url")
            base_branch = repo_data.get("default_branch") or "main"
            repo_language = repo_data.get("language") or "Unknown"

            agent_run.issue_title_snapshot = issue_title
            agent_run.issue_body_snapshot = issue_body
            agent_run.issue_url = issue_url
            await db.commit()

            # 3) 获取短期 installation token，创建 Sandbox，再装配 Coding Agent 的 Tool 集合。
            installation_token = await github.get_installation_token(
                installation.github_installation_id
            )
            language_map = {
                "Python": "python",
                "TypeScript": "typescript",
                "JavaScript": "javascript",
            }
            sandbox_language = language_map.get(repo_language, "python")

            sandbox_manager = SandboxManager(
                git_username="x-access-token",
                git_token=installation_token,
            )
            sandbox = sandbox_manager.acquire(
                agent_id=f"{agent_run_id}:coder",
                repository_url=f"https://github.com/{agent_run.repository}.git",
                branch=base_branch,
                language=sandbox_language,
            )

            # 只在编排层初始化一次 Git 身份与认证；Agent 后续只需 add/commit/push。
            push_url = (
                f"https://x-access-token:{installation_token}@github.com/{agent_run.repository}.git"
            )
            bootstrap_cmd = (
                f"git config user.name {shlex.quote('Metis AI')} && "
                f"git config user.email {shlex.quote('ai@metis.dev')} && "
                f"git remote set-url origin {shlex.quote(push_url)}"
            )
            bootstrap_response = sandbox.process.exec(
                command=bootstrap_cmd,
                cwd="workspace/repo",
                timeout=60,
            )
            if bootstrap_response.exit_code != 0:
                agent_run.status = "FAILED"
                agent_run.error = (
                    "failed_git_bootstrap: "
                    f"exit_code={bootstrap_response.exit_code}, "
                    f"output={(bootstrap_response.result or '').strip()[:500]}"
                )
                agent_run.completed_at = _utcnow()
                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )
                await db.commit()
                return {
                    "status": "failed",
                    "reason": "failed_git_bootstrap",
                    "agent_run_id": str(agent_run.id),
                }

            tools = get_coder_tools(sandbox=sandbox)
            llm_client = get_llm_client()

            # 4) 进入 AgentLoop：每轮由 LLM 决定 Tool Calling，直到 finish_task 或资源上限。
            agent = BackgroundAgent(
                agent_id=str(agent_run.id),
                repository=agent_run.repository,
                issue_number=agent_run.issue_number,
                issue_title=issue_title,
                issue_body=issue_body,
                custom_instructions=agent_run.custom_instructions or "",
                tools=tools,
                llm_client=llm_client,
                max_iterations=1000,
                max_tokens=10_000_000,
                max_tool_calls=500,
                max_duration_seconds=7200,
            )
            final_state = await AgentLoop(agent).execute()

            # 无论成功失败都保存 Prompt、对话、token 与 Tool 统计，便于复盘执行过程。
            agent_run.system_prompt = agent.system_prompt
            agent_run.initial_user_message = agent.initial_user_message
            agent_run.conversation = final_state.messages
            agent_run.final_result = final_state.result or {}
            agent_run.iteration = final_state.iteration
            agent_run.tokens_used = final_state.tokens_used
            agent_run.tool_calls_made = final_state.tool_calls_made

            if final_state.status != "completed" or not final_state.result:
                agent_run.status = "FAILED"
                agent_run.error = final_state.error or "agent_not_completed"
                agent_run.completed_at = _utcnow()
                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )
                await db.commit()
                return {
                    "status": "failed",
                    "reason": agent_run.error,
                    "agent_run_id": str(agent_run.id),
                }

            summary = (final_state.result.get("summary") or "").strip()
            branch_name = (final_state.result.get("branch_name") or "").strip()
            if not summary:
                summary = f"Implemented issue #{agent_run.issue_number} via background agent."
            if not branch_name:
                agent_run.status = "FAILED"
                agent_run.error = "missing_branch_name"
                agent_run.completed_at = _utcnow()
                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )
                await db.commit()
                return {
                    "status": "failed",
                    "reason": "missing_branch_name",
                    "agent_run_id": str(agent_run.id),
                }

            # 5) 创建 PR 前验证 Agent 已把 Branch 推到 origin，避免生成无效 PR。
            branch_check_response = sandbox.process.exec(
                command=f"git ls-remote --heads origin {shlex.quote(branch_name)}",
                cwd="workspace/repo",
                timeout=30,
            )
            if (
                branch_check_response.exit_code != 0
                or not (branch_check_response.result or "").strip()
            ):
                agent_run.status = "FAILED"
                agent_run.error = (
                    "branch_not_pushed_to_origin: "
                    f"branch={branch_name}, "
                    f"exit_code={branch_check_response.exit_code}, "
                    f"output={(branch_check_response.result or '').strip()[:500]}"
                )
                agent_run.completed_at = _utcnow()
                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )
                await db.commit()
                return {
                    "status": "failed",
                    "reason": "branch_not_pushed_to_origin",
                    "agent_run_id": str(agent_run.id),
                }

            # 6) 优先从最新 Commit 的 diff 汇总变更文件。
            changed_files: list[str] = []
            try:
                diff_response = sandbox.process.exec(
                    command="git diff --name-only HEAD~1..HEAD",
                    cwd="workspace/repo",
                    timeout=30,
                )
                if diff_response.exit_code == 0:
                    changed_files = _extract_changed_files_from_diff_output(
                        diff_response.result or ""
                    )
            except Exception:
                changed_files = []

            # 若无法取得 Commit diff，则退回 Sandbox 当前 Git 状态。
            if not changed_files:
                try:
                    status = sandbox.git.status("workspace/repo")
                    changed_files = [f.name for f in status.file_status]
                except Exception:
                    changed_files = []

            # 7) PR 是编排层的外部副作用，不由 LLM 直接调用 GitHub API 创建。
            pr_title, pr_body = _build_pr_payload(
                issue_number=agent_run.issue_number,
                issue_title=issue_title,
                summary=summary,
            )
            pr_data = await github.create_pull_request(
                owner=owner,
                repo=repo,
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base=base_branch,
                installation_id=installation.github_installation_id,
            )

            # 8) 将 Branch、PR、耗时和变更文件写回 AgentRun，闭合整条执行链。
            completed_at = _utcnow()
            agent_run.status = "COMPLETED"
            agent_run.completed_at = completed_at
            agent_run.elapsed_seconds = int(
                (completed_at - (agent_run.started_at or started_at)).total_seconds()
            )
            agent_run.branch_name = branch_name
            agent_run.final_summary = summary
            agent_run.pr_number = pr_data.get("number")
            agent_run.pr_url = pr_data.get("html_url")
            agent_run.changed_files = changed_files
            await db.commit()

            return {
                "status": "success",
                "agent_run_id": str(agent_run.id),
                "pr_number": agent_run.pr_number,
                "pr_url": agent_run.pr_url,
            }

        except Exception as e:
            logger.error(
                "Background agent task failed run=%s: %s",
                agent_run_id,
                e,
                exc_info=True,
            )
            await db.rollback()
            if agent_run:
                await db.refresh(agent_run)
                agent_run.status = "FAILED"
                agent_run.error = str(e)
                agent_run.completed_at = _utcnow()
                if agent and agent.state:
                    agent_run.system_prompt = agent.system_prompt
                    agent_run.initial_user_message = agent.initial_user_message
                    agent_run.conversation = agent.state.messages
                    agent_run.final_result = agent.state.result or {}
                    agent_run.iteration = agent.state.iteration
                    agent_run.tokens_used = agent.state.tokens_used
                    agent_run.tool_calls_made = agent.state.tool_calls_made
                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )
                await db.commit()
            raise
        finally:
            if sandbox_manager:
                try:
                    sandbox_manager.release(f"{agent_run_id}:coder")
                except Exception as cleanup_err:
                    logger.error("Background sandbox cleanup failed: %s", cleanup_err)
            try:
                await engine.dispose()
            except Exception as dispose_err:
                logger.error("Engine dispose failed: %s", dispose_err)
