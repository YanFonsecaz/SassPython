import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VersaoArtigo(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "versoes_artigo"
    __table_args__ = (
        UniqueConstraint("execucao_id", "versao", name="uq_versoes_execucao_versao"),
    )

    execucao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execucoes_ferramentas.id"), nullable=False
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    origem: Mapped[str] = mapped_column(String(30), nullable=False)
    conteudo_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    contagem_palavras: Mapped[int] = mapped_column(Integer, nullable=False)
    score_revisao: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback_recebido: Mapped[str | None] = mapped_column(Text, nullable=True)

    execucao: Mapped["ExecucaoFerramenta"] = relationship(back_populates="versoes")  # noqa: F821
