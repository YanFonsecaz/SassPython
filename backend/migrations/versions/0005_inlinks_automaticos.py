"""inlinks automaticos

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-09 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conteudos_vetores", sa.Column("url_canonica", sa.Text(), nullable=True))
    op.add_column("conteudos_vetores", sa.Column("chunk_index", sa.Integer(), nullable=True))
    op.add_column("conteudos_vetores", sa.Column("tipo_recurso", sa.String(20), nullable=True))
    op.add_column("conteudos_vetores", sa.Column("html_hash", sa.String(64), nullable=True))
    op.add_column("conteudos_vetores", sa.Column("tokens", sa.Integer(), nullable=True))

    op.execute(
        "CREATE UNIQUE INDEX uniq_vetor_url_chunk ON conteudos_vetores (usuario_id, url_canonica, chunk_index) "
        "WHERE url_canonica IS NOT NULL"
    )

    op.create_table(
        "inlinks_sugeridos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("execucao_id", UUID(as_uuid=True), sa.ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url_origem", sa.Text(), nullable=False),
        sa.Column("url_destino", sa.Text(), nullable=False),
        sa.Column("anchor_text", sa.Text(), nullable=False),
        sa.Column("paragrafo_idx", sa.Integer(), nullable=False),
        sa.Column("offset_chars", sa.Integer(), nullable=False),
        sa.Column("score_total", sa.Float(), nullable=False),
        sa.Column("score_semantico", sa.Float(), nullable=False),
        sa.Column("score_contexto", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="aplicado"),
        sa.Column("motivo_rejeicao", sa.Text(), nullable=True),
        sa.Column("rel_attr", sa.String(50), nullable=False, server_default="noopener"),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_inlinks_execucao", "inlinks_sugeridos", ["execucao_id"])


def downgrade() -> None:
    op.drop_index("idx_inlinks_execucao")
    op.drop_table("inlinks_sugeridos")
    op.execute("DROP INDEX IF EXISTS uniq_vetor_url_chunk")
    op.drop_column("conteudos_vetores", "tokens")
    op.drop_column("conteudos_vetores", "html_hash")
    op.drop_column("conteudos_vetores", "tipo_recurso")
    op.drop_column("conteudos_vetores", "chunk_index")
    op.drop_column("conteudos_vetores", "url_canonica")
