import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Cliente(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "clientes"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    site_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    conteudos: Mapped[list["ConteudoVetor"]] = relationship(  # noqa: F821
        back_populates="cliente", cascade="all, delete-orphan"
    )
    execucoes: Mapped[list["ExecucaoFerramenta"]] = relationship(  # noqa: F821
        back_populates="cliente", cascade="all, delete-orphan"
    )
