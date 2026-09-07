"""真实 LLM + MockSandbox 的 Multi-Agent Smoke Test。"""

import asyncio
from pprint import pprint

from app.agents.multi_agent.graph import build_graph
from app.agents.sandbox.mock import MockSandbox
from app.core.client import get_llm_client


def print_agent_metrics(
    name: str,
    trace: dict | None,
) -> None:
    """打印 Agent 的核心运行和 Token 指标。"""

    if not trace:
        print(f"\n{name}: N/A")
        return

    prompt_tokens = trace.get("prompt_tokens", 0)
    cache_hit_tokens = trace.get("cache_hit_tokens", 0)

    cache_hit_rate = (
        cache_hit_tokens / prompt_tokens
        if prompt_tokens
        else 0.0
    )

    print(f"\n{name}:")
    print(f"  Iterations        : {trace.get('iteration', 0)}")
    print(f"  Tool Calls        : {trace.get('tool_calls_made', 0)}")
    print(f"  Total Tokens      : {trace.get('tokens_used', 0)}")
    print(f"  Prompt Tokens     : {prompt_tokens}")
    print(f"  Cache Hit Tokens  : {cache_hit_tokens}")
    print(f"  Cache Miss Tokens : {trace.get('cache_miss_tokens', 0)}")
    print(f"  Completion Tokens : {trace.get('completion_tokens', 0)}")
    print(f"  Cache Hit Rate    : {cache_hit_rate:.2%}")


async def main() -> None:
    """运行一次真实模型 Coding Agent 工作流。"""

    graph = build_graph()

    sandbox = MockSandbox()

    # MOCK_LLM=false 后，这里会拿到真实 LiteLLM Client。
    llm_client = get_llm_client()

    try:
        result = await graph.ainvoke(
            {
                "repository": "mock_workspace",
                "issue_number": 1,
                "issue_title": "修复登录接口500错误",
                "issue_body": (
                    "使用正确账号 admin / 123456 登录时，"
                    "接口会返回 500。请定位问题并修复，"
                    "确保现有测试通过。"
                ),
                "custom_instructions": "",
                "base_branch": "main",
                "retry_count": 0,
                "code_result": {},
                "test_result": {},
                "review_result": {},
            },
            context={
                "sandbox": sandbox,
                "llm_client": llm_client,
            },
            config={
                "recursion_limit": 50,
            },
        )

        print("\n========== Real LLM Smoke Test ==========\n")

        print("Retry Count:")
        print(result.get("retry_count"))

        print("\nCode Result:")
        pprint(result.get("code_result"))

        print("\nTest Result:")
        pprint(result.get("test_result"))

        print("\nReview Result:")
        pprint(result.get("review_result"))

        print("\nFinal Result:")
        pprint(result.get("final_result"))

        print_agent_metrics(
            "Coder Metrics",
            result.get("coder_trace"),
        )

        print_agent_metrics(
        "Reviewer Metrics",
    result.get("reviewer_trace"),
)
        print("\n=========================================\n")

    finally:
        sandbox.delete()


if __name__ == "__main__":
    asyncio.run(main())
