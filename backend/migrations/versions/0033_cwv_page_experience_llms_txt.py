"""cwv_page_experience.llms_txt column

SPEC_CWV_Navegacao_Agentica: veredito do check llms.txt por origem
(pass/fail/erro/na), no mesmo padrão dos demais checks de Page Experience.

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cwv_page_experience",
        sa.Column("llms_txt", sa.String(10), nullable=False, server_default="na"),
    )
    op.create_check_constraint(
        "cwv_page_experience_llms_txt_check",
        "cwv_page_experience",
        "llms_txt IN ('pass','fail','erro','na')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "cwv_page_experience_llms_txt_check",
        "cwv_page_experience",
        type_="check",
    )
    op.drop_column("cwv_page_experience", "llms_txt")
