"""Modelo da tabela indices_site (status da indexação do site por cliente).

SPEC_Inlinks_Descoberta_Automatica_Candidatas: um registro por cliente,
acompanha o progresso e o resultado da indexação do sitemap.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class IndiceSite(Base, TimestampMixin):
    """criado_em/atualizado_em vêm do TimestampMixin (migration 0023 tem ambos)."""

    __tablename__ = "indices_site"

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), primary_key=True
    )
    dominio: Mapped[str] = mapped_column(String(255), nullable=False)
    # indexando | pronto | falhou
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="indexando")
    n_paginas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_falhas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    erro_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
