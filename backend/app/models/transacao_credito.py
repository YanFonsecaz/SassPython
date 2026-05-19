import uuid

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TransacaoCredito(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "transacoes_creditos"
    __table_args__ = (
        Index("ix_transacoes_conta_criado", "conta_id", "criado_em"),
    )

    conta_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contas_creditos.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    descricao: Mapped[str] = mapped_column(String(500), nullable=False)
    ferramenta: Mapped[str | None] = mapped_column(String(50), nullable=True)
    execucao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execucoes_ferramentas.id"), nullable=True
    )

    conta: Mapped["ContaCredito"] = relationship(back_populates="transacoes")  # noqa: F821
