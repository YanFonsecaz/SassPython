"""inlinks performance history

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-09 21:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inlinks_historico_performance",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "usuario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url_destino", sa.Text(), nullable=False),
        sa.Column("evento", sa.String(30), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column(
            "execucao_id",
            UUID(as_uuid=True),
            sa.ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata_json", JSONB(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_perf_usuario_url",
        "inlinks_historico_performance",
        ["usuario_id", "url_destino"],
    )
    op.create_index(
        "idx_perf_evento",
        "inlinks_historico_performance",
        ["evento"],
    )
    op.create_index(
        "idx_perf_criado",
        "inlinks_historico_performance",
        ["criado_em"],
    )


def downgrade() -> None:
    op.drop_index("idx_perf_criado", table_name="inlinks_historico_performance")
    op.drop_index("idx_perf_evento", table_name="inlinks_historico_performance")
    op.drop_index("idx_perf_usuario_url", table_name="inlinks_historico_performance")
    op.drop_table("inlinks_historico_performance")
