"""adicionar saldo_reservado e ultimo_codigo

P0-1.4: saldo_reservado em contas_creditos para reservas atomicas de creditos.
SPEC 02 2.5: ultimo_codigo em mfa_dispositivos para anti-replay TOTP.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-16
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contas_creditos",
        sa.Column("saldo_reservado", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("contas_creditos", "saldo_reservado", server_default=None)

    op.add_column(
        "mfa_dispositivos",
        sa.Column("ultimo_codigo", sa.String(length=6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mfa_dispositivos", "ultimo_codigo")
    op.drop_column("contas_creditos", "saldo_reservado")
