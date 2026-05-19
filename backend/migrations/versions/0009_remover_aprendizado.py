"""remover sistema de aprendizado/penalizacao

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("inlinks_historico_performance")
    op.drop_column("inlinks_sugeridos", "status_humano")
    op.drop_column("inlinks_sugeridos", "motivo_humano")
    op.drop_column("inlinks_sugeridos", "revisado_humano_em")


def downgrade() -> None:
    op.add_column(
        "inlinks_sugeridos",
        sa.Column("status_humano", sa.String(20), nullable=True),
    )
    op.add_column(
        "inlinks_sugeridos",
        sa.Column("motivo_humano", sa.Text(), nullable=True),
    )
    op.add_column(
        "inlinks_sugeridos",
        sa.Column("revisado_humano_em", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "inlinks_historico_performance",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "usuario_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url_destino", sa.Text, nullable=False),
        sa.Column("evento", sa.String(30), nullable=False),
        sa.Column("motivo", sa.Text, nullable=True),
        sa.Column(
            "execucao_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
