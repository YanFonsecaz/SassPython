import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Usuario(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "usuarios"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verificado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    plano_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planos.id"), nullable=True
    )
    mfa_ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sessoes: Mapped[list["Sessao"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")  # noqa: F821
    mfa_dispositivos: Mapped[list["MfaDispositivo"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")  # noqa: F821
    reset_tokens: Mapped[list["ResetSenhaToken"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")  # noqa: F821
