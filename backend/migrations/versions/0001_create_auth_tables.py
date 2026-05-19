"""create auth tables

Revision ID: 0001
Revises:
Create Date: 2026-04-20 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "planos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(50), unique=True, nullable=False),
        sa.Column("creditos_por_mes", sa.Integer, nullable=False),
        sa.Column("preco_mensal", sa.Numeric(10, 2), nullable=False),
        sa.Column("cliente_limite", sa.Integer, nullable=False),
        sa.Column("permite_extras", sa.Boolean, nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default="true"),
    )
    op.execute("""
        INSERT INTO planos (id, nome, creditos_por_mes, preco_mensal, cliente_limite, permite_extras)
        VALUES
            (gen_random_uuid(), 'free', 50, 0.00, 3, false),
            (gen_random_uuid(), 'pro', 500, 97.00, 15, true),
            (gen_random_uuid(), 'business', 2000, 247.00, -1, true)
    """)

    op.create_table(
        "usuarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("email_verificado", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("plano_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("planos.id"), nullable=True),
        sa.Column("mfa_ativo", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_usuarios_email", "usuarios", ["email"])

    op.create_table(
        "sessoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revogada", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_sessoes_token_hash", "sessoes", ["token_hash"])
    op.create_index("idx_sessoes_usuario_id", "sessoes", ["usuario_id"])

    op.create_table(
        "mfa_dispositivos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("segredo_totp", sa.String(255), nullable=True),
        sa.Column("credential_id", sa.LargeBinary, nullable=True),
        sa.Column("public_key", sa.LargeBinary, nullable=True),
        sa.Column("counter", sa.Integer, nullable=True),
        sa.Column("ultimo_uso", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_mfa_usuario_id", "mfa_dispositivos", ["usuario_id"])

    op.create_table(
        "reset_senha_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("usado", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reset_senha_tokens")
    op.drop_table("mfa_dispositivos")
    op.drop_table("sessoes")
    op.drop_table("usuarios")
    op.drop_table("planos")
