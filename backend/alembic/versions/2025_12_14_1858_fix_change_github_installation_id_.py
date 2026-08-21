"""修复：将 github_installation_id 唯一约束改为与 Repository 的组合约束。

Revision ID: 670b7ce006e1
Revises: 9308de41b8f0
Create Date: 2025-12-14 18:58:49.581406

"""

from collections.abc import Sequence

from alembic import op

# Alembic revision 标识。
revision: str = "670b7ce006e1"
down_revision: str | Sequence[str] | None = "9308de41b8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """向前升级数据库 schema。"""
    # 以下命令由 Alembic 自动生成。
    op.drop_index(op.f("ix_installations_github_installation_id"), table_name="installations")
    op.create_index(
        op.f("ix_installations_github_installation_id"),
        "installations",
        ["github_installation_id"],
        unique=False,
    )
    op.create_index(
        "ix_installations_github_installation_id_repository",
        "installations",
        ["github_installation_id", "repository"],
        unique=True,
    )
    # Alembic 自动生成命令结束。


def downgrade() -> None:
    """回退数据库 schema。"""
    # 以下命令由 Alembic 自动生成。
    op.drop_index("ix_installations_github_installation_id_repository", table_name="installations")
    op.drop_index(op.f("ix_installations_github_installation_id"), table_name="installations")
    op.create_index(
        op.f("ix_installations_github_installation_id"),
        "installations",
        ["github_installation_id"],
        unique=True,
    )
    # Alembic 自动生成命令结束。
