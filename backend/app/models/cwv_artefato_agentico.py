"""Modelo: cwv_artefato_agentico (SPEC_CWV_Navegacao_Agentica_Geracao_IA).

Artefato gerado por IA para um item agêntico da auditoria: llms.txt ideal ou
scaffold WebMCP. Um vigente por (auditoria, tipo) — "Regenerar" faz upsert.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class CwvArtefatoAgentico(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cwv_artefato_agentico"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('llms_txt','webmcp')",
            name="cwv_artefato_agentico_tipo_check",
        ),
        # UNIQUE (auditoria_id, tipo) — 1 artefato vigente por tipo.
        Index("uq_cwv_artefato_agentico_aud_tipo", "auditoria_id", "tipo", unique=True),
    )

    auditoria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cwv_auditoria.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # 'llms_txt' | 'webmcp'
    diagnostico: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conteudo_md: Mapped[str] = mapped_column(Text, nullable=False)  # llms.txt OU código
    explicacao_md: Mapped[str | None] = mapped_column(Text, nullable=True)  # só WebMCP
    # ferramentas_sugeridas, justificativa, detectado, versao_spec, como_aplicar_md
    meta_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    modelo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    gerado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
