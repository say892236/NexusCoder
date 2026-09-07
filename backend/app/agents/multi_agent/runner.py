from langsmith import trace
from langgraph.types import Command

from app.agents.multi_agent.checkpointer import (
    create_postgres_checkpointer,
)
from app.agents.multi_agent.graph import build_graph
from app.core.config import settings




async def run_multi_agent_graph(
    *,
    thread_id: str,
    repository: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    custom_instructions: str,
    base_branch: str,
    sandbox,
    llm_client,
    recalled_memories: list[dict[str, object]] | None = None,
    require_human_approval: bool = False,
) -> dict:
    """
    启动一次 Multi-Agent Coding Workflow。

    thread_id 使用 AgentRun ID，
    让 LangGraph 可以通过 PostgreSQL Checkpoint
    保存和恢复当前工作流。
    """

    # =========================
    # Graph State
    # =========================

    graph_input = {
        "repository": repository,
        "issue_number": issue_number,
        "issue_title": issue_title,
        "issue_body": issue_body,
        "custom_instructions": custom_instructions,
        "base_branch": base_branch,
        "retry_count": 0,
        "code_result": {},
        "test_result": {},
        "review_result": {},
        # 当前 Repository 召回出的历史 Memory。
        "recalled_memories": recalled_memories or [],
        # 是否开启 HITL。
        "require_human_approval": (require_human_approval),
    }

    # =========================
    # Runtime Context
    # =========================

    runtime_context = {
        "sandbox": sandbox,
        "llm_client": llm_client,
    }

    # =========================
    # LangGraph Config
    # =========================

    config = {
        "configurable": {
            # PostgreSQL Checkpointer
            # 使用它定位这一次 AgentRun。
            "thread_id": thread_id,
        },

        "recursion_limit": 50,
    }

    # =========================
    # PostgreSQL Checkpointer
    # =========================

    async with create_postgres_checkpointer() as checkpointer:

        graph = build_graph(
            checkpointer=checkpointer,
        )

        # LangSmith 只记录安全、必要的业务信息。
        # Sandbox、LLM Client、Issue Body 等不直接作为 Trace 输入。
        if settings.LANGSMITH_TRACING:
            async with trace(
                "multi_agent_workflow",
                run_type="chain",
                inputs={
                    "repository": repository,
                    "issue_number": issue_number,
                    "issue_title": issue_title,
                    "memory_count": len(
                        recalled_memories or []
                    ),
                    "require_human_approval": (
                        require_human_approval
                    ),
                },
                metadata={
                    "thread_id": thread_id,
                    "repository": repository,
                    "issue_number": issue_number,
                    "base_branch": base_branch,
                },
                tags=[
                    "multi-agent",
                    "coding-agent",
                    repository,
                ],
            ):
                return await graph.ainvoke(
                    graph_input,
                    config=config,
                    context=runtime_context,
                )

        return await graph.ainvoke(
            graph_input,
            config=config,
            context=runtime_context,
        )


async def resume_multi_agent_graph(
    *,
    thread_id: str,
    approved: bool,
) -> dict:
    """
    恢复一个正在等待人工审批的 Multi-Agent Workflow。

    approved=True:
        人工批准。

    approved=False:
        人工拒绝。
    """

    config = {
        "configurable": {
            # 必须与第一次执行完全相同。
            "thread_id": thread_id,
        },
        "recursion_limit": 50,
    }

    # Checkpointer 必须一直存活到 graph.ainvoke() 执行完成。
    async with create_postgres_checkpointer() as checkpointer:
        graph = build_graph(
            checkpointer=checkpointer,
        )

        if settings.LANGSMITH_TRACING:
            async with trace(
                "multi_agent_resume",
                run_type="chain",
                inputs={
                    "approved": approved,
                },
                metadata={
                    "thread_id": thread_id,
                },
                tags=[
                    "multi-agent",
                    "hitl",
                    "resume",
                ],
            ):
                return await graph.ainvoke(
                    Command(
                        resume=approved,
                    ),
                    config=config,
                )

        return await graph.ainvoke(
            Command(
                resume=approved,
            ),
            config=config,
        )
