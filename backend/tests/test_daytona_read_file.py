import asyncio

from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.file_tools import ReadFileTool


async def main():

    manager = SandboxManager()

    sandbox = manager.acquire(
        agent_id="read-file-test",
        repository_url="https://github.com/pallets/flask.git",
        language="python",
    )


    tool = ReadFileTool(
        sandbox
    )


    result = await tool.execute(
        file_path="README.md"
    )


    print("================")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
