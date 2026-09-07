import asyncio

from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.file_tools import (
    CreateFileTool,
    DeleteFileTool,
    ReadFileTool,
)


async def main():

    manager = SandboxManager()

    sandbox = manager.acquire(
        agent_id="delete-test",
        repository_url="https://github.com/pallets/flask.git",
        language="python",
    )


    # 1. 创建测试文件
    create_tool = CreateFileTool(sandbox)

    create_result = await create_tool.execute(
        file_path="test_delete.py",
        content="print('delete test')"
    )

    print("================ create")
    print(create_result)


    # 2. 删除文件
    delete_tool = DeleteFileTool(sandbox)

    delete_result = await delete_tool.execute(
        file_path="test_delete.py"
    )

    print("================ delete")
    print(delete_result)


    # 3. 尝试读取
    read_tool = ReadFileTool(sandbox)

    read_result = await read_tool.execute(
        file_path="test_delete.py"
    )

    print("================ read after delete")
    print(read_result)


if __name__ == "__main__":
    asyncio.run(main())
