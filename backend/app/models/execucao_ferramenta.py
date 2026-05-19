import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExecucaoFerramenta(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "execucoes_ferramentas"
    __table_args__ = (
        Index("ix_execucoes_usuario_status", "usuario_id", "status"),
        Index("ix_execucoes_usuario_criado", "usuario_id", "criado_em"),
        Index("ix_execucoes_status", "status"),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True
    )
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=True
    )
    ferramenta: Mapped[str] = mapped_column(String(50), nullable=False)
    creditos_cobrados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    etapa_atual: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entrada_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resultado_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    erro_msg: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tentativas_revisao: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tentativas_feedback: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timeout_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cliente: Mapped["Cliente"] = relationship(back_populates="execucoes")  # noqa: F821
    versoes: Mapped[list["VersaoArtigo"]] = relationship(  # noqa: F821
        back_populates="execucao", cascade="all, delete-orphan"
    )
