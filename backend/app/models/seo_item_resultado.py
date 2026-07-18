"""Modelo: seo_item_resultado — 1 linha por item do checklist por auditoria.

evidencias_json segue contrato JSONB tipado (padrão SPEC_CWV_Contratos_JSONB_Tipados):
{"total_avaliadas": int, "total_afetadas": int, "amostra": [{...}], "truncada": bool}
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin

STATUS_ITEM = ("aprovado", "atencao", "reprovado", "na", "sem_dados")


class SeoItemResultado(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "seo_item_resultado"
    __table_args__ = (
        UniqueConstraint("auditoria_id", "item_slug", name="uq_seo_item_auditoria_slug"),
        CheckConstraint(
            "status_antes IS NULL OR status_antes IN "
            "('aprovado','atencao','reprovado','na','sem_dados')",
            name="seo_item_status_antes_check",
        ),
        CheckConstraint(
            "status_depois IS NULL OR status_depois IN "
            "('aprovado','atencao','reprovado','na','sem_dados')",
            name="seo_item_status_depois_check",
        ),
        CheckConstraint("modo IN ('auto','manual')", name="seo_item_modo_check"),
        Index("ix_seo_item_auditoria", "auditoria_id"),
    )

    auditoria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seo_auditoria.id", ondelete="CASCADE"), nullable=False,
    )
    item_slug: Mapped[str] = mapped_column(String(140), nullable=False)
    status_antes: Mapped[str | None] = mapped_column(String(15), nullable=True)
    status_depois: Mapped[str | None] = mapped_column(String(15), nullable=True)
    modo: Mapped[str] = mapped_column(String(10), nullable=False, server_default="auto")
    diagnostico: Mapped[str | None] = mapped_column(Text, nullable=True)
    recomendacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidencias_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status_cliente: Mapped[str | None] = mapped_column(Text, nullable=True)
    validacao_seo: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacao_cliente: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacao_seo: Mapped[str | None] = mapped_column(Text, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
