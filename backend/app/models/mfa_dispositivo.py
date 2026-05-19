import uuid

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MfaDispositivo(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "mfa_dispositivos"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    segredo_totp: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_id: Mapped[bytes | None] = mapped_column(nullable=True)
    public_key: Mapped[bytes | None] = mapped_column(nullable=True)
    counter: Mapped[int | None] = mapped_column(nullable=True)
    ultimo_uso: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_codigo: Mapped[str | None] = mapped_column(String(6), nullable=True)

    usuario: Mapped["Usuario"] = relationship(back_populates="mfa_dispositivos")  # noqa: F821
