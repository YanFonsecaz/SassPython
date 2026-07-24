"""Modelo: cwv_checklist_item (SPEC_CWV_Auditoria_Ciclo_De_Vida).

Um item do checklist da auditoria — pode ser um problema PSI (fail/pass),
um item de field data (crux_*) ou um item de page experience (pe_*).
Snapshot no momento da criação da auditoria (estável enquanto o cliente trabalha).
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class CwvChecklistItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cwv_checklist_item"
    __table_args__ = (
        CheckConstraint(
            # SPEC_CWV_Navegacao_Agentica: 'agentic' (migração 0034).
            "origem IN ('psi_audit','page_experience','field_data','agentic')",
            name="cwv_checklist_origem_check",
        ),
        CheckConstraint(
            "status_before IN ('pass','fail','na')",
            name="cwv_checklist_status_before_check",
        ),
        CheckConstraint(
            "status_after IS NULL OR status_after IN ('pass','fail','na')",
            name="cwv_checklist_status_after_check",
        ),
        CheckConstraint(
            "status_implementacao IN ('nao_executado','em_andamento','implementado')",
            name="cwv_checklist_status_impl_check",
        ),
        UniqueConstraint("auditoria_id", "item_codigo", name="uq_cwv_checklist_auditoria_codigo"),
        Index("ix_cwv_checklist_auditoria", "auditoria_id", "prioridade"),
    )

    auditoria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cwv_auditoria.id", ondelete="CASCADE"), nullable=False,
    )
    origem: Mapped[str] = mapped_column(String(20), nullable=False)
    item_codigo: Mapped[str] = mapped_column(String(120), nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    status_before: Mapped[str] = mapped_column(String(10), nullable=False)
    status_after: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status_implementacao: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="nao_executado",
    )
    nota_cliente: Mapped[str | None] = mapped_column(Text, nullable=True)
    nota_seo: Mapped[str | None] = mapped_column(Text, nullable=True)
    prioridade: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    esforco: Mapped[str | None] = mapped_column(String(10), nullable=True)
    escopo_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    metricas_afetadas: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    # Sem FK aqui — a FK chega na migração da S8 (Consolidador_Cross_URL).
    problema_consolidado_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
