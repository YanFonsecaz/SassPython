"""Modelo: cwv_audit_kb_cache (SPEC_CWV_Cache_Classificacao_Audit_KB).

Cache determinístico da classificação ``audit_id → kb_codigo``. O LLM
classifica cada audit_id UMA vez na vida; depois é lookup. Mata a divergência
mobile/desktop na raiz e corta a maior fatia de custo LLM do analisador.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CwvAuditKbCache(Base):
    __tablename__ = "cwv_audit_kb_cache"
    __table_args__ = (
        CheckConstraint(
            "origem IN ('llm', 'manual')",
            name="cwv_audit_kb_cache_origem_check",
        ),
    )

    audit_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    # null = classificado como "sem KB catalogada" (problema vira audit_id puro).
    kb_codigo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    origem: Mapped[str] = mapped_column(String(10), nullable=False)
    modelo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
