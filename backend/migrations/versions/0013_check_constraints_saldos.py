"""CHECK constraints on saldo columns

SPEC 03 §3.1: Defesa em profundidade - garantir saldos nunca negativos.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-16
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "chk_saldo_plano_nao_negativo",
        "contas_creditos",
        "saldo_plano >= 0",
    )
    op.create_check_constraint(
        "chk_saldo_extras_nao_negativo",
        "contas_creditos",
        "saldo_extras >= 0",
    )
    op.create_check_constraint(
        "chk_saldo_reservado_nao_negativo",
        "contas_creditos",
        "saldo_reservado >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("chk_saldo_reservado_nao_negativo", "contas_creditos", type_="check")
    op.drop_constraint("chk_saldo_extras_nao_negativo", "contas_creditos", type_="check")
    op.drop_constraint("chk_saldo_plano_nao_negativo", "contas_creditos", type_="check")
