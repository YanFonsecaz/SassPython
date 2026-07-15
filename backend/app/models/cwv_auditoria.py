"""Modelo: cwv_auditoria (SPEC_CWV_Auditoria_Ciclo_De_Vida).

Entidade "campanha" que amarra execuções CWV existentes num ciclo
before → implementação → after com checklist colaborativo. Não altera nada
no fluxo de análise avulsa nem no billing.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class CwvAuditoria(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cwv_auditoria"
    __table_args__ = (
        CheckConstraint(
            "fase IN ('before','aguardando_implementacao','after','concluida')",
            name="cwv_auditoria_fase_check",
        ),
        CheckConstraint(
            "consolidacao_status IN ('nao_executada','executando','concluida','falhou')",
            name="cwv_auditoria_consolidacao_check",
        ),
        Index("ix_cwv_auditoria_cliente", "cliente_id", text("criado_em DESC")),
        Index("ix_cwv_auditoria_usuario", "usuario_id"),
    )

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False,
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False,
    )
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    fase: Mapped[str] = mapped_column(String(30), nullable=False, server_default="before")
    execucao_before_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"),
        nullable=True,
    )
    execucao_after_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"),
        nullable=True,
    )
    health_score_before: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    health_score_after: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    consolidacao_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="nao_executada",
    )
    relatorio_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
