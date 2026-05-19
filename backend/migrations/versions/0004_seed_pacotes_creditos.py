"""seed pacotes creditos

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-22 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO pacotes_creditos (id, nome, creditos, preco, ativo)
        VALUES
            (gen_random_uuid(), 'starter', 100, 27.00, true),
            (gen_random_uuid(), 'pro_500', 500, 97.00, true),
            (gen_random_uuid(), 'business_2000', 2000, 347.00, true),
            (gen_random_uuid(), 'enterprise_5000', 5000, 697.00, true)
        ON CONFLICT (nome) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM pacotes_creditos WHERE nome IN ('starter', 'pro_500', 'business_2000', 'enterprise_5000')")
