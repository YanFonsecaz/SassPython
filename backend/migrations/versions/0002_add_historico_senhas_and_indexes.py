"""add historico_senhas table + indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-21 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "historico_senhas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_historico_senhas_usuario_id", "historico_senhas", ["usuario_id"])

    op.create_index("idx_reset_senha_tokens_usuario_id", "reset_senha_tokens", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("idx_reset_senha_tokens_usuario_id", table_name="reset_senha_tokens")
    op.drop_index("idx_historico_senhas_usuario_id", table_name="historico_senhas")
    op.drop_table("historico_senhas")
