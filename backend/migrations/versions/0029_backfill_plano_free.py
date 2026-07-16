"""backfill: assign plano free to users without plano_id + grant monthly credits

SPEC_Onboarding_Plano_Free: existing users without plano_id get the free plan,
and their credit accounts with saldo_plano=0 get the monthly credits with a
fresh 30-day cycle.

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Assign free plan to users without plano_id (idempotent).
    op.execute(
        """
        UPDATE usuarios SET plano_id = (SELECT id FROM planos WHERE nome = 'free' LIMIT 1)
        WHERE plano_id IS NULL
        """
    )
    # Grant monthly credits to free-plan users with saldo_plano = 0.
    op.execute(
        """
        UPDATE contas_creditos c SET saldo_plano = p.creditos_por_mes,
               ciclo_inicio = CURRENT_DATE, ciclo_fim = CURRENT_DATE + INTERVAL '30 days'
        FROM usuarios u JOIN planos p ON p.id = u.plano_id
        WHERE c.usuario_id = u.id AND c.saldo_plano = 0 AND p.nome = 'free'
        """
    )


def downgrade() -> None:
    # No-op: cannot distinguish which users had a plan before the backfill.
    pass
