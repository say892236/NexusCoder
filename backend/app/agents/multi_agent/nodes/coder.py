from langgraph.runtime import Runtime

from app.agents.implementation.background_agent import BackgroundAgent
from app.agents.loop import AgentLoop
from app.agents.multi_agent.context import MultiAgentRuntimeContext
from app.agents.multi_agent.state import CodingAgentState
from app.agents.tools.manager import get_coder_tools
from app.core.client import get_llm_client


async def coder_node(
    state: CodingAgentState,
    runtime: Runtime[MultiAgentRuntimeContext],
):
    """执行 Coder Agent，并把结果写回 Multi-Agent State。"""

    print("🤖 Coder Agent 启动")

    # Sandbox 属于运行时依赖，不进入 Graph State。
    sandbox = runtime.context.get("sandbox")

    if sandbox is None:
        raise RuntimeError("Coder requires sandbox in MultiAgentRuntimeContext")

    # 为 Coder 组装代码修改相关 Tools。
    tools = get_coder_tools(
        sandbox=sandbox,
    )

    # 优先使用 Runtime 注入的 LLM。
    llm_client = runtime.context.get("llm_client") or get_llm_client()

    agent = BackgroundAgent(
        agent_id="coder",
        repository=state["repository"],
        issue_number=state["issue_number"],
        issue_title=state["issue_title"],
        issue_body=state["issue_body"],
        custom_instructions=state.get(
            "custom_instructions",
            "",
        ),
        tools=tools,
        llm_client=llm_client,
        recalled_memories=state.get(
            "recalled_memories",
            [],
        ),
        # Retry Feedback：
        # Supervisor 决定重新进入 Coder 时，
        # 把上一轮测试 / Review 结果一并传入。
        retry_count=state.get(
            "retry_count",
            0,
        ),
        test_result=state.get(
            "test_result",
            {},
        ),
        review_result=state.get(
            "review_result",
            {},
        ),
    )

    # 单 Agent 内部：
    # LLM -> Tool -> Observation -> LLM ...
    final_state = await AgentLoop(agent).execute()

    # =========================================================
    # 累计 Coder Token Usage
    #
    # coder_trace 仍然只保存“本次” Coder 的完整 Trace；
    # coder_usage 保存整个 Workflow 中所有 Coder 运行的累计消耗。
    #
    # 当 Tester / Reviewer 触发 Retry 时，
    # 下一次进入 coder_node 会在旧 usage 基础上继续累加。
    # =========================================================

    previous_usage = state.get(
        "coder_usage",
        {},
    )

    coder_usage = {
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
        "current_agent": "coder",
        "code_result": (final_state.result or {}),
        "coder_status": (final_state.status.value),
        "coder_error": (final_state.error),
        # 最近一次 Coder 的完整运行轨迹。
        "coder_trace": {
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
        # 整个 Workflow 生命周期中的 Coder 累计 Usage。
        "coder_usage": coder_usage,
    }
