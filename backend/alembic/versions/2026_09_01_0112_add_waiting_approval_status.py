"""add waiting approval status

Revision ID: 3b35e14144cf
Revises: c631417e35af
Create Date: 2026-09-01 01:12:41.640344

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b35e14144cf"
down_revision: str | Sequence[str] | None = "c631417e35af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TYPE agent_run_status_enum
        ADD VALUE IF NOT EXISTS 'WAITING_FOR_APPROVAL'
        """
    )

def downgrade() -> None:
    """Downgrade schema."""
