"""Modelo: cwv_problema_consolidado (SPEC_CWV_Consolidador_Cross_URL).

Problema consolidado de uma auditoria — agrupa problemas idênticos entre
URLs/estratégias, com causa raiz e escopo redigidos (fase LLM opcional).
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class CwvProblemaConsolidado(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cwv_problema_consolidado"
    __table_args__ = (
        CheckConstraint(
            "severidade BETWEEN 1 AND 5",
            name="cwv_consolidado_severidade_check",
        ),
        CheckConstraint(
            "esforco IS NULL OR esforco IN ('baixo', 'medio', 'alto')",
            name="cwv_consolidado_esforco_check",
        ),
        Index("ix_cwv_consolidado_auditoria", "auditoria_id", "prioridade_ordem"),
    )

    auditoria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cwv_auditoria.id", ondelete="CASCADE"), nullable=False,
    )
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    causa_raiz: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    kb_codigo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    audit_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")
    problemas_origem_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")
    evidencias_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    severidade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    prioridade_ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    esforco: Mapped[str | None] = mapped_column(String(10), nullable=True)
    metricas_afetadas: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")
    escopo_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    recomendacao_md: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
