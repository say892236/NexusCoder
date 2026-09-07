import asyncio

from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.file_tools import (
    CreateFileTool,
    ReadFileTool,
    ReplaceInFilesTool,
)


async def main():

    manager = SandboxManager()


    sandbox = manager.acquire(
        agent_id="replace-file-test",
        repository_url="https://github.com/pallets/flask.git",
        language="python",
    )


    # 1. 创建测试文件
    create_tool = CreateFileTool(
        sandbox
    )


    create_result = await create_tool.execute(
        file_path="hello.py",
        content='print("old version")'
    )


    print("================ create")
    print(create_result)



    # 2. 替换内容
    replace_tool = ReplaceInFilesTool(
        sandbox
    )


    replace_result = await replace_tool.execute(
        files=[
            "hello.py"
        ],
        pattern="old version",
        replacement="new version",
    )


    print("================ replace")
    print(replace_result)



    # 3. 读取验证
    read_tool = ReadFileTool(
        sandbox
    )


    read_result = await read_tool.execute(
        file_path="hello.py"
    )


    print("================ read")
    print(read_result)



if __name__ == "__main__":
    asyncio.run(main())
