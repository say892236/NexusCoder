import pytest

from app.agents.multi_agent.runner import (
    run_multi_agent_graph,
)
from app.agents.sandbox.mock import MockSandbox
from app.core.mock_client import MockLLM


@pytest.mark.asyncio
async def test_background_task_can_run_multi_agent_graph():
    """验证后台任务能够正确接入 Multi-Agent Graph。"""

    sandbox = MockSandbox()

    try:
        result = await run_multi_agent_graph(
            thread_id="background-graph-test",
            repository="mock/repository",
            issue_number=1,
            issue_title="Fix login endpoint",
            issue_body="Login endpoint returns 500.",
            custom_instructions="",
            base_branch="main",
            sandbox=sandbox,
            llm_client=MockLLM(),
            require_human_approval=False,
        )

        # 整个 Multi-Agent Workflow 成功结束。
        assert result["next_agent"] == "finish"
        assert result["final_result"]["success"] is True

        # Coder 成功完成代码修改。
        assert result["code_result"]["completed"] is True

        # Tester 测试通过。
        assert result["test_result"]["passed"] is True

        # Reviewer 最终批准。
        assert result["review_result"]["verdict"] == "APPROVE"

        # Celery 后续需要使用的 Coder Trace 已经存在。
        assert "coder_trace" in result

        # Reviewer Trace 也成功返回。
        assert "reviewer_trace" in result

    finally:
        sandbox.delete()
