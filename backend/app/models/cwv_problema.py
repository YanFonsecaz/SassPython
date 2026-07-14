import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class CwvProblema(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cwv_problema"
    __table_args__ = (
        CheckConstraint(
            "severidade BETWEEN 1 AND 5",
            name="cwv_problema_severidade_check",
        ),
        CheckConstraint(
            "esforco IS NULL OR esforco IN ('baixo', 'medio', 'alto')",
            name="cwv_problema_esforco_check",
        ),
        Index("ix_cwv_problema_analise", "analise_id", "prioridade_ordem"),
        Index("ix_cwv_problema_audit_id", "audit_id"),
    )

    analise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cwv_analise.id", ondelete="CASCADE"), nullable=False,
    )
    kb_codigo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    audit_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    severidade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    prioridade_ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    metricas_afetadas: Mapped[dict] = mapped_column(JSONB, nullable=False)
    contexto_especifico: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    documentacao_md: Mapped[str] = mapped_column(Text, nullable=False)
    pesquisado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    esforco: Mapped[str | None] = mapped_column(String(10), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False,
    )
