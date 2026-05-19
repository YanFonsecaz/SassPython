import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PesquisaCache(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pesquisas_cache"
    __table_args__ = (
        UniqueConstraint("usuario_id", "query_hash", "fonte", name="uq_pesquisas_cache_lookup"),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True
    )
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    query_original: Mapped[str] = mapped_column(String(1000), nullable=False)
    resultados_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fonte: Mapped[str] = mapped_column(String(30), nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
