import asyncio

from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.process_tools import RunCodeTool


async def main():

    manager = SandboxManager()

    sandbox = manager.acquire(
        agent_id="run-code-test-001",
        repository_url=None,
        language="python",
    )


    tool = RunCodeTool(
        sandbox
    )


    result = await tool.execute(
        code="print('hello from Daytona')"
    )


    print("================")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
