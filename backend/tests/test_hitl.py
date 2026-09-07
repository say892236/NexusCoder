import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.multi_agent.graph import build_graph
from app.agents.sandbox.mock import MockSandbox
from app.core.mock_client import MockLLM


@pytest.mark.asyncio
async def test_hitl_approve():
    """Reviewer 通过后暂停，人工批准后继续完成。"""

    sandbox = MockSandbox()

    try:
        checkpointer = InMemorySaver()

        graph = build_graph(
            checkpointer=checkpointer,
        )

        config = {
            "configurable": {
                "thread_id": "hitl-test-approve",
            },
            "recursion_limit": 50,
        }

        context = {
            "sandbox": sandbox,
            "llm_client": MockLLM(),
        }

        # =====================================================
        # 第一次执行
        # =====================================================
        # Coder -> Tester -> Reviewer -> Human Approval
        #
        # 到 interrupt 后暂停。
        # =====================================================

        paused_result = await graph.ainvoke(
            {
                "repository": "mock_workspace",
                "issue_number": 1,
                "issue_title": "修复登录接口500错误",
                "issue_body": "登录接口存在bug",

                "custom_instructions": "",
                "base_branch": "main",

                "retry_count": 0,
                "code_result": {},
                "test_result": {},
                "review_result": {},

                # 开启 HITL。
                "require_human_approval": True,
            },
            config=config,
            context=context,
        )

        # Graph 确实暂停了。
        assert "__interrupt__" in paused_result

        # =====================================================
        # 人工点击 Approve
        # =====================================================

        final_result = await graph.ainvoke(
            Command(
                resume=True,
            ),
            config=config,
            context=context,
        )

        assert (
            final_result["human_approved"]
            is True
        )

        assert (
            final_result["final_result"]["success"]
            is True
        )

        assert (
            final_result["next_agent"]
            == "finish"
        )

    finally:
        sandbox.delete()


@pytest.mark.asyncio
async def test_hitl_reject():
    """Reviewer 通过后暂停，人工拒绝后任务结束失败。"""

    sandbox = MockSandbox()

    try:
        checkpointer = InMemorySaver()

        graph = build_graph(
            checkpointer=checkpointer,
        )

        config = {
            "configurable": {
                "thread_id": "hitl-test-reject",
            },
            "recursion_limit": 50,
        }

        context = {
            "sandbox": sandbox,
            "llm_client": MockLLM(),
        }

        # 第一次运行：
        # Coder -> Tester -> Reviewer -> interrupt
        paused_result = await graph.ainvoke(
            {
                "repository": "mock_workspace",
                "issue_number": 1,
                "issue_title": "修复登录接口500错误",
                "issue_body": "登录接口存在bug",

                "custom_instructions": "",
                "base_branch": "main",

                "retry_count": 0,
                "code_result": {},
                "test_result": {},
                "review_result": {},

                "require_human_approval": True,
            },
            config=config,
            context=context,
        )

        # 确认 Graph 确实停在 HITL。
        assert "__interrupt__" in paused_result

        # 模拟用户点击 Reject。
        final_result = await graph.ainvoke(
            Command(
                resume=False,
            ),
            config=config,
            context=context,
        )

        assert final_result["human_approved"] is False

        assert (
            final_result["final_result"]["success"]
            is False
        )

        assert (
            final_result["final_result"]["reason"]
            == "human rejected"
        )

        assert final_result["next_agent"] == "finish"

    finally:
        sandbox.delete()
