"""Issue -> AgentRun -> Celery -> Sandbox -> Multi-Agent Graph -> PR 主任务。

这是 NexusCoder 后台 Coding Agent 的首要入口。

Celery worker 根据 AgentRun 恢复上下文，创建并配置 Sandbox，
然后进入 Multi-Agent Graph：

Supervisor -> Coder -> Tester -> Reviewer

Graph 完成后，外层编排继续确认远端 Branch、创建 PR，
最后把结果写回 AgentRun，并在 finally 中释放 Sandbox。
"""

import asyncio
import logging
import selectors
import shlex
import sys
from datetime import datetime, timezone

from sqlalchemy import and_, select

from app.agents.memory.service import (
    recall_memories,
    remember_successful_run,
)
from app.agents.multi_agent.runner import (
    resume_multi_agent_graph,
    run_multi_agent_graph,
)
from app.agents.sandbox.manager import SandboxManager
from app.core.celery_app import BaseTask, celery_app
from app.core.client import get_llm_client
from app.db.base import AsyncSessionLocal, engine
from app.models.agent_run import AgentRun
from app.models.installation import Installation
from app.services.github import GitHubService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """返回 UTC 时间。"""
    return datetime.now(timezone.utc)


def _extract_changed_files_from_diff_output(
    output: str,
) -> list[str]:
    """从 git diff --name-only 输出中提取文件名。"""
    return [line.strip() for line in output.splitlines() if line.strip()]


def _build_pr_payload(
    issue_number: int,
    issue_title: str,
    summary: str,
) -> tuple[str, str]:
    """根据 Issue 上下文与 Agent 总结构造 PR 标题和正文。"""

    title = (f"Fix: issue #{issue_number} - {issue_title}").strip()

    body = f"## Summary\n\n{summary.strip()}\n\n---\nCloses #{issue_number}"

    return title, body


_worker_loop: asyncio.AbstractEventLoop | None = None


def _run_async(coro):
    """Windows Celery solo worker 复用同一个 EventLoop。"""

    global _worker_loop  # noqa: PLW0603

    if sys.platform == "win32":
        if _worker_loop is None or _worker_loop.is_closed():
            _worker_loop = asyncio.SelectorEventLoop(
                selectors.SelectSelector()
            )

        asyncio.set_event_loop(_worker_loop)

        return _worker_loop.run_until_complete(coro)

    return asyncio.run(coro)


@celery_app.task(bind=True, base=BaseTask, time_limit=7200)
def process_issue_with_agent(
    self,
    agent_run_id: str,
):
    return _run_async(
        _process_issue_with_agent_async(
            self,
            agent_run_id,
        )
    )


