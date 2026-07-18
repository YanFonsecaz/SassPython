"""seo_auditoria + seo_crawl + seo_item_resultado (Onda 1 SEOTEC)."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seo_auditoria",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("cliente_id", UUID(as_uuid=True), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("dominio", sa.Text(), nullable=False),
        sa.Column("fase", sa.String(20), nullable=False, server_default="before"),
        sa.Column("score_antes", sa.Numeric(5, 2), nullable=True),
        sa.Column("score_depois", sa.Numeric(5, 2), nullable=True),
        sa.Column("data_inicial", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_conclusao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "fase IN ('before','implementacao','after','concluida')",
            name="seo_auditoria_fase_check",
        ),
    )
    op.create_index("ix_seo_auditoria_cliente", "seo_auditoria", ["cliente_id", sa.text("criado_em DESC")])
    op.create_index("ix_seo_auditoria_usuario", "seo_auditoria", ["usuario_id"])

    op.create_table(
        "seo_crawl",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("auditoria_id", UUID(as_uuid=True), sa.ForeignKey("seo_auditoria.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execucao_id", UUID(as_uuid=True), sa.ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fase_destino", sa.String(10), nullable=False),
        sa.Column("origem", sa.String(10), nullable=False),
        sa.Column("sf_versao", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("contadores_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(15), nullable=False, server_default="recebido"),
        sa.Column("erro_msg", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("origem IN ('conector','upload')", name="seo_crawl_origem_check"),
        sa.CheckConstraint("fase_destino IN ('before','after')", name="seo_crawl_fase_check"),
        sa.CheckConstraint(
            "status IN ('recebido','processando','processado','parcial','erro')",
            name="seo_crawl_status_check",
        ),
    )
    op.create_index("ix_seo_crawl_auditoria", "seo_crawl", ["auditoria_id"])

    op.create_table(
        "seo_item_resultado",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("auditoria_id", UUID(as_uuid=True), sa.ForeignKey("seo_auditoria.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_slug", sa.String(140), nullable=False),
        sa.Column("status_antes", sa.String(15), nullable=True),
        sa.Column("status_depois", sa.String(15), nullable=True),
        sa.Column("modo", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("diagnostico", sa.Text(), nullable=True),
        sa.Column("recomendacao", sa.Text(), nullable=True),
        sa.Column("evidencias_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("status_cliente", sa.Text(), nullable=True),
        sa.Column("validacao_seo", sa.Text(), nullable=True),
        sa.Column("observacao_cliente", sa.Text(), nullable=True),
        sa.Column("observacao_seo", sa.Text(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("auditoria_id", "item_slug", name="uq_seo_item_auditoria_slug"),
        sa.CheckConstraint(
            "status_antes IS NULL OR status_antes IN ('aprovado','atencao','reprovado','na','sem_dados')",
            name="seo_item_status_antes_check",
        ),
        sa.CheckConstraint(
            "status_depois IS NULL OR status_depois IN ('aprovado','atencao','reprovado','na','sem_dados')",
            name="seo_item_status_depois_check",
        ),
        sa.CheckConstraint("modo IN ('auto','manual')", name="seo_item_modo_check"),
    )
    op.create_index("ix_seo_item_auditoria", "seo_item_resultado", ["auditoria_id"])


def downgrade() -> None:
    op.drop_table("seo_item_resultado")
    op.drop_table("seo_crawl")
    op.drop_table("seo_auditoria")
