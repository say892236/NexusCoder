"""带连接池的 Redis 连接管理。"""

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

from app.core.config import settings


class RedisClient:
    """使用连接池的单例 Redis 客户端管理器。

    整个应用共享一个连接池，以减少重复建连并避免连接泄漏。
    """

    _instance: aioredis.Redis | None = None
    _pool: ConnectionPool | None = None

    @classmethod
    async def get_instance(cls) -> aioredis.Redis:
        """获取或创建 Redis 客户端实例。

        底层复用连接池，可安全地重复调用。
        """
        if cls._instance is None:
            cls._pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_keepalive=settings.REDIS_SOCKET_KEEPALIVE,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                decode_responses=True,  # 直接返回字符串而非 bytes。
            )
            cls._instance = aioredis.Redis(connection_pool=cls._pool)

        return cls._instance

    @classmethod
    async def close(cls) -> None:
        """关闭 Redis 连接池。"""
        if cls._instance:
            await cls._instance.aclose()
            cls._instance = None
        if cls._pool:
            await cls._pool.aclose()
            cls._pool = None


# 供 FastAPI 依赖注入使用的便捷函数。
async def get_redis() -> aioredis.Redis:
    """获取 Redis 客户端实例。"""
    return await RedisClient.get_instance()
