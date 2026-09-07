from app.agents.sandbox.manager import SandboxManager
from app.agents.sandbox.mock import MockSandbox
from app.core.config import settings

SANDBOX_AGENT_ID = "coder"


async def prepare_environment_node(state):
    """准备整个 Multi-Agent Workflow 共用的 Sandbox。"""

    # 1. 外部已经注入 Sandbox：
    #    直接复用，并且 Graph 不拥有它的生命周期。
    if state.get("sandbox") is not None:
        print("🧪 使用已有 Sandbox")

        return {
            "sandbox": state["sandbox"],
            "sandbox_owned": False,
        }

    # 2. 本地 Mock 模式：
    #    Sandbox 由 Graph 自己创建，因此结束后需要清理。
    if settings.MOCK_SANDBOX:
        print("🧪 使用 Mock Sandbox")

        sandbox = MockSandbox()

        return {
            "sandbox": sandbox,
            "sandbox_owned": True,
        }

    # 3. 真实 Daytona：
    #    保存 manager，因为后续 cleanup 必须用同一个实例 release。
    sandbox_manager = SandboxManager()

    sandbox = sandbox_manager.acquire(
        agent_id=SANDBOX_AGENT_ID,
        repository_url=state["repository"],
    )

    return {
        "sandbox": sandbox,
        "sandbox_manager": sandbox_manager,
        "sandbox_owned": True,
    }


async def cleanup_environment_node(state):
    """释放由当前 Graph 自己创建的 Sandbox。"""

    # 外部注入的 Sandbox 不属于 Graph，不能擅自删除。
    if not state.get("sandbox_owned", False):
        print("🧹 Sandbox 由外部管理，跳过清理")
        return {}

    sandbox = state.get("sandbox")
    sandbox_manager = state.get("sandbox_manager")

    try:
        # 真实 Daytona：
        # 必须通过创建它的同一个 SandboxManager release。
        if sandbox_manager is not None:
            sandbox_manager.release(
                SANDBOX_AGENT_ID
            )

            print("🧹 Daytona Sandbox 已释放")
            return {}

        # MockSandbox 没有经过 SandboxManager，
        # 直接调用自身 delete。
        if sandbox is not None:
            sandbox.delete()

            print("🧹 Mock Sandbox 已释放")

    except Exception as e:
        # 清理失败不能覆盖 Coding Task 本身的执行结果。
        print(f"⚠️ Sandbox cleanup failed: {e}")

    return {}
