"""cwv problema audit_id column

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-27 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cwv_problema",
        sa.Column("audit_id", sa.String(80), nullable=True),
    )
    op.create_index(
        "ix_cwv_problema_audit_id",
        "cwv_problema",
        ["audit_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cwv_problema_audit_id", table_name="cwv_problema")
    op.drop_column("cwv_problema", "audit_id")
