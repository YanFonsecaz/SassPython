import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class InlinkSugerido(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "inlinks_sugeridos"

    execucao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"), nullable=False
    )
    url_origem: Mapped[str] = mapped_column(Text, nullable=False)
    url_destino: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_text: Mapped[str] = mapped_column(Text, nullable=False)
    paragrafo_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    offset_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    score_total: Mapped[float] = mapped_column(Float, nullable=False)
    score_semantico: Mapped[float] = mapped_column(Float, nullable=False)
    score_contexto: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="aplicado")
    motivo_rejeicao: Mapped[str | None] = mapped_column(Text, nullable=True)
    rel_attr: Mapped[str] = mapped_column(String(50), nullable=False, default="noopener")
    trecho_contexto: Mapped[str | None] = mapped_column(Text, nullable=True)
    titulo_destino: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo_contexto: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria_match: Mapped[str | None] = mapped_column(String(30), nullable=True)
    trecho_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    conector_antes: Mapped[str | None] = mapped_column(String(80), nullable=True)
    conector_depois: Mapped[str | None] = mapped_column(String(80), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(nullable=False, server_default="now()")
