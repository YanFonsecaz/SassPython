"""inlinks contexto e justificativa

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-10 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("inlinks_sugeridos", sa.Column("trecho_contexto", sa.Text(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("titulo_destino", sa.Text(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("motivo_contexto", sa.Text(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("categoria_match", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("inlinks_sugeridos", "categoria_match")
    op.drop_column("inlinks_sugeridos", "motivo_contexto")
    op.drop_column("inlinks_sugeridos", "titulo_destino")
    op.drop_column("inlinks_sugeridos", "trecho_contexto")
