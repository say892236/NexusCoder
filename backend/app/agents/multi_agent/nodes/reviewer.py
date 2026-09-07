import asyncio

from langgraph.runtime import Runtime

from app.agents.implementation.review_agent import ReviewAgent
from app.agents.loop import AgentLoop
from app.agents.multi_agent.context import MultiAgentRuntimeContext
from app.agents.multi_agent.state import CodingAgentState
from app.agents.tools.manager import get_multi_agent_reviewer_tools
from app.agents.tools.reviewer_tools import GitDiffTool
from app.core.client import get_llm_client


async def reviewer_node(
    state: CodingAgentState,
    runtime: Runtime[MultiAgentRuntimeContext],
):
    """执行 Reviewer Agent。"""

    print("👀 Reviewer Agent 启动")

    sandbox = runtime.context.get("sandbox")

    if sandbox is None:
        raise RuntimeError("Reviewer requires sandbox in MultiAgentRuntimeContext")

    llm_client = runtime.context.get("llm_client") or get_llm_client()

    base_branch = state.get(
        "base_branch",
        "main",
    )

    tools = get_multi_agent_reviewer_tools(
        sandbox=sandbox,
        base_branch=base_branch,
    )

    # Reviewer 进入 LLM 前，
    # 先确定性获取整个 Branch Diff。
    diff_tool = GitDiffTool(
        sandbox=sandbox,
        base_branch=base_branch,
    )

    try:
        diff_result = await asyncio.wait_for(
            diff_tool.execute(),
            timeout=30,
        )

    except asyncio.TimeoutError:
        return {
            "current_agent": "reviewer",
            "review_result": {
                "completed": False,
                "verdict": "REQUEST_CHANGES",
                "summary": "获取Git Diff超时",
                "error": "timeout",
            },
            "reviewer_status": "failed",
            "reviewer_error": "timeout",
        }

    if not diff_result.success:
        return {
            "current_agent": "reviewer",
            "review_result": {
                "completed": False,
                "verdict": "REQUEST_CHANGES",
                "summary": "无法获取代码 Diff",
                "error": diff_result.error,
            },
            "reviewer_status": "failed",
            "reviewer_error": (diff_result.error),
        }

    pr_diff = diff_result.data.get(
        "diff",
        "",
    )

    # 没有 Diff 时直接通过。
    if not pr_diff.strip():
        return {
            "current_agent": "reviewer",
            "review_result": {
                "completed": True,
                "verdict": "APPROVE",
                "summary": "没有检测到代码变更",
                "findings": [],
            },
            "reviewer_status": "completed",
            "reviewer_error": None,
        }

    agent = ReviewAgent(
        agent_id="reviewer",
        pr_title=state["issue_title"],
        pr_description=state["issue_body"],
        pr_diff=pr_diff,
        sensitivity=state.get(
            "review_sensitivity",
            "MEDIUM",
        ),
        custom_instructions=state.get(
            "review_custom_instructions",
            "",
        ),
        ignore_patterns=state.get(
            "review_ignore_patterns",
            [],
        ),
        tools=tools,
        llm_client=llm_client,
    )

    try:
        final_state = await asyncio.wait_for(
            AgentLoop(agent).execute(),
            timeout=120,
        )

    except asyncio.TimeoutError:
        return {
            "current_agent": "reviewer",
            "review_result": {
                "completed": False,
                "verdict": "REQUEST_CHANGES",
                "summary": "代码评审执行超时",
                "error": "agent_loop_timeout",
            },
            "reviewer_status": "failed",
            "reviewer_error": ("agent_loop_timeout"),
        }

    # =========================================================
    # 累计 Reviewer Token Usage
    #
    # reviewer_trace 只保存最近一次 Reviewer 的完整 Trace；
    # reviewer_usage 保存整个 Workflow 中所有 Reviewer LLM
    # 执行的累计 Token 消耗。
    # =========================================================

    previous_usage = state.get(
        "reviewer_usage",
        {},
    )

    reviewer_usage = {
        "runs": (previous_usage.get("runs", 0) + 1),
        "tokens_used": (previous_usage.get("tokens_used", 0) + final_state.tokens_used),
        "prompt_tokens": (previous_usage.get("prompt_tokens", 0) + final_state.prompt_tokens),
        "completion_tokens": (
            previous_usage.get("completion_tokens", 0) + final_state.completion_tokens
        ),
        "cache_hit_tokens": (
            previous_usage.get("cache_hit_tokens", 0) + final_state.cache_hit_tokens
        ),
        "cache_miss_tokens": (
            previous_usage.get("cache_miss_tokens", 0) + final_state.cache_miss_tokens
        ),
    }

    return {
        "current_agent": "reviewer",
        "review_result": (final_state.result or {}),
        "reviewer_status": (final_state.status.value),
        "reviewer_error": (final_state.error),
        # 最近一次 Reviewer 的完整运行轨迹。
        "reviewer_trace": {
            "system_prompt": agent.system_prompt,
            "initial_user_message": agent.initial_user_message,
            "conversation": final_state.messages,
            "iteration": final_state.iteration,
            "tokens_used": final_state.tokens_used,
            "prompt_tokens": final_state.prompt_tokens,
            "completion_tokens": final_state.completion_tokens,
            "cache_hit_tokens": final_state.cache_hit_tokens,
            "cache_miss_tokens": final_state.cache_miss_tokens,
            "tool_calls_made": final_state.tool_calls_made,
        },
        # 整个 Workflow 生命周期中的 Reviewer 累计 Usage。
        "reviewer_usage": reviewer_usage,
    }
