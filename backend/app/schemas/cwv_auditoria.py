"""Schemas da auditoria CWV (SPEC_CWV_Auditoria_Ciclo_De_Vida)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

FaseAuditoria = Literal["before", "aguardando_implementacao", "after", "concluida"]
OrigemItem = Literal["psi_audit", "page_experience", "field_data", "agentic"]
StatusCheck = Literal["pass", "fail", "na"]
StatusImplementacao = Literal["nao_executado", "em_andamento", "implementado"]


class AuditoriaCriarRequest(BaseModel):
    cliente_id: UUID
    execucao_id: UUID
    titulo: str | None = None


class ChecklistItemResposta(BaseModel):
    id: UUID
    origem: OrigemItem
    item_codigo: str
    titulo: str
    status_before: StatusCheck
    status_after: StatusCheck | None = None
    status_implementacao: StatusImplementacao = "nao_executado"
    nota_cliente: str | None = None
    nota_seo: str | None = None
    prioridade: int = 0
    esforco: str | None = None
    escopo_json: dict = {}
    metricas_afetadas: list[str] = []


class AuditoriaResposta(BaseModel):
    id: UUID
    cliente_id: UUID
    titulo: str
    fase: FaseAuditoria
    execucao_before_id: UUID | None = None
    execucao_after_id: UUID | None = None
    health_score_before: float | None = None
    health_score_after: float | None = None
    consolidacao_status: str = "nao_executada"
    # SPEC_CWV_Contratos_JSONB_Tipados: relatorio_json tipado (não dict cru).
    relatorio_json: "RelatorioJsonResposta | None" = None
    checklist: list[ChecklistItemResposta] = []
    n_pass_before: int = 0
    n_fail_before: int = 0
    n_implementados: int = 0
    criado_em: str
    atualizado_em: str


# --- SPEC_CWV_Contratos_JSONB_Tipados --------------------------------------


class PlanoFaseRelatorio(BaseModel):
    """Fase do plano de ação do relatório executivo (redator.py + fallback)."""

    titulo: str
    justificativa: str
    itens_codigos: list[str] = []


class RelatorioJsonResposta(BaseModel):
    """Shape do JSONB ``cwv_auditoria.relatorio_json``.

    ``status`` é ``gerando`` (job em fila), ``concluido`` (redator OK) ou
    ``falhou`` (redator exceção). Quando ``status='concluido'``, os demais
    campos vêm preenchidos.
    """

    model_config = {"extra": "allow"}  # lenient: preserva campos novos sem quebrar clientes.

    status: str | None = None
    sumario_executivo_md: str | None = None
    diagnostico_tecnico_md: str | None = None
    plano_fases: list[PlanoFaseRelatorio] = []
    gerado_em: str | None = None
    modelo: str | None = None


class ProblemaConsolidadoResposta(BaseModel):
    """SPEC_CWV_Contratos_JSONB_Tipados: tipa o ``cwv_problema_consolidado``.

    Espelha o tipo TS ``ProblemaConsolidadoResposta`` em ``cwv.ts:420``.
    """

    id: UUID
    titulo: str
    causa_raiz: str
    kb_codigo: str | None = None
    severidade: int
    prioridade_ordem: int
    esforco: str | None = None
    metricas_afetadas: list[str] = []
    escopo_json: dict = {}
    evidencias_json: dict = {}
    recomendacao_md: str
    problemas_origem_ids: list[str] = []


class ConsolidadosResposta(BaseModel):
    """SPEC_CWV_Contratos_JSONB_Tipados: ``GET /auditorias/{id}/consolidados``."""

    consolidados: list[ProblemaConsolidadoResposta]
    status: str


class ArtefatoAgenticoResposta(BaseModel):
    """SPEC_CWV_Navegacao_Agentica_Geracao_IA: artefato gerado por IA.

    ``tipo='llms_txt'``: ``conteudo_md`` = Markdown do llms.txt, ``diagnostico``
    preenchido. ``tipo='webmcp'``: ``conteudo_md`` = código scaffold,
    ``explicacao_md`` preenchido; ``meta_json`` traz ferramentas_sugeridas,
    como_aplicar_md, detectado, versao_spec (WebMCP) ou justificativa (llms.txt).
    """

    tipo: str
    diagnostico: str | None = None
    conteudo_md: str
    explicacao_md: str | None = None
    meta_json: dict = {}
    modelo: str | None = None
    gerado_em: str


AuditoriaResposta.model_rebuild()


class AuditoriaResumo(BaseModel):
    id: UUID
    titulo: str
    fase: FaseAuditoria
    cliente_id: UUID | None = None
    cliente_nome: str | None = None
    health_score_before: float | None = None
    health_score_after: float | None = None
    n_itens: int = 0
    criado_em: str


class AuditoriaListResponse(BaseModel):
    auditorias: list[AuditoriaResumo]
    # SPEC_CWV_Paginacao_Listagens: total sem página para UI "Carregar mais".
    total: int = 0


class AuditoriaPatch(BaseModel):
    fase: FaseAuditoria | None = None
    titulo: str | None = None


class ChecklistItemPatch(BaseModel):
    status_implementacao: StatusImplementacao | None = None
    nota_cliente: str | None = None
    nota_seo: str | None = None
    prioridade: int | None = Field(default=None, ge=0)
    status_before: StatusCheck | None = None
    status_after: StatusCheck | None = None


class ComparativoMetricas(BaseModel):
    analise_id: str
    score_performance: int | None = None
    lcp_ms: float | None = None
    cls: float | None = None
    inp_ms: float | None = None
    tbt_ms: float | None = None
    n_problemas: int = 0


class ComparativoProblemas(BaseModel):
    resolvidos: int
    persistentes: int
    novos: int
    titulos_resolvidos: list[str] = []
    titulos_novos: list[str] = []


class ComparativoPar(BaseModel):
    url_canonica: str
    estrategia: str
    template_tipo: str = ""
    before: ComparativoMetricas
    after: ComparativoMetricas | None = None
    problemas: ComparativoProblemas | None = None


class ComparativoResposta(BaseModel):
    fase: FaseAuditoria
    pares: list[ComparativoPar]


class LinkReferencia(BaseModel):
    titulo: str
    url: str


class EvidenciaItem(BaseModel):
    """Elementos com falha agrupados por URL×estratégia (SPEC_CWV_Detalhe_Evidencias_Elementos)."""

    url_canonica: str
    estrategia: str
    elementos: list[str] = []
    total: int = 0


class ItemDetalheResposta(BaseModel):
    """Ficha explicativa de um item do checklist (KB via item_codigo)."""

    item_codigo: str
    titulo: str
    tem_kb: bool
    descricao: str | None = None
    severidade: int | None = None
    metricas_afetadas: list[str] = []
    solucao_geral: str | None = None
    solucao_plataforma: str | None = None
    plataforma: str | None = None
    links_referencia: list[LinkReferencia] = []
    esforco: str | None = None
    urls_escopo: list[str] = []
    evidencias: list[EvidenciaItem] = []
