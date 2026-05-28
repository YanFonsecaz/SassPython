"""cwv metadata analise rasa

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-26 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cwv_analise", sa.Column("audits_totais", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cwv_analise", sa.Column("n_network_requests", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cwv_analise", sa.Column("main_document_size_bytes", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("cwv_analise", "main_document_size_bytes")
    op.drop_column("cwv_analise", "n_network_requests")
    op.drop_column("cwv_analise", "audits_totais")
