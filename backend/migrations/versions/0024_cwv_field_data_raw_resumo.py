"""add field data CrUX + raw_resumo_json to cwv_analise

SPEC_CWV_Field_Data_Retencao_Payload: materializa o field data CrUX
(loadingExperience/originLoadingExperience do payload PSI) em colunas para
exibição e query, e adiciona raw_resumo_json (resumo compacto ≤64KB, sem
screenshots/details.items) que habilita specs futuras (checklist Pass/Fail
completo precisa do score de TODOS os audits, não só dos falhos).

Todas as colunas são nullable (com server_default onde NOT NULL) — análises
antigas e execuções falhas ficam com defaults, sem backfill.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cwv_analise",
        sa.Column("raw_resumo_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("cwv_analise", sa.Column("crux_lcp_p75_ms", sa.Numeric(10, 2), nullable=True))
    op.add_column("cwv_analise", sa.Column("crux_inp_p75_ms", sa.Numeric(10, 2), nullable=True))
    op.add_column("cwv_analise", sa.Column("crux_cls_p75", sa.Numeric(6, 4), nullable=True))
    op.add_column("cwv_analise", sa.Column("crux_lcp_categoria", sa.String(20), nullable=True))
    op.add_column("cwv_analise", sa.Column("crux_inp_categoria", sa.String(20), nullable=True))
    op.add_column("cwv_analise", sa.Column("crux_cls_categoria", sa.String(20), nullable=True))
    op.add_column("cwv_analise", sa.Column("crux_overall_categoria", sa.String(20), nullable=True))
    op.add_column(
        "cwv_analise",
        sa.Column("crux_origem_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("cwv_analise", "crux_origem_fallback")
    op.drop_column("cwv_analise", "crux_overall_categoria")
    op.drop_column("cwv_analise", "crux_cls_categoria")
    op.drop_column("cwv_analise", "crux_inp_categoria")
    op.drop_column("cwv_analise", "crux_lcp_categoria")
    op.drop_column("cwv_analise", "crux_cls_p75")
    op.drop_column("cwv_analise", "crux_inp_p75_ms")
    op.drop_column("cwv_analise", "crux_lcp_p75_ms")
    op.drop_column("cwv_analise", "raw_resumo_json")
