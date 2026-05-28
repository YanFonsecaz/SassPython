"""cwv llm observability

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-26 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cwv_analise",
        sa.Column("llm_usado", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "cwv_analise",
        sa.Column("llm_audits_processados", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cwv_analise",
        sa.Column("llm_audits_descartados", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("cwv_analise", "llm_audits_descartados")
    op.drop_column("cwv_analise", "llm_audits_processados")
    op.drop_column("cwv_analise", "llm_usado")
