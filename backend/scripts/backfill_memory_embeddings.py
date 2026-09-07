"""给历史 AgentMemory 补齐 Embedding。"""

import asyncio

from app.agents.memory.service import (
    backfill_memory_embeddings,
)
from app.db.base import AsyncSessionLocal, engine


async def main():
    """批量补齐历史 Memory Embedding。"""

    total = 0

    while True:
        async with AsyncSessionLocal() as db:
            count = await backfill_memory_embeddings(
                db,
                batch_size=100,
            )

            await db.commit()

        total += count

        print(f"本批处理 {count} 条，累计 {total} 条。")

        if count == 0:
            break

    await engine.dispose()

    print(f"Memory embedding backfill 完成，共处理 {total} 条。")


if __name__ == "__main__":
    asyncio.run(main())
