import time

import pytest

from app.agents.base import (
    AgentStatus,
    BaseAgent,
)


class DummyAgent(BaseAgent):
    """只用于测试 BaseAgent 的预算停止逻辑。"""



@pytest.mark.parametrize(
    ("limit_type", "setup_state", "expected_reason"),
    [
        (
            "iterations",
            lambda agent: setattr(
                agent.state,
                "iteration",
                agent.max_iterations,
            ),
            "max_iterations_reached",
        ),
        (
            "tokens",
            lambda agent: setattr(
                agent.state,
                "tokens_used",
                agent.max_tokens,
            ),
            "max_tokens_reached",
        ),
        (
            "tool_calls",
            lambda agent: setattr(
                agent.state,
                "tool_calls_made",
                agent.max_tool_calls,
            ),
            "max_tool_calls_reached",
        ),
        (
            "duration",
            lambda agent: setattr(
                agent.state,
                "start_time",
                time.time() - agent.max_duration_seconds - 1,
            ),
            "max_duration_reached",
        ),
    ],
)
def test_should_stop_marks_failed_when_budget_reached(
    limit_type,
    setup_state,
    expected_reason,
):
    agent = DummyAgent(
        agent_id="test-agent",
        system_prompt="test",
        initial_user_message="test",
        tools=None,
        llm_client=None,
        max_iterations=3,
        max_tokens=100,
        max_tool_calls=5,
        max_duration_seconds=10,
    )

    # 模拟某一种资源预算已经耗尽。
    setup_state(agent)

    should_stop = agent.should_stop()

    assert should_stop is True

    # 预算耗尽不能算正常完成。
    assert agent.state.status == AgentStatus.FAILED

    # 上层可以准确知道失败原因。
    assert agent.state.error == expected_reason

    # result 也明确表示任务没有真正完成。
    assert agent.state.result["completed"] is False
    assert agent.state.result["reason"] == expected_reason
