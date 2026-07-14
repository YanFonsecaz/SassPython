"""create cwv_page_experience table

SPEC_CWV_Page_Experience: armazena as checagens de Page Experience (HTTPS,
SSL, redirect 301, security headers, Safe Browsing, mixed content,
mobile-friendly) por origem (scheme://host) por execução. UNIQUE
(execucao_id, origem) — uma linha por domínio por execução.

Revision ID: 0027
Revises: 0025
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0027"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cwv_page_experience",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "execucao_id",
            UUID(as_uuid=True),
            sa.ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("https", sa.String(10), nullable=False, server_default="na"),
        sa.Column("ssl", sa.String(10), nullable=False, server_default="na"),
        sa.Column("redirect_301", sa.String(10), nullable=False, server_default="na"),
        sa.Column("security_headers", sa.String(10), nullable=False, server_default="na"),
        sa.Column("safe_browsing", sa.String(10), nullable=False, server_default="na"),
        sa.Column("mixed_content", sa.String(10), nullable=False, server_default="na"),
        sa.Column("mobile_friendly", sa.String(10), nullable=False, server_default="na"),
        sa.Column("detalhes_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_check_constraint("cwv_page_experience_https_check", "cwv_page_experience", "https IN ('pass','fail','erro','na')")
    op.create_check_constraint("cwv_page_experience_ssl_check", "cwv_page_experience", "ssl IN ('pass','fail','erro','na')")
    op.create_check_constraint("cwv_page_experience_redirect_check", "cwv_page_experience", "redirect_301 IN ('pass','fail','erro','na')")
    op.create_check_constraint("cwv_page_experience_headers_check", "cwv_page_experience", "security_headers IN ('pass','fail','erro','na')")
    op.create_check_constraint("cwv_page_experience_safe_check", "cwv_page_experience", "safe_browsing IN ('pass','fail','erro','na')")
    op.create_check_constraint("cwv_page_experience_mixed_check", "cwv_page_experience", "mixed_content IN ('pass','fail','erro','na')")
    op.create_check_constraint("cwv_page_experience_mobile_check", "cwv_page_experience", "mobile_friendly IN ('pass','fail','erro','na')")
    op.create_index("uq_cwv_page_experience_exec_origem", "cwv_page_experience", ["execucao_id", "origem"], unique=True)
    op.create_index("ix_cwv_page_experience_execucao", "cwv_page_experience", ["execucao_id"])


def downgrade() -> None:
    op.drop_index("ix_cwv_page_experience_execucao", table_name="cwv_page_experience")
    op.drop_index("uq_cwv_page_experience_exec_origem", table_name="cwv_page_experience")
    op.drop_table("cwv_page_experience")
