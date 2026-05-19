import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConteudoVetor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conteudos_vetores"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True
    )
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=True, index=True
    )
    execucao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execucoes_ferramentas.id"), nullable=True
    )
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    intencao: Mapped[str] = mapped_column(String(50), nullable=False)
    palavras_chave: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    atividades: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding: Mapped[list[Any]] = mapped_column(Vector(1024), nullable=False)
    score_base: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    url_canonica: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo_recurso: Mapped[str | None] = mapped_column(String(20), nullable=True)
    html_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    cliente: Mapped["Cliente"] = relationship(back_populates="conteudos")  # noqa: F821