async def _process_issue_with_agent_async(
    task_self,
    agent_run_id: str,
):
    """编排一次完整的异步 Issue -> PR 执行。"""

    sandbox = None
    sandbox_manager = None
    agent_run = None

    # 保存 Multi-Agent Graph 的最终状态。
    # 如果 Graph 后面的 Branch / PR 阶段失败，
    # except 中仍然可以把 Agent 执行轨迹写入数据库。
    graph_result = None

    async with AsyncSessionLocal() as db:
        github = GitHubService()

        try:
            # =========================================================
            # 1. 读取 AgentRun / Installation
            # =========================================================

            run_query = await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))

            agent_run = run_query.scalar_one_or_none()

            if not agent_run:
                logger.warning(
                    "AgentRun %s not found",
                    agent_run_id,
                )

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
                        Installation.is_active == True,  # noqa: E712
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
                    "reason": ("installation_not_found_or_inactive"),
                }

            # =========================================================
            # 2. AgentRun -> RUNNING
            # =========================================================

            started_at = _utcnow()

            agent_run.status = "RUNNING"
            agent_run.started_at = started_at
            agent_run.error = None

            # Celery 重试或人工重跑时，
            # 清理上一次任务结果。
            agent_run.completed_at = None
            agent_run.elapsed_seconds = None
            agent_run.pr_number = None
            agent_run.pr_url = None
            agent_run.branch_name = None
            agent_run.final_summary = None

            agent_run.celery_task_id = agent_run.celery_task_id or task_self.request.id

            await db.commit()

            owner, repo = agent_run.repository.split("/")

            # =========================================================
            # 3. 获取 GitHub Issue / Repository
            # =========================================================

            issue_data = await github.get_issue(
                owner=owner,
                repo=repo,
                issue_number=agent_run.issue_number,
                installation_id=(installation.github_installation_id),
            )

            repo_data = await github.get_repository(
                owner=owner,
                repo=repo,
                installation_id=(installation.github_installation_id),
            )

            issue_title = issue_data.get("title") or (agent_run.issue_title_snapshot or "").strip()

            issue_body = issue_data.get("body") or (agent_run.issue_body_snapshot or "")

            issue_url = issue_data.get("html_url")

            base_branch = repo_data.get("default_branch") or "main"

            repo_language = repo_data.get("language") or "Unknown"

            # 刷新 AgentRun 中保存的 Issue 快照。
            agent_run.issue_title_snapshot = issue_title

            agent_run.issue_body_snapshot = issue_body

            agent_run.issue_url = issue_url

            await db.commit()

            # =========================================================
            # 4. 创建 Daytona Sandbox
            # =========================================================

            installation_token = await github.get_installation_token(
                installation.github_installation_id
            )

            language_map = {
                "Python": "python",
                "TypeScript": "typescript",
                "JavaScript": "javascript",
            }

            sandbox_language = language_map.get(
                repo_language,
                "python",
            )

            sandbox_manager = SandboxManager(
                git_username="x-access-token",
                git_token=installation_token,
            )

            sandbox = sandbox_manager.acquire(
                agent_id=f"{agent_run_id}:coder",
                repository_url=(f"https://github.com/{agent_run.repository}.git"),
                branch=base_branch,
                language=sandbox_language,
            )

            # =========================================================
            # 5. 初始化 Git 身份 / Push 凭据
            # =========================================================

            push_url = (
                f"https://x-access-token:{installation_token}@github.com/{agent_run.repository}.git"
            )

            bootstrap_cmd = (
                f"git config user.name "
                f"{shlex.quote('NexusCoder')} && "
                f"git config user.email "
                f"{shlex.quote('ai@metis.dev')} && "
                f"git remote set-url origin "
                f"{shlex.quote(push_url)}"
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
                    f"exit_code="
                    f"{bootstrap_response.exit_code}, "
                    f"output="
                    f"{(bootstrap_response.result or '').strip()[:500]}"
                )

                agent_run.completed_at = _utcnow()

                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )

                await db.commit()

                return {
                    "status": "failed",
                    "reason": ("failed_git_bootstrap"),
                    "agent_run_id": str(agent_run.id),
                }

            # =========================================================
            # 6. 执行 Multi-Agent Graph
            # =========================================================
            #
            # 以前这里是：
            #
            # BackgroundAgent
            #       ↓
            # AgentLoop
            #
            # 现在升级成：
            #
            # Supervisor
            #       ↓
            # Coder
            #       ↓
            # Tester
            #       ↓
            # Reviewer
            #
            # Sandbox 由当前 Celery Task 创建，
            # 所以 Graph 只是使用。
            #
            # 最终真正的 release 仍由下面 finally 负责。
            # =========================================================

            llm_client = get_llm_client()

            # ---------------------------------------------------------
            # Memory Recall
            # 在新 Coding 任务开始前，读取当前 Repository 的历史经验。
            # ---------------------------------------------------------

            memory_query = f"{issue_title}\n{issue_body}"

            memories = await recall_memories(
                db,
                repository=agent_run.repository,
                query_text=memory_query,
                limit=5,
                langsmith_extra={
                    "metadata": {
                        "thread_id": str(agent_run.id),
                        "issue_number": agent_run.issue_number,
                        "repository": agent_run.repository,
                    },
                    "tags": [
                        "memory",
                        "recall",
                    ],
                },
            )

            recalled_memories = [
                {
                    "memory_type": memory.memory_type,
                    "memory_key": memory.memory_key,
                    "summary": memory.summary,
                    "content": memory.content,
                    "importance": memory.importance,
                }
                for memory in memories
            ]

            logger.info(
                "Recalled %s memories for repository=%s",
                len(recalled_memories),
                agent_run.repository,
            )

            graph_result = await run_multi_agent_graph(
                # AgentRun ID 同时作为 LangGraph thread_id。
                thread_id=str(agent_run.id),
                repository=agent_run.repository,
                issue_number=agent_run.issue_number,
                issue_title=issue_title,
                issue_body=issue_body,
                custom_instructions=(agent_run.custom_instructions or ""),
                base_branch=base_branch,
                sandbox=sandbox,
                llm_client=llm_client,
                recalled_memories=recalled_memories,
                # 正式启用 HITL。
                require_human_approval=True,
            )
            # =========================================================
            # HITL：Graph 暂停等待人工审批
            # =========================================================

            if graph_result.get("__interrupt__"):
                coder_trace = graph_result.get("coder_trace") or {}
                reviewer_trace = graph_result.get("reviewer_trace") or {}

                # 保存当前已经完成的 Multi-Agent 执行轨迹。
                agent_run.system_prompt = coder_trace.get("system_prompt")
                agent_run.initial_user_message = coder_trace.get("initial_user_message")
                agent_run.conversation = coder_trace.get(
                    "conversation",
                    [],
                )

                agent_run.iteration = int(coder_trace.get("iteration") or 0) + int(
                    reviewer_trace.get("iteration") or 0
                )

                agent_run.tokens_used = int(coder_trace.get("tokens_used") or 0) + int(
                    reviewer_trace.get("tokens_used") or 0
                )

                agent_run.tool_calls_made = int(coder_trace.get("tool_calls_made") or 0) + int(
                    reviewer_trace.get("tool_calls_made") or 0
                )

                # 保存当前业务结果，方便 API / 前端展示审批内容。
                agent_run.final_result = {
                    "success": None,
                    "status": "waiting_for_approval",
                    "code_result": graph_result.get("code_result", {}),
                    "test_result": graph_result.get("test_result", {}),
                    "review_result": graph_result.get("review_result", {}),
                }

                # 关键状态：不是失败，也不是完成。
                agent_run.status = "WAITING_FOR_APPROVAL"

                # 任务只是暂停，不应写 completed_at。
                agent_run.completed_at = None
                agent_run.elapsed_seconds = None
                agent_run.error = None

                await db.commit()

                return {
                    "status": "waiting_for_approval",
                    "agent_run_id": str(agent_run.id),
                }

            # =========================================================
            # 7. 提取 Multi-Agent 执行结果
            # =========================================================

            workflow_result = graph_result.get("final_result") or {}

            code_result = graph_result.get("code_result") or {}

            coder_trace = graph_result.get("coder_trace") or {}

            reviewer_trace = graph_result.get("reviewer_trace") or {}

            # ---------------------------------------------------------
            # 保存 Agent 执行轨迹
            # ---------------------------------------------------------
            #
            # AgentRun 原本的数据模型是按“单 Agent”
            # 设计的。
            #
            # 当前先继续使用 Coder 作为主轨迹，
            # 避免现在同时修改数据库 Schema。
            # ---------------------------------------------------------

            agent_run.system_prompt = coder_trace.get("system_prompt")

            agent_run.initial_user_message = coder_trace.get("initial_user_message")

            agent_run.conversation = coder_trace.get(
                "conversation",
                [],
            )

            # 保存整个 Multi-Agent 最终结果。
            agent_run.final_result = workflow_result

            # Coder + Reviewer 统计汇总。
            agent_run.iteration = int(coder_trace.get("iteration") or 0) + int(
                reviewer_trace.get("iteration") or 0
            )

            agent_run.tokens_used = int(coder_trace.get("tokens_used") or 0) + int(
                reviewer_trace.get("tokens_used") or 0
            )

            agent_run.tool_calls_made = int(coder_trace.get("tool_calls_made") or 0) + int(
                reviewer_trace.get("tool_calls_made") or 0
            )

            # =========================================================
            # 8. 判断 Multi-Agent Workflow 是否成功
            # =========================================================

            if not workflow_result.get("success"):
                failure_reason = (
                    workflow_result.get("reason")
                    or graph_result.get("coder_error")
                    or graph_result.get("reviewer_error")
                    or ("multi_agent_workflow_failed")
                )

                agent_run.status = "FAILED"
                agent_run.error = failure_reason

                agent_run.completed_at = _utcnow()

                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )

                await db.commit()

                return {
                    "status": "failed",
                    "reason": failure_reason,
                    "agent_run_id": str(agent_run.id),
                }

            # =========================================================
            # 9. 从 Coder Result 获取 Summary / Branch
            # =========================================================

            summary = (code_result.get("summary") or "").strip()

            branch_name = (code_result.get("branch_name") or "").strip()

            if not summary:
                summary = f"Implemented issue #{agent_run.issue_number} via multi-agent workflow."

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
                    "reason": ("missing_branch_name"),
                    "agent_run_id": str(agent_run.id),
                }

            # =========================================================
            # 10. 验证 Branch 已 Push 到 origin
            # =========================================================

            branch_check_response = sandbox.process.exec(
                command=(f"git ls-remote --heads origin {shlex.quote(branch_name)}"),
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
                    f"exit_code="
                    f"{branch_check_response.exit_code}, "
                    f"output="
                    f"{(branch_check_response.result or '').strip()[:500]}"
                )

                agent_run.completed_at = _utcnow()

                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )

                await db.commit()

                return {
                    "status": "failed",
                    "reason": ("branch_not_pushed_to_origin"),
                    "agent_run_id": str(agent_run.id),
                }

            # =========================================================
            # 11. 获取整个任务修改过的文件
            # =========================================================
            #
            # 原来：
            #
            # HEAD~1..HEAD
            #
            # 只能看到最后一个 Commit。
            #
            # 现在比较：
            #
            # base_branch...HEAD
            #
            # 得到整个 Coding Task 的全部修改。
            # =========================================================

            changed_files: list[str] = []

            try:
                diff_response = sandbox.process.exec(
                    command=(f"git diff --name-only {shlex.quote(base_branch)}...HEAD"),
                    cwd="workspace/repo",
                    timeout=30,
                )

                if diff_response.exit_code == 0:
                    changed_files = _extract_changed_files_from_diff_output(
                        diff_response.result or ""
                    )

            except Exception:
                changed_files = []

            # 如果无法取得 Commit Diff，
            # 退回 Sandbox 当前 Git 状态。
            if not changed_files:
                try:
                    status = sandbox.git.status("workspace/repo")

                    changed_files = [f.name for f in status.file_status]

                except Exception:
                    changed_files = []

            # =========================================================
            # 12. 创建 GitHub PR
            # =========================================================
            #
            # PR 属于外层确定性业务副作用。
            #
            # 不让 LLM 自己直接调用 GitHub API 创建。
            # =========================================================

            pr_title, pr_body = _build_pr_payload(
                issue_number=(agent_run.issue_number),
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
                installation_id=(installation.github_installation_id),
            )

            # 成功任务写入 Memory
            await remember_successful_run(
                db,
                llm_client=get_llm_client(),
                repository=agent_run.repository,
                issue_number=agent_run.issue_number,
                issue_title=agent_run.issue_title_snapshot or "",
                issue_body=agent_run.issue_body_snapshot or "",
                solution_summary=summary,
                source_agent_run_id=agent_run.id,
                success=True,
                test_result=workflow_result.get("test_result") or {},
                review_result=workflow_result.get("review_result") or {},
                human_approved=True,
            )

            # =========================================================
            # 13. AgentRun -> COMPLETED
            # =========================================================

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
                "pr_number": (agent_run.pr_number),
                "pr_url": (agent_run.pr_url),
            }

        # =============================================================
        # 全局异常处理
        # =============================================================

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

                # 如果 Multi-Agent Graph 已经跑完，
                # 即使后面的 Branch / PR 阶段失败，
                # 仍然保存已有执行轨迹。
                if graph_result:
                    coder_trace = graph_result.get("coder_trace") or {}

                    reviewer_trace = graph_result.get("reviewer_trace") or {}

                    agent_run.system_prompt = coder_trace.get("system_prompt")

                    agent_run.initial_user_message = coder_trace.get("initial_user_message")

                    agent_run.conversation = coder_trace.get(
                        "conversation",
                        [],
                    )

                    agent_run.final_result = graph_result.get("final_result") or {}

                    agent_run.iteration = int(coder_trace.get("iteration") or 0) + int(
                        reviewer_trace.get("iteration") or 0
                    )

                    agent_run.tokens_used = int(coder_trace.get("tokens_used") or 0) + int(
                        reviewer_trace.get("tokens_used") or 0
                    )

                    agent_run.tool_calls_made = int(coder_trace.get("tool_calls_made") or 0) + int(
                        reviewer_trace.get("tool_calls_made") or 0
                    )

                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )

                await db.commit()

            # 继续抛出，让 Celery 知道 Task 本身失败。
            raise

        # =============================================================
        # Sandbox / DB 最终资源清理
        # =============================================================

        finally:
            # Sandbox 是 Celery Task 创建的，
            # 所以最终生命周期由这里负责。
            #
            # Multi-Agent Graph 收到的是外部注入的 Sandbox，
            # 不负责删除它。
            if sandbox_manager:
                try:
                    sandbox_manager.release(f"{agent_run_id}:coder")

                except Exception as cleanup_err:
                    logger.error(
                        "Background sandbox cleanup failed: %s",
                        cleanup_err,
                    )

            try:
                await engine.dispose()

            except Exception as dispose_err:
                logger.error(
                    "Engine dispose failed: %s",
                    dispose_err,
                )


