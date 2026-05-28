"""cwv analise e problemas

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-25 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cwv_analise",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("execucao_id", UUID(as_uuid=True), sa.ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cliente_id", UUID(as_uuid=True), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_canonica", sa.Text(), nullable=False),
        sa.Column("template_tipo", sa.String(20), nullable=False),
        sa.Column("estrategia", sa.String(10), nullable=False, server_default="mobile"),
        sa.Column("plataforma_detectada", sa.String(20), nullable=False, server_default="desconhecida"),
        sa.Column("score_performance", sa.Integer(), nullable=True),
        sa.Column("lcp_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("cls", sa.Numeric(6, 4), nullable=True),
        sa.Column("inp_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("fcp_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("ttfb_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("tbt_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("raw_psi_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("erro_msg", sa.String(500), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_check_constraint(
        "cwv_analise_template_check",
        "cwv_analise",
        "template_tipo IN ('home','categoria','produto','blog','blogpost','outros')",
    )
    op.create_check_constraint(
        "cwv_analise_estrategia_check",
        "cwv_analise",
        "estrategia IN ('mobile','desktop')",
    )
    op.create_index("ix_cwv_analise_cliente_url_data", "cwv_analise", ["cliente_id", "url_canonica", sa.text("criado_em DESC")])
    op.create_index("ix_cwv_analise_execucao", "cwv_analise", ["execucao_id"])
    op.create_index("ix_cwv_analise_usuario", "cwv_analise", ["usuario_id"])

    op.create_table(
        "cwv_problema",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analise_id", UUID(as_uuid=True), sa.ForeignKey("cwv_analise.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kb_codigo", sa.String(80), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("severidade", sa.SmallInteger(), nullable=False),
        sa.Column("prioridade_ordem", sa.Integer(), nullable=False),
        sa.Column("metricas_afetadas", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("contexto_especifico", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("documentacao_md", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_check_constraint(
        "cwv_problema_severidade_check",
        "cwv_problema",
        "severidade BETWEEN 1 AND 5",
    )
    op.create_index("ix_cwv_problema_analise", "cwv_problema", ["analise_id", "prioridade_ordem"])


def downgrade() -> None:
    op.drop_table("cwv_problema")
    op.drop_table("cwv_analise")
