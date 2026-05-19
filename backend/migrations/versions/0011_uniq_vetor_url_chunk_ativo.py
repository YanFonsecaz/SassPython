"""tornar uniq_vetor_url_chunk condicional em ativo=true

Permite re-inserir vetor para a mesma (usuario_id, url_canonica, chunk_index)
quando o registro antigo foi desativado (ativo=false). Necessário para
re-extração via Enriquecedor melhorado.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-14
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uniq_vetor_url_chunk", table_name="conteudos_vetores")
    op.create_index(
        "uniq_vetor_url_chunk",
        "conteudos_vetores",
        ["usuario_id", "url_canonica", "chunk_index"],
        unique=True,
        postgresql_where="url_canonica IS NOT NULL AND ativo = true",
    )


def downgrade() -> None:
    op.drop_index("uniq_vetor_url_chunk", table_name="conteudos_vetores")
    op.create_index(
        "uniq_vetor_url_chunk",
        "conteudos_vetores",
        ["usuario_id", "url_canonica", "chunk_index"],
        unique=True,
        postgresql_where="url_canonica IS NOT NULL",
    )
