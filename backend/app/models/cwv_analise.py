import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class CwvAnalise(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cwv_analise"

    execucao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"), nullable=False,
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False,
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_canonica: Mapped[str] = mapped_column(Text, nullable=False)
    template_tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    estrategia: Mapped[str] = mapped_column(String(10), nullable=False, server_default="mobile")
    plataforma_detectada: Mapped[str] = mapped_column(String(20), nullable=False, server_default="desconhecida")
    score_performance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lcp_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    cls: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    inp_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    fcp_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    ttfb_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    tbt_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    raw_psi_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # SPEC_CWV_Field_Data_Retencao_Payload: resumo compacto do payload PSI
    # (≤64KB, sem screenshots/details.items) + field data CrUX materializado.
    raw_resumo_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    crux_lcp_p75_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    crux_inp_p75_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    crux_cls_p75: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    crux_lcp_categoria: Mapped[str | None] = mapped_column(String(20), nullable=True)
    crux_inp_categoria: Mapped[str | None] = mapped_column(String(20), nullable=True)
    crux_cls_categoria: Mapped[str | None] = mapped_column(String(20), nullable=True)
    crux_overall_categoria: Mapped[str | None] = mapped_column(String(20), nullable=True)
    crux_origem_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    erro_msg: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audits_totais: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    n_network_requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    main_document_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    llm_usado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    llm_audits_processados: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    llm_audits_descartados: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "template_tipo IN ('home','categoria','produto','blog','blogpost','outros')",
            name="cwv_analise_template_check",
        ),
        CheckConstraint(
            "estrategia IN ('mobile','desktop')",
            name="cwv_analise_estrategia_check",
        ),
        Index("ix_cwv_analise_cliente_url_data", "cliente_id", "url_canonica", criado_em.desc()),
        Index("ix_cwv_analise_execucao", "execucao_id"),
        Index("ix_cwv_analise_usuario", "usuario_id"),
    )
