"""widen parecer.plataforma to TEXT

A plataforma inferida pela IA pode passar de 60 caracteres
(ex.: "Nao especificada (possivelmente e-commerce customizado...)").

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("parecer", "plataforma", type_=sa.Text(), existing_type=sa.String(60), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("parecer", "plataforma", type_=sa.String(60), existing_type=sa.Text(), existing_nullable=True)
