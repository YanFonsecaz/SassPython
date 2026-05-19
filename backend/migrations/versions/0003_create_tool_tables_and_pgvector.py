"""create tool tables + pgvector + indexes

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-22 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "pacotes_creditos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(50), unique=True, nullable=False),
        sa.Column("creditos", sa.Integer, nullable=False),
        sa.Column("preco", sa.Numeric(10, 2), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default="true"),
    )

    op.create_table(
        "clientes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("site_url", sa.String(500), nullable=True),
        sa.Column("config_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_clientes_usuario_id", "clientes", ["usuario_id"])

    op.create_table(
        "contas_creditos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), unique=True, nullable=False),
        sa.Column("saldo_plano", sa.Integer, nullable=False, server_default="0"),
        sa.Column("saldo_extras", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ciclo_inicio", sa.Date, nullable=False),
        sa.Column("ciclo_fim", sa.Date, nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "execucoes_ferramentas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("cliente_id", UUID(as_uuid=True), sa.ForeignKey("clientes.id"), nullable=True),
        sa.Column("ferramenta", sa.String(50), nullable=False),
        sa.Column("creditos_cobrados", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("etapa_atual", sa.String(50), nullable=True),
        sa.Column("entrada_json", JSONB, nullable=False),
        sa.Column("resultado_json", JSONB, nullable=True),
        sa.Column("erro_msg", sa.String(1000), nullable=True),
        sa.Column("tentativas_revisao", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tentativas_feedback", sa.Integer, nullable=False, server_default="0"),
        sa.Column("thread_id", sa.String(255), unique=True, nullable=False),
        sa.Column("job_id", sa.String(255), nullable=True),
        sa.Column("timeout_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_execucoes_usuario_id", "execucoes_ferramentas", ["usuario_id"])

    op.create_table(
        "transacoes_creditos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("conta_id", UUID(as_uuid=True), sa.ForeignKey("contas_creditos.id"), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("quantidade", sa.Integer, nullable=False),
        sa.Column("descricao", sa.String(500), nullable=False),
        sa.Column("ferramenta", sa.String(50), nullable=True),
        sa.Column("execucao_id", UUID(as_uuid=True), sa.ForeignKey("execucoes_ferramentas.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "versoes_artigo",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("execucao_id", UUID(as_uuid=True), sa.ForeignKey("execucoes_ferramentas.id"), nullable=False),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("origem", sa.String(30), nullable=False),
        sa.Column("conteudo_markdown", sa.Text, nullable=False),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("contagem_palavras", sa.Integer, nullable=False),
        sa.Column("score_revisao", sa.Float, nullable=True),
        sa.Column("feedback_recebido", sa.Text, nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_versoes_execucao_versao", "versoes_artigo", ["execucao_id", "versao"])

    op.create_table(
        "conteudos_vetores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("cliente_id", UUID(as_uuid=True), sa.ForeignKey("clientes.id"), nullable=True),
        sa.Column("execucao_id", UUID(as_uuid=True), sa.ForeignKey("execucoes_ferramentas.id"), nullable=True),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("conteudo", sa.Text, nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("intencao", sa.String(50), nullable=False),
        sa.Column("palavras_chave", JSONB, nullable=False, server_default="[]"),
        sa.Column("atividades", JSONB, nullable=False, server_default="[]"),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("score_base", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_conteudos_usuario_id", "conteudos_vetores", ["usuario_id"])
    op.create_index("idx_conteudos_cliente_id", "conteudos_vetores", ["cliente_id"])
    op.execute(
        "CREATE INDEX idx_conteudos_vetores_embedding "
        "ON conteudos_vetores USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 200)"
    )

    op.create_table(
        "pesquisas_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("query_original", sa.String(1000), nullable=False),
        sa.Column("resultados_json", JSONB, nullable=False),
        sa.Column("fonte", sa.String(30), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_pesquisas_cache_usuario_id", "pesquisas_cache", ["usuario_id"])
    op.create_unique_constraint("uq_pesquisas_cache_lookup", "pesquisas_cache", ["usuario_id", "query_hash", "fonte"])

    op.create_table(
        "compras",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("pacote_id", UUID(as_uuid=True), sa.ForeignKey("pacotes_creditos.id"), nullable=True),
        sa.Column("plano_id", UUID(as_uuid=True), sa.ForeignKey("planos.id"), nullable=True),
        sa.Column("valor_pago", sa.Numeric(10, 2), nullable=False),
        sa.Column("gateway_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("compras")
    op.drop_constraint("uq_pesquisas_cache_lookup", "pesquisas_cache", type_="unique")
    op.drop_index("idx_pesquisas_cache_usuario_id", table_name="pesquisas_cache")
    op.drop_table("pesquisas_cache")
    op.execute("DROP INDEX IF EXISTS idx_conteudos_vetores_embedding")
    op.drop_index("idx_conteudos_cliente_id", table_name="conteudos_vetores")
    op.drop_index("idx_conteudos_usuario_id", table_name="conteudos_vetores")
    op.drop_table("conteudos_vetores")
    op.drop_constraint("uq_versoes_execucao_versao", "versoes_artigo", type_="unique")
    op.drop_table("versoes_artigo")
    op.drop_table("transacoes_creditos")
    op.drop_index("idx_execucoes_usuario_id", table_name="execucoes_ferramentas")
    op.drop_table("execucoes_ferramentas")
    op.drop_table("contas_creditos")
    op.drop_index("idx_clientes_usuario_id", table_name="clientes")
    op.drop_table("clientes")
    op.drop_table("pacotes_creditos")
    op.execute("DROP EXTENSION IF EXISTS vector")
