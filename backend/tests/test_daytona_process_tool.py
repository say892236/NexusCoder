import asyncio

from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.process_tools import RunCommandTool


async def main():

    print("🚀 创建 Daytona Sandbox")

    manager = SandboxManager()

    sandbox = manager.acquire(
        agent_id="process-tool-test",
        repository_url=None,
        language="python",
    )

    print("✅ Sandbox 创建成功")


    tool = RunCommandTool(
        sandbox=sandbox
    )


    result = await tool.execute(
        command="python --version"
    )


    print("========== Tool Result ==========")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
