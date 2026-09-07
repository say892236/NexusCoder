from app.agents.multi_agent.graph import build_graph
from app.agents.sandbox.mock import MockSandbox
from app.core.mock_client import MockLLM


async def test_multi_agent_graph():
    """验证完整 Multi-Agent Graph 主流程。"""

    app = build_graph()

    sandbox = MockSandbox()
    llm_client = MockLLM()

    try:
        result = await app.ainvoke(
            # =========================
            # Graph State
            # =========================
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
            },

            # =========================
            # Runtime Context
            # =========================
            context={
                "sandbox": sandbox,
                "llm_client": llm_client,
            },

            config={
                "recursion_limit": 50,
            },
        )

        # Workflow 正常结束。
        assert result["next_agent"] == "finish"

        # 整体任务成功。
        assert result["final_result"]["success"] is True

        # Coder 完成代码修改。
        assert result["code_result"]["completed"] is True

        # Tester 测试通过。
        assert result["test_result"]["passed"] is True

        # Reviewer 审查通过。
        assert result["review_result"]["verdict"] == "APPROVE"

        # Agent 执行轨迹存在。
        assert "coder_trace" in result
        assert "reviewer_trace" in result

    finally:
        # 现在 Graph 不再管理 Sandbox 生命周期，
        # 测试自己创建的 Sandbox 由测试自己清理。
        sandbox.delete()
