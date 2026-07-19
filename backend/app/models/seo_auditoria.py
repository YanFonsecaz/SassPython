"""Modelo: seo_auditoria (SPEC_Ferramenta_Auditoria_SEO_Tecnico §3.1)."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class SeoAuditoria(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "seo_auditoria"
    __table_args__ = (
        CheckConstraint(
            "fase IN ('before','implementacao','after','concluida')",
            name="seo_auditoria_fase_check",
        ),
        Index("ix_seo_auditoria_cliente", "cliente_id", text("criado_em DESC")),
        Index("ix_seo_auditoria_usuario", "usuario_id"),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False,
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False,
    )
    dominio: Mapped[str] = mapped_column(Text, nullable=False)
    fase: Mapped[str] = mapped_column(String(20), nullable=False, server_default="before")
    score_antes: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    score_depois: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    data_inicial: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_conclusao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
