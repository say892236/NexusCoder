import asyncio
import os
import selectors
import sys
from uuid import uuid4

import pytest
from langgraph.types import Command

from app.agents.multi_agent.checkpointer import create_postgres_checkpointer
from app.agents.multi_agent.graph import build_graph
from app.agents.sandbox.mock import MockSandbox
from app.core.mock_client import MockLLM


async def run_postgres_test():
    # 使用唯一 thread_id，避免读取之前的 Checkpoint
    config = {
        "configurable": {"thread_id": f"pg-hitl-{uuid4().hex}"},
        "recursion_limit": 50,
    }

    sandbox = MockSandbox()
    context = {"sandbox": sandbox, "llm_client": MockLLM()}

    try:
        # 第一次连接：执行到 HITL 暂停
        async with create_postgres_checkpointer() as cp:
            graph = build_graph(checkpointer=cp)

            result = await graph.ainvoke(
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

            assert "__interrupt__" in result

        # 第二次连接：从 PostgreSQL 恢复之前暂停的工作流
        async with create_postgres_checkpointer() as cp:
            graph = build_graph(checkpointer=cp)

            result = await graph.ainvoke(
                Command(resume=True),
                config=config,
                context=context,
            )

            assert result["human_approved"] is True
            assert result["final_result"]["success"] is True

    finally:
        sandbox.delete()


# 只有显式开启时才执行真实数据库测试
@pytest.mark.skipif(
    os.getenv("RUN_PG_TEST") != "1",
    reason="需要真实 PostgreSQL，设置 RUN_PG_TEST=1 后执行",
)
def test_hitl_postgres():
    # Windows + Psycopg 使用 SelectorEventLoop
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        try:
            loop.run_until_complete(run_postgres_test())
        finally:
            loop.close()
    else:
        asyncio.run(run_postgres_test())