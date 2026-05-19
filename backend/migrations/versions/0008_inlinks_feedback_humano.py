"""inlinks feedback humano + conectores

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("inlinks_sugeridos", sa.Column("status_humano", sa.String(20), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("motivo_humano", sa.Text(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("revisado_humano_em", sa.DateTime(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("trecho_original", sa.Text(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("conector_antes", sa.String(80), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("conector_depois", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("inlinks_sugeridos", "conector_depois")
    op.drop_column("inlinks_sugeridos", "conector_antes")
    op.drop_column("inlinks_sugeridos", "trecho_original")
    op.drop_column("inlinks_sugeridos", "revisado_humano_em")
    op.drop_column("inlinks_sugeridos", "motivo_humano")
    op.drop_column("inlinks_sugeridos", "status_humano")
