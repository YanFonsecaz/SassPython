"""checklist: metricas_afetadas column

SPEC_CWV_Checklist_Metric_Impact: add metricas_afetadas JSONB to cwv_checklist_item
for metric badges + filtering in the grid.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cwv_checklist_item",
        sa.Column(
            "metricas_afetadas",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("cwv_checklist_item", "metricas_afetadas")
