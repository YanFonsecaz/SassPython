"""create parecer table

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parecer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("execucao_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cliente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("subtitulo", sa.Text(), nullable=True),
        sa.Column("site", sa.Text(), nullable=True),
        sa.Column("plataforma", sa.String(60), nullable=True),
        sa.Column("cliente_nome", sa.Text(), nullable=False),
        sa.Column("meta_json", postgresql.JSONB(), nullable=False),
        sa.Column("estrutura_json", postgresql.JSONB(), nullable=False),
        sa.Column("parecer_html", sa.Text(), nullable=False),
        sa.Column("n_imagens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("modelo", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="concluido"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_parecer_usuario_cliente_data", "parecer", ["usuario_id", "cliente_id", "criado_em"])
    op.create_index("ix_parecer_execucao", "parecer", ["execucao_id"])
    op.create_index("ix_parecer_usuario_id", "parecer", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_parecer_usuario_id")
    op.drop_index("ix_parecer_execucao", table_name="parecer")
    op.drop_index("ix_parecer_usuario_cliente_data", table_name="parecer")
    op.drop_table("parecer")
