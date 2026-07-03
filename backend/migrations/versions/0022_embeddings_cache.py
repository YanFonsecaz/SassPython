"""create embeddings_cache table (L2 durável atrás do Redis)

SPEC_Inlinks_Cache_Duravel_Embeddings: o cache de embeddings já existe em Redis
(TTL 30d, chave emb:{provider}:{modelo}:{dims}:{sha256}), mas produção usa o
Key-Value free do Render (25MB) — evicção torna o cache efêmero e cada
re-execução paga API de novo. Esta migration cria a camada L2 em Postgres:
mesma chave do Redis como PK, embedding em VECTOR binário (~4KB vs ~13KB JSON),
 timestamps de criação e último uso (limpeza por uso).

É cache, não dado de domínio — sem FK com conteúdo.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "embeddings_cache",
        sa.Column("chave", sa.String(120), primary_key=True),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "usado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Limpeza por uso — job semanal filtra por usado_em.
    op.create_index("ix_embeddings_cache_usado_em", "embeddings_cache", ["usado_em"])


def downgrade() -> None:
    op.drop_index("ix_embeddings_cache_usado_em", table_name="embeddings_cache")
    op.drop_table("embeddings_cache")
