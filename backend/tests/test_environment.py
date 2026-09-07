import pytest

from app.agents.multi_agent.nodes.environment import (
    cleanup_environment_node,
    prepare_environment_node,
)
from app.agents.sandbox.mock import MockSandbox


@pytest.mark.asyncio
async def test_external_sandbox_should_not_be_deleted():
    sandbox = MockSandbox()

    state = {
        "repository": "mock_workspace",
        "sandbox": sandbox,
    }

    # 外部已经提供 Sandbox。
    prepared = await prepare_environment_node(state)

    assert prepared["sandbox"] is sandbox
    assert prepared["sandbox_owned"] is False

    # cleanup 不应该删除外部资源。
    await cleanup_environment_node({
        **state,
        **prepared,
    })

    assert sandbox.fs.base.exists()

    # 测试自己负责清理自己创建的资源。
    sandbox.delete()


@pytest.mark.asyncio
async def test_owned_mock_sandbox_should_be_deleted():
    sandbox = MockSandbox()

    base_path = sandbox.fs.base

    state = {
        "sandbox": sandbox,
        "sandbox_owned": True,
    }

    assert base_path.exists()

    await cleanup_environment_node(state)

    assert not base_path.exists()
