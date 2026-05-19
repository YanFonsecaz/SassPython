import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ContaCredito(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "contas_creditos"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), unique=True, nullable=False
    )
    saldo_plano: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saldo_extras: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saldo_reservado: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ciclo_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    ciclo_fim: Mapped[date] = mapped_column(Date, nullable=False)

    transacoes: Mapped[list["TransacaoCredito"]] = relationship(  # noqa: F821
        back_populates="conta", cascade="all, delete-orphan"
    )

    @hybrid_property
    def saldo_disponivel(self) -> int:
        return self.saldo_plano + self.saldo_extras - self.saldo_reservado

    @property
    def saldo_total(self) -> int:
        return self.saldo_plano + self.saldo_extras
