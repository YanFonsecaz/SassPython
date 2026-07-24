"""cwv_checklist_item: origem 'agentic' no check constraint

SPEC_CWV_Navegacao_Agentica: o grupo "Navegação agêntica" grava itens com
origem='agentic'; o constraint de 0026 só permitia
psi_audit/page_experience/field_data (bug capturado no e2e real — o INSERT do
checklist violava o check e derrubava a geração inteira, fail-open engolia).

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-17
"""
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_CONSTRAINT = "cwv_checklist_origem_check"
_TABELA = "cwv_checklist_item"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABELA, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABELA,
        "origem IN ('psi_audit','page_experience','field_data','agentic')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABELA, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABELA,
        "origem IN ('psi_audit','page_experience','field_data')",
    )