@celery_app.task(
    bind=True,
    base=BaseTask,
    time_limit=1800,
)
def resume_issue_after_approval(
    self,
    agent_run_id: str,
    approved: bool,
):
    """人工 Approve / Reject 后恢复 LangGraph。"""

    return _run_async(
        _resume_issue_after_approval_async(
            self,
            agent_run_id,
            approved,
        )
    )


# resume task
async def _resume_issue_after_approval_async(
    task_self,
    agent_run_id: str,
    approved: bool,
):
    """恢复处于 WAITING_FOR_APPROVAL 的 AgentRun。"""

    agent_run = None

    async with AsyncSessionLocal() as db:
        github = GitHubService()

        try:
            # 1. 读取 AgentRun
            run_query = await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))

            agent_run = run_query.scalar_one_or_none()

            if not agent_run:
                return {
                    "status": "ignored",
                    "reason": "agent_run_not_found",
                }

            # 2. 获取 GitHub Installation
            installation_query = await db.execute(
                select(Installation).where(
                    and_(
                        Installation.id == agent_run.installation_id,
                        Installation.repository == agent_run.repository,
                        Installation.is_active == True,  # noqa: E712
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
                    "reason": ("installation_not_found_or_inactive"),
                }

            # 恢复过程中属于 RUNNING。
            agent_run.status = "RUNNING"
            agent_run.error = None

            agent_run.celery_task_id = task_self.request.id

            await db.commit()

            # 3. 使用同一个 AgentRun ID 恢复 checkpoint
            graph_result = await resume_multi_agent_graph(
                thread_id=str(agent_run.id),
                approved=approved,
            )

            workflow_result = graph_result.get("final_result") or {}

            # =================================================
            # Human Reject
            # =================================================

            if not approved:
                agent_run.status = "CANCELED"

                agent_run.final_result = workflow_result or {
                    "success": False,
                    "reason": "human rejected",
                    "human_approved": False,
                }

                agent_run.error = "human rejected"
                agent_run.completed_at = _utcnow()

                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )

                await db.commit()

                return {
                    "status": "canceled",
                    "reason": "human rejected",
                    "agent_run_id": str(agent_run.id),
                }

            # =================================================
            # Human Approve
            # =================================================

            if not workflow_result.get("success"):
                reason = workflow_result.get("reason") or "multi_agent_resume_failed"

                agent_run.status = "FAILED"
                agent_run.error = reason
                agent_run.final_result = workflow_result
                agent_run.completed_at = _utcnow()

                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )

                await db.commit()

                return {
                    "status": "failed",
                    "reason": reason,
                    "agent_run_id": str(agent_run.id),
                }

            code_result = graph_result.get("code_result") or {}

            summary = (code_result.get("summary") or "").strip()

            branch_name = (code_result.get("branch_name") or "").strip()

            if not summary:
                summary = f"Implemented issue #{agent_run.issue_number} via multi-agent workflow."

            if not branch_name:
                agent_run.status = "FAILED"
                agent_run.error = "missing_branch_name"
                agent_run.completed_at = _utcnow()

                await db.commit()

                return {
                    "status": "failed",
                    "reason": "missing_branch_name",
                    "agent_run_id": str(agent_run.id),
                }

            # 4. 获取 Repository 默认 Branch
            owner, repo = agent_run.repository.split("/")

            repo_data = await github.get_repository(
                owner=owner,
                repo=repo,
                installation_id=(installation.github_installation_id),
            )

            base_branch = repo_data.get("default_branch") or "main"

            # 5. 人工批准后真正创建 PR
            pr_title, pr_body = _build_pr_payload(
                issue_number=agent_run.issue_number,
                issue_title=(agent_run.issue_title_snapshot or ""),
                summary=summary,
            )

            pr_data = await github.create_pull_request(
                owner=owner,
                repo=repo,
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base=base_branch,
                installation_id=(installation.github_installation_id),
            )

            # 6. 完成 AgentRun
            completed_at = _utcnow()

            agent_run.status = "COMPLETED"
            agent_run.completed_at = completed_at

            if agent_run.started_at:
                agent_run.elapsed_seconds = int(
                    (completed_at - agent_run.started_at).total_seconds()
                )

            agent_run.branch_name = branch_name
            agent_run.final_summary = summary

            agent_run.pr_number = pr_data.get("number")

            agent_run.pr_url = pr_data.get("html_url")

            agent_run.final_result = workflow_result

            agent_run.error = None

            await db.commit()

            return {
                "status": "success",
                "agent_run_id": str(agent_run.id),
                "pr_number": agent_run.pr_number,
                "pr_url": agent_run.pr_url,
            }

        except Exception as exc:
            logger.error(
                "Resume HITL task failed run=%s: %s",
                agent_run_id,
                exc,
                exc_info=True,
            )

            await db.rollback()

            if agent_run:
                await db.refresh(agent_run)

                agent_run.status = "FAILED"
                agent_run.error = str(exc)
                agent_run.completed_at = _utcnow()

                if agent_run.started_at:
                    agent_run.elapsed_seconds = int(
                        (agent_run.completed_at - agent_run.started_at).total_seconds()
                    )

                await db.commit()

            raise
