import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Compra(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "compras"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    pacote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pacotes_creditos.id"), nullable=True
    )
    plano_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planos.id"), nullable=True
    )
    valor_pago: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    gateway_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
