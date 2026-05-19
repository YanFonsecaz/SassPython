"""adicionar resumo e categoria em conteudos_vetores

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conteudos_vetores", sa.Column("resumo", sa.Text(), nullable=True))
    op.add_column("conteudos_vetores", sa.Column("categoria", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("conteudos_vetores", "categoria")
    op.drop_column("conteudos_vetores", "resumo")
