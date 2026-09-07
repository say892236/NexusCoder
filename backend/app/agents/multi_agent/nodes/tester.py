from langgraph.runtime import Runtime

from app.agents.multi_agent.context import MultiAgentRuntimeContext
from app.agents.multi_agent.state import CodingAgentState


async def tester_node(
    state: CodingAgentState,
    runtime: Runtime[MultiAgentRuntimeContext],
):
    """
    执行确定性测试。

    Tester 不需要 LLM，
    直接通过 pytest 的退出码判断测试是否成功。
    """

    print("🧪 Tester 正在执行测试")

    sandbox = runtime.context.get("sandbox")

    if sandbox is None:
        raise RuntimeError(
            "Tester requires sandbox in MultiAgentRuntimeContext"
        )

    result = sandbox.process.exec(
        command="pytest",
        cwd="workspace/repo",
        timeout=120,
    )

    return {
        "current_agent": "tester",

        "test_result": {
            "passed": (
                result.exit_code == 0
            ),

            "output": (
                result.result
            ),
        },
    }
