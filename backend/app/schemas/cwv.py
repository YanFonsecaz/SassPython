from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator

TemplateTipo = Literal["home", "categoria", "produto", "blog", "blogpost", "outros"]
Estrategia = Literal["mobile", "desktop"]
MotivoFalha = Literal[
    "saldo_insuficiente",
    "rate_limit",
    "cliente_invalido",
    "cliente_removido",
    "psi_total",
    "timeout",
    "cancelada",
    "erro_interno",
]
PlataformaValida = Literal[
    "vtex", "wordpress", "nextjs", "shopify", "wix",
    "squarespace", "magento", "hugo", "jekyll", "webflow", "outros",
]


class PlataformaOverrideRequest(BaseModel):
    plataforma: PlataformaValida


class PlataformaOverrideResponse(BaseModel):
    plataforma: str
    n_problemas_atualizados: int


class UrlsPorTemplate(BaseModel):
    home: list[HttpUrl] = Field(default_factory=list, max_length=10)
    categoria: list[HttpUrl] = Field(default_factory=list, max_length=20)
    produto: list[HttpUrl] = Field(default_factory=list, max_length=20)
    blog: list[HttpUrl] = Field(default_factory=list, max_length=10)
    blogpost: list[HttpUrl] = Field(default_factory=list, max_length=20)
    outros: list[HttpUrl] = Field(default_factory=list, max_length=20)

    @field_validator("*")
    @classmethod
    def dedup(cls, v: list[HttpUrl]) -> list[HttpUrl]:
        seen: set[str] = set()
        out: list[HttpUrl] = []
        for u in v:
            s = str(u)
            if s not in seen:
                seen.add(s)
                out.append(u)
        return out

    def total(self) -> int:
        return sum(len(getattr(self, f)) for f in self.model_fields)

    def itens(self) -> list[tuple[str, str]]:
        result = []
        for template in ("home", "categoria", "produto", "blog", "blogpost", "outros"):
            for url in getattr(self, template):
                result.append((template, str(url)))
        return result


class AnalisarRequest(BaseModel):
    cliente_id: UUID
    urls_por_template: UrlsPorTemplate

    @field_validator("urls_por_template")
    @classmethod
    def pelo_menos_uma_url(cls, v: UrlsPorTemplate) -> UrlsPorTemplate:
        if v.total() == 0:
            raise ValueError("Informe pelo menos uma URL em algum template")
        if v.total() > 50:
            raise ValueError("Máximo de 50 URLs por execução")
        return v


class ProblemaResposta(BaseModel):
    id: UUID
    kb_codigo: str | None = None
    audit_id: str | None = None
    titulo: str
    severidade: int
    prioridade_ordem: int
    metricas_afetadas: list[str]
    contexto_especifico: dict | None = None
    documentacao_md: str
    pesquisado: bool = False
    esforco: str | None = None


class AnaliseResposta(BaseModel):
    id: UUID
    cliente_id: UUID
    url: str
    url_canonica: str
    template_tipo: str
    plataforma_detectada: str
    estrategia: str
    score_performance: int | None
    lcp_ms: float | None
    cls: float | None
    inp_ms: float | None
    fcp_ms: float | None
    ttfb_ms: float | None
    tbt_ms: float | None
    status: str
    erro_msg: str | None
    criado_em: str
    problemas: list[ProblemaResposta]
    audits_totais: int = 0
    n_network_requests: int = 0
    main_document_size_bytes: int = 0
    llm_usado: bool = False
    llm_audits_processados: int = 0
    llm_audits_descartados: int = 0


class AnaliseResumoResposta(BaseModel):
    id: UUID
    url_canonica: str
    template_tipo: str
    estrategia: str
    score_performance: int | None
    lcp_ms: float | None
    cls: float | None
    inp_ms: float | None
    n_problemas: int
    n_problemas_alta_severidade: int
    criado_em: str


class HistoricoUrlResposta(BaseModel):
    url_canonica: str
    template_tipo: str
    plataforma_detectada: str
    analises: list[AnaliseResumoResposta]


class HistoricoListResponse(BaseModel):
    urls: list[HistoricoUrlResposta]


class CustoCwvResponse(BaseModel):
    custo: int
    custo_por_url: int
    n_urls: int
    n_urls_reais: int = 0


class MetricaComparada(BaseModel):
    antes: int | float
    depois: int | float
    delta: int | float
    melhorou: bool | None


class ProblemaComparado(BaseModel):
    kb_codigo: str | None
    titulo: str


class ComparacaoResposta(BaseModel):
    analise_atual_id: str
    analise_anterior_id: str | None
    dias_decorridos: int | None
    metricas: dict[str, MetricaComparada]
    problemas_resolvidos: list[ProblemaComparado]
    problemas_novos: list[ProblemaComparado]
    problemas_persistentes: list[ProblemaComparado]


class HealthScorePorEstrategia(BaseModel):
    mobile: float | None = None
    desktop: float | None = None


class HealthScoreResposta(BaseModel):
    health_score: float | None
    n_pass: int = 0
    n_total: int = 0
    por_estrategia: HealthScorePorEstrategia = Field(default_factory=HealthScorePorEstrategia)
