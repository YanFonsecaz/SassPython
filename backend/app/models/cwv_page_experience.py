"""Modelo: cwv_page_experience (SPEC_CWV_Page_Experience).

Uma linha por origem (``scheme://host``) por execução — checagens de Page
Experience são propriedades do domínio, não da URL individual.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class CwvPageExperience(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cwv_page_experience"
    __table_args__ = (
        CheckConstraint(
            "https IN ('pass','fail','erro','na')",
            name="cwv_page_experience_https_check",
        ),
        CheckConstraint(
            "ssl IN ('pass','fail','erro','na')",
            name="cwv_page_experience_ssl_check",
        ),
        CheckConstraint(
            "redirect_301 IN ('pass','fail','erro','na')",
            name="cwv_page_experience_redirect_check",
        ),
        CheckConstraint(
            "security_headers IN ('pass','fail','erro','na')",
            name="cwv_page_experience_headers_check",
        ),
        CheckConstraint(
            "safe_browsing IN ('pass','fail','erro','na')",
            name="cwv_page_experience_safe_check",
        ),
        CheckConstraint(
            "mixed_content IN ('pass','fail','erro','na')",
            name="cwv_page_experience_mixed_check",
        ),
        CheckConstraint(
            "mobile_friendly IN ('pass','fail','erro','na')",
            name="cwv_page_experience_mobile_check",
        ),
        # UNIQUE (execucao_id, origem) — uma linha por origem por execução.
        Index("uq_cwv_page_experience_exec_origem", "execucao_id", "origem", unique=True),
        Index("ix_cwv_page_experience_execucao", "execucao_id"),
    )

    execucao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"),
        nullable=False,
    )
    origem: Mapped[str] = mapped_column(Text, nullable=False)
    https: Mapped[str] = mapped_column(String(10), nullable=False, server_default="na")
    ssl: Mapped[str] = mapped_column(String(10), nullable=False, server_default="na")
    redirect_301: Mapped[str] = mapped_column(String(10), nullable=False, server_default="na")
    security_headers: Mapped[str] = mapped_column(String(10), nullable=False, server_default="na")
    safe_browsing: Mapped[str] = mapped_column(String(10), nullable=False, server_default="na")
    mixed_content: Mapped[str] = mapped_column(String(10), nullable=False, server_default="na")
    mobile_friendly: Mapped[str] = mapped_column(String(10), nullable=False, server_default="na")
    detalhes_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False,
    )
