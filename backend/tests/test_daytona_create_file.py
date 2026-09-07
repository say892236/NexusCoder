import asyncio

from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.file_tools import CreateFileTool, ReadFileTool


async def main():

    manager = SandboxManager()

    sandbox = manager.acquire(
        agent_id="create-file-test",
        repository_url="https://github.com/pallets/flask.git",
        language="python",
    )


    tool = CreateFileTool(
        sandbox
    )


    result = await tool.execute(
        file_path="agent_test.py",
        content="""
print("hello from coding agent")
"""
    )


    print("================ create result")
    print(result)


    # 再读取验证
    read_tool = ReadFileTool(
        sandbox
    )


    read_result = await read_tool.execute(
        file_path="agent_test.py"
    )


    print("================ read result")
    print(read_result)



if __name__ == "__main__":
    asyncio.run(main())
