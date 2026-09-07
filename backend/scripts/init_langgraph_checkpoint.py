import asyncio
import selectors
import sys

from app.agents.multi_agent.checkpointer import (
    create_postgres_checkpointer,
)


async def main():
    """初始化 LangGraph Checkpoint 数据表。"""

    async with create_postgres_checkpointer() as checkpointer:
        await checkpointer.setup()

    print("LangGraph checkpoint tables initialized.")


if __name__ == "__main__":
    if sys.platform == "win32":
        # Psycopg async 在 Windows 下不能使用默认 ProactorEventLoop，
        # 因此显式创建 SelectorEventLoop。
        loop = asyncio.SelectorEventLoop(
            selectors.SelectSelector()
        )

        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
        finally:
            loop.close()

    else:
        asyncio.run(main())
