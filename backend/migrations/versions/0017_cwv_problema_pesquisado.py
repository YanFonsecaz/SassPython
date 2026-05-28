"""cwv problema pesquisado flag

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-27 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cwv_problema",
        sa.Column(
            "pesquisado",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("cwv_problema", "pesquisado")
