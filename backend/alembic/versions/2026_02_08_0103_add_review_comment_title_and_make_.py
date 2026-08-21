"""新增 ReviewComment title，并将 github_comment_id 改为 bigint。

Revision ID: 113096f34455
Revises: 670b7ce006e1
Create Date: 2026-02-08 01:03:27.916621

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Alembic revision 标识。
revision: str = "113096f34455"
down_revision: str | Sequence[str] | None = "670b7ce006e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """向前升级数据库 schema。"""
    # 以下命令由 Alembic 自动生成。
    op.add_column(
        "review_comments",
        sa.Column("title", sa.String(length=255), nullable=True, comment="Short finding title"),
    )
    op.alter_column(
        "review_comments",
        "github_comment_id",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        comment="GitHub API comment ID (bigint)",
        existing_comment="GitHub API comment ID",
        existing_nullable=True,
    )
    # Alembic 自动生成命令结束。


def downgrade() -> None:
    """回退数据库 schema。"""
    # 以下命令由 Alembic 自动生成。
    op.alter_column(
        "review_comments",
        "github_comment_id",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        comment="GitHub API comment ID",
        existing_comment="GitHub API comment ID (bigint)",
        existing_nullable=True,
    )
    op.drop_column("review_comments", "title")
    # Alembic 自动生成命令结束。
