"""cwv_audit_kb_cache table

SPEC_CWV_Cache_Classificacao_Audit_KB: cache determinístico da classificação
``audit_id → kb_codigo`` para eliminar chamadas LLM redundantes e o
não-determinismo mobile/desktop do bug ``outros``.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cwv_audit_kb_cache",
        sa.Column("audit_id", sa.String(120), primary_key=True, nullable=False),
        sa.Column("kb_codigo", sa.String(80), nullable=True),
        sa.Column("origem", sa.String(10), nullable=False),
        sa.Column("modelo", sa.String(60), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "origem IN ('llm', 'manual')",
            name="cwv_audit_kb_cache_origem_check",
        ),
        comment="Cache determinístico audit_id -> kb_codigo (SPEC_CWV_Cache_Classificacao_Audit_KB).",
    )


def downgrade() -> None:
    op.drop_table("cwv_audit_kb_cache")
