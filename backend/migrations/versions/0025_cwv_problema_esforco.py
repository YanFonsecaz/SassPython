"""add esforco column to cwv_problema

SPEC_CWV_Estimador_Esforco: classifica o esforço de implementação de cada
problema em baixo/medio/alto (determinístico, por kb_codigo com fallback de
família de audit_id). Coluna nullable — problemas antigos ficam NULL.

Revision ID: 0025
Revises: 0023
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cwv_problema",
        sa.Column("esforco", sa.String(10), nullable=True),
    )
    op.create_check_constraint(
        "cwv_problema_esforco_check",
        "cwv_problema",
        "esforco IS NULL OR esforco IN ('baixo', 'medio', 'alto')",
    )


def downgrade() -> None:
    op.drop_constraint("cwv_problema_esforco_check", "cwv_problema", type_="check")
    op.drop_column("cwv_problema", "esforco")
