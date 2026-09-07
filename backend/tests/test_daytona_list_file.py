import asyncio

from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.file_tools import ListFilesTool


async def main():

    manager = SandboxManager()

    sandbox = manager.acquire(
        agent_id="file-test",
        repository_url="https://github.com/pallets/flask.git",
        language="python",
    )


    tool = ListFilesTool(
        sandbox
    )


    result = await tool.execute(
        directory="workspace/repo"
    )


    print("================")
    print(result)



if __name__ == "__main__":
    asyncio.run(main())
