"""create cwv_problema_consolidado + add FK on cwv_checklist_item

SPEC_CWV_Consolidador_Cross_URL: tabela de problemas consolidados (dedup
cross-URL + causa raiz + escopo via LLM juiz). Adiciona também a FK pendente
de cwv_checklist_item.problema_consolidado_id (coluna criada sem FK na 0026).

Revision ID: 0028
Revises: 0026
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0028"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cwv_problema_consolidado",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "auditoria_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cwv_auditoria.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("causa_raiz", sa.Text(), nullable=False, server_default=""),
        sa.Column("kb_codigo", sa.String(80), nullable=True),
        sa.Column("audit_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("problemas_origem_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidencias_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("severidade", sa.SmallInteger(), nullable=False),
        sa.Column("prioridade_ordem", sa.Integer(), nullable=False),
        sa.Column("esforco", sa.String(10), nullable=True),
        sa.Column("metricas_afetadas", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("escopo_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("recomendacao_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_check_constraint("cwv_consolidado_severidade_check", "cwv_problema_consolidado", "severidade BETWEEN 1 AND 5")
    op.create_check_constraint("cwv_consolidado_esforco_check", "cwv_problema_consolidado", "esforco IS NULL OR esforco IN ('baixo', 'medio', 'alto')")
    op.create_index("ix_cwv_consolidado_auditoria", "cwv_problema_consolidado", ["auditoria_id", "prioridade_ordem"])

    # FK pendente desde a 0026 (coluna problema_consolidado_id sem FK).
    op.create_foreign_key(
        "fk_cwv_checklist_problema_consolidado",
        "cwv_checklist_item",
        "cwv_problema_consolidado",
        ["problema_consolidado_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_cwv_checklist_problema_consolidado", "cwv_checklist_item", type_="foreignkey")
    op.drop_index("ix_cwv_consolidado_auditoria", table_name="cwv_problema_consolidado")
    op.drop_constraint("cwv_consolidado_esforco_check", "cwv_problema_consolidado", type_="check")
    op.drop_constraint("cwv_consolidado_severidade_check", "cwv_problema_consolidado", type_="check")
    op.drop_table("cwv_problema_consolidado")
