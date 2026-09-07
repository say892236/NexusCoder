from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings


def get_checkpoint_database_url() -> str:
    """
    将 SQLAlchemy asyncpg URL 转成
    LangGraph Postgres Checkpointer 使用的 Psycopg URL。
    """

    return settings.DATABASE_URL.replace(
        "postgresql+asyncpg://",
        "postgresql://",
        1,
    )


def create_postgres_checkpointer():
    """创建 LangGraph PostgreSQL Checkpointer。"""

    return AsyncPostgresSaver.from_conn_string(
        get_checkpoint_database_url()
    )
