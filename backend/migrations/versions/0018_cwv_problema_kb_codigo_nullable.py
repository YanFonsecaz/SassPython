"""cwv problema kb_codigo nullable

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-27 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("cwv_problema", "kb_codigo", nullable=True)


def downgrade() -> None:
    op.execute("UPDATE cwv_problema SET kb_codigo='outros' WHERE kb_codigo IS NULL")
    op.alter_column("cwv_problema", "kb_codigo", nullable=False)
