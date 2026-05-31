import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Parecer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "parecer"

    execucao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"), nullable=False,
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False,
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True,
    )

    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    subtitulo: Mapped[str | None] = mapped_column(Text)
    site: Mapped[str | None] = mapped_column(Text)
    plataforma: Mapped[str | None] = mapped_column(Text)  # IA pode inferir descricao longa
    cliente_nome: Mapped[str] = mapped_column(Text, nullable=False)

    meta_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    estrutura_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parecer_html: Mapped[str] = mapped_column(Text, nullable=False)
    n_imagens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    modelo: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="concluido")

    __table_args__ = (
        Index("ix_parecer_usuario_cliente_data", "usuario_id", "cliente_id", "criado_em"),
        Index("ix_parecer_execucao", "execucao_id"),
    )
