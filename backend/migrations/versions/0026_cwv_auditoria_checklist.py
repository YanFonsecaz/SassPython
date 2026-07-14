"""create cwv_auditoria + cwv_checklist_item tables

SPEC_CWV_Auditoria_Ciclo_De_Vida: entidade "campanha" que amarra execuções CWV
num ciclo before → implementação → after com checklist colaborativo. Não altera
o fluxo de análise avulsa nem o billing.

Revision ID: 0026
Revises: 0027
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0026"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cwv_auditoria",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cliente_id", UUID(as_uuid=True), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("fase", sa.String(30), nullable=False, server_default="before"),
        sa.Column(
            "execucao_before_id",
            UUID(as_uuid=True),
            sa.ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "execucao_after_id",
            UUID(as_uuid=True),
            sa.ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("health_score_before", sa.Numeric(5, 2), nullable=True),
        sa.Column("health_score_after", sa.Numeric(5, 2), nullable=True),
        sa.Column("consolidacao_status", sa.String(20), nullable=False, server_default="nao_executada"),
        sa.Column("relatorio_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_check_constraint("cwv_auditoria_fase_check", "cwv_auditoria", "fase IN ('before','aguardando_implementacao','after','concluida')")
    op.create_check_constraint("cwv_auditoria_consolidacao_check", "cwv_auditoria", "consolidacao_status IN ('nao_executada','executando','concluida','falhou')")
    op.create_index("ix_cwv_auditoria_cliente", "cwv_auditoria", ["cliente_id", sa.text("criado_em DESC")])
    op.create_index("ix_cwv_auditoria_usuario", "cwv_auditoria", ["usuario_id"])

    op.create_table(
        "cwv_checklist_item",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "auditoria_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cwv_auditoria.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("item_codigo", sa.String(120), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("status_before", sa.String(10), nullable=False),
        sa.Column("status_after", sa.String(10), nullable=True),
        sa.Column("status_implementacao", sa.String(20), nullable=False, server_default="nao_executado"),
        sa.Column("nota_cliente", sa.Text(), nullable=True),
        sa.Column("nota_seo", sa.Text(), nullable=True),
        sa.Column("prioridade", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("esforco", sa.String(10), nullable=True),
        sa.Column("escopo_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("problema_consolidado_id", UUID(as_uuid=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_check_constraint("cwv_checklist_origem_check", "cwv_checklist_item", "origem IN ('psi_audit','page_experience','field_data')")
    op.create_check_constraint("cwv_checklist_status_before_check", "cwv_checklist_item", "status_before IN ('pass','fail','na')")
    op.create_check_constraint("cwv_checklist_status_after_check", "cwv_checklist_item", "status_after IS NULL OR status_after IN ('pass','fail','na')")
    op.create_check_constraint("cwv_checklist_status_impl_check", "cwv_checklist_item", "status_implementacao IN ('nao_executado','em_andamento','implementado')")
    op.create_unique_constraint("uq_cwv_checklist_auditoria_codigo", "cwv_checklist_item", ["auditoria_id", "item_codigo"])
    op.create_index("ix_cwv_checklist_auditoria", "cwv_checklist_item", ["auditoria_id", "prioridade"])


def downgrade() -> None:
    op.drop_index("ix_cwv_checklist_auditoria", table_name="cwv_checklist_item")
    op.drop_constraint("uq_cwv_checklist_auditoria_codigo", "cwv_checklist_item", type_="unique")
    op.drop_table("cwv_checklist_item")
    op.drop_index("ix_cwv_auditoria_usuario", table_name="cwv_auditoria")
    op.drop_index("ix_cwv_auditoria_cliente", table_name="cwv_auditoria")
    op.drop_constraint("cwv_auditoria_consolidacao_check", "cwv_auditoria", type_="check")
    op.drop_constraint("cwv_auditoria_fase_check", "cwv_auditoria", type_="check")
    op.drop_table("cwv_auditoria")
