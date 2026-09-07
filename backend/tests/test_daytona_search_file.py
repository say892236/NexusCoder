import asyncio

from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.file_tools import SearchFilesTool


async def main():

    manager = SandboxManager()

    sandbox = manager.acquire(
        agent_id="search-test",
        repository_url="https://github.com/pallets/flask.git",
        language="python",
    )

    tool = SearchFilesTool(
        sandbox
    )

    result = await tool.execute(
        pattern="Flask",
        directory="workspace/repo"
    )

    print("================ search result")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
