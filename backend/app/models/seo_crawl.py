"""Modelo: seo_crawl — 1 linha por ingestão de pacote (conector ou upload)."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class SeoCrawl(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "seo_crawl"
    __table_args__ = (
        CheckConstraint("origem IN ('conector','upload')", name="seo_crawl_origem_check"),
        CheckConstraint("fase_destino IN ('before','after')", name="seo_crawl_fase_check"),
        CheckConstraint(
            "status IN ('recebido','processando','processado','parcial','erro')",
            name="seo_crawl_status_check",
        ),
        Index("ix_seo_crawl_auditoria", "auditoria_id"),
    )

    auditoria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seo_auditoria.id", ondelete="CASCADE"), nullable=False,
    )
    execucao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"),
        nullable=True,
    )
    fase_destino: Mapped[str] = mapped_column(String(10), nullable=False)
    origem: Mapped[str] = mapped_column(String(10), nullable=False)
    sf_versao: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    contadores_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(15), nullable=False, server_default="recebido")
    erro_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
