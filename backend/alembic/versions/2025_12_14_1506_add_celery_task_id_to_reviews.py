"""为 reviews 表新增 celery_task_id。

Revision ID: 9308de41b8f0
Revises: e046b977f8a9
Create Date: 2025-12-14 15:06:13.077431

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Alembic revision 标识。
revision: str = "9308de41b8f0"
down_revision: str | Sequence[str] | None = "e046b977f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """向前升级数据库 schema。"""
    # 以下命令由 Alembic 自动生成。
    op.add_column(
        "reviews",
        sa.Column(
            "celery_task_id",
            sa.String(length=255),
            nullable=True,
            comment="Celery task ID for tracking",
        ),
    )
    op.create_index(op.f("ix_reviews_celery_task_id"), "reviews", ["celery_task_id"], unique=False)
    # Alembic 自动生成命令结束。


def downgrade() -> None:
    """回退数据库 schema。"""
    # 以下命令由 Alembic 自动生成。
    op.drop_index(op.f("ix_reviews_celery_task_id"), table_name="reviews")
    op.drop_column("reviews", "celery_task_id")
    # Alembic 自动生成命令结束。
