"""cwv_artefato_agentico table

SPEC_CWV_Navegacao_Agentica_Geracao_IA: artefato gerado por IA (llms.txt ideal
ou scaffold WebMCP) por auditoria. UNIQUE (auditoria_id, tipo) — regenerar faz
upsert.

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cwv_artefato_agentico",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "auditoria_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cwv_auditoria.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("diagnostico", sa.String(20), nullable=True),
        sa.Column("conteudo_md", sa.Text(), nullable=False),
        sa.Column("explicacao_md", sa.Text(), nullable=True),
        sa.Column("meta_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("modelo", sa.String(60), nullable=True),
        sa.Column(
            "gerado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tipo IN ('llms_txt','webmcp')",
            name="cwv_artefato_agentico_tipo_check",
        ),
    )
    op.create_index(
        "uq_cwv_artefato_agentico_aud_tipo",
        "cwv_artefato_agentico",
        ["auditoria_id", "tipo"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_cwv_artefato_agentico_aud_tipo", table_name="cwv_artefato_agentico")
    op.drop_table("cwv_artefato_agentico")
