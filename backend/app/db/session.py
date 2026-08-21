"""FastAPI 使用的异步数据库 session 依赖。"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供自动事务与生命周期管理的异步数据库 session。

    每个请求创建一个 SQLAlchemy AsyncSession 并 yield 给 endpoint；成功时自动 commit，
    异常时 rollback，最终始终关闭 session 并把连接归还连接池。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
