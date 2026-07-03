"""create indices_site + (cliente_id, tipo_recurso) index on conteudos_vetores

SPEC_Inlinks_Descoberta_Automatica_Candidatas: índice do site por cliente.
- nova tabela indices_site (um registro por cliente, status da indexação);
- índice composto (cliente_id, tipo_recurso) em conteudos_vetores para a busca
  vetorial escopada por cliente (descoberta: tipo_recurso='pagina_site').

A coluna cliente_id e tipo_recurso já existem em conteudos_vetores (migrations
0003 e 0005) — só falta o índice composto para a consulta multi-tenant.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Índice composto para a busca vetorial escopada por cliente na descoberta.
    op.create_index(
        "ix_conteudos_vetores_cliente_tipo",
        "conteudos_vetores",
        ["cliente_id", "tipo_recurso"],
    )

    op.create_table(
        "indices_site",
        sa.Column("cliente_id", UUID(as_uuid=True), sa.ForeignKey("clientes.id"), primary_key=True),
        sa.Column("dominio", sa.String(255), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="indexando"),
        sa.Column("n_paginas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("n_falhas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("erro_msg", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("indices_site")
    op.drop_index("ix_conteudos_vetores_cliente_tipo", table_name="conteudos_vetores")
