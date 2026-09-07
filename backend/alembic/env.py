import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings

# 导入 ORM Base 与全部 model，供 Alembic 比较 metadata。
from app.db.base import Base

# 显式导入全部 model，确保 autogenerate 能检测表结构。
from app.models import agent_run, installation, review, user  # noqa: F401

# Alembic Config 对象。
config = context.config

# 使用应用配置覆盖 alembic.ini 中的 sqlalchemy.url。
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 读取配置文件并初始化 Python logging。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 将 model MetaData 提供给 autogenerate。
# 示例：可导入业务 model，并将其 ``Base.metadata`` 设为 target_metadata。
target_metadata = Base.metadata
# LangGraph Checkpointer / Store 自己管理的表。
# 这些表不属于 NexusCoder SQLAlchemy ORM，Alembic 不应参与迁移。
LANGGRAPH_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
    "store",
    "store_vectors",
    "store_migrations",
    "vector_migrations",
}


def include_object(
    object_,
    name,
    type_,
    reflected,
    compare_to,
):
    """忽略由 LangGraph 自己维护的数据库表。"""

    if type_ == "table" and name in LANGGRAPH_TABLES:  # noqa: SIM103
        return False

    return True

# 其他 env.py 配置也可通过 config 按需读取。
# 示例：可通过 ``config.get_main_option("my_important_option")`` 读取其他选项。


def run_migrations_offline() -> None:
    """以 offline 模式生成 migration SQL。

    仅使用数据库 URL 配置 context, 不创建 Engine, 因此无需可用的 DBAPI 或数据库连接。

    ``context.execute()`` 会把 SQL 写入脚本输出。

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """使用给定数据库连接执行 migration。"""
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """以异步模式执行实际数据库 migration。

    创建 async Engine, 并在连接上下文中运行 migration, 以匹配项目的异步 SQLAlchemy。
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """以 online 模式连接数据库并执行 migration。

    由于项目使用异步 SQLAlchemy, 这里在 async context 中创建和使用 Engine。
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
