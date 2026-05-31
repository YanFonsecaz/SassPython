from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class BlocoEntrada(BaseModel):
    texto: str = Field(default="", max_length=8000)
    imagens: list[str] = Field(default_factory=list, max_length=10)


class GerarParecerRequest(BaseModel):
    cliente_id: UUID
    titulo_sugerido: str | None = Field(default=None, max_length=200)
    blocos: list[BlocoEntrada] = Field(min_length=1, max_length=40)

    @property
    def total_imagens(self) -> int:
        return sum(len(b.imagens) for b in self.blocos)


class CustoParecerResponse(BaseModel):
    custo: int
    custo_base: int
    custo_por_imagem: int
    n_imagens: int


class ParecerExecucaoResposta(BaseModel):
    id: str
    ferramenta: str
    status: str
    etapa_atual: str | None = None
    creditos_cobrados: int | None = None
    parecer_id: str | None = None
    erro_msg: str | None = None
    criado_em: str
    concluida_em: str | None = None


class ParecerResposta(BaseModel):
    id: str
    execucao_id: str
    cliente_id: str
    cliente_nome: str
    titulo: str
    subtitulo: str | None = None
    site: str | None = None
    plataforma: str | None = None
    meta: dict
    estrutura: dict
    parecer_html: str
    n_imagens: int
    modelo: str | None = None
    status: str
    criado_em: str
    atualizado_em: str | None = None


class ParecerResumoResposta(BaseModel):
    id: str
    execucao_id: str
    cliente_id: str
    cliente_nome: str
    titulo: str
    subtitulo: str | None = None
    site: str | None = None
    plataforma: str | None = None
    n_imagens: int
    status: str
    criado_em: str


class ParecerHistoricoResponse(BaseModel):
    pareceres: list[ParecerResumoResposta]


class ExportarParecerRequest(BaseModel):
    html: str = Field(min_length=1)
    nome_arquivo: str | None = Field(default=None, max_length=120)


Impacto = Literal["LCP", "CLS", "INP", "FCP", "TTFB", "SEO", "Indexacao", "Acessibilidade", "Outro"]


class AchadoImagem(BaseModel):
    indice_global: int
    o_que_mostra: str
    problema: str
    impacto: list[Impacto]
    onde_ocorre: str
    confianca: float = Field(ge=0, le=1)
    degradado: bool = Field(default=False)  # True quando a analise de visao falhou (fallback)


class EvidenciaItem(BaseModel):
    legenda: str  # texto apos "Evidencia:"
    imagens_indices: list[int] = Field(default_factory=list)


class ProblemaSecao(BaseModel):
    descricao: str  # paragrafo "Problema"
    evidencias: list[EvidenciaItem] = Field(default_factory=list)  # 1+ "Evidencia:"
    solucao: str  # paragrafo "Solucao"
    solucao_escopo: str | None = None  # ex.: "Desktop e Mobile" -> "Solucao (Desktop e Mobile)"


class SubSecao(BaseModel):
    titulo: str  # ex.: "LCP atrasado por CSS bloqueante" ou "Versao Desktop"
    problemas: list[ProblemaSecao]


class SecaoParecer(BaseModel):
    titulo: str  # ex.: "Pagina de categoria — /cabelos"
    url: str | None = None
    observacao: str | None = None  # ex.: "Observacao: os problemas ocorrem em Desktop e Mobile."
    subsecoes: list[SubSecao]


class PrioridadeGlobal(BaseModel):
    titulo: str  # ex.: "Prioridade 1 — Eliminar render-blocking"
    itens: list[str]


class ParecerEstruturado(BaseModel):
    titulo: str = "PARECER TÉCNICO — SEO / PERFORMANCE"
    subtitulo: str  # ex.: "Otimizacao de Core Web Vitals"
    escopo_linha: str  # ex.: "LCP e CLS — dominio.com.br (Cliente)"
    secoes: list[SecaoParecer]
    recomendacoes_globais: list[PrioridadeGlobal]
