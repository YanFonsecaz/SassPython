
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class InlinksRequest(BaseModel):
    pilar_url: str | None = Field(default=None, max_length=2048)
    pilar_markdown: str | None = Field(default=None, max_length=100000)
    candidatas_urls: list[str] = Field(..., min_length=1, max_length=100)
    threshold_score: float = Field(default=0.6, ge=0.0, le=1.0)
    max_inlinks: int = Field(default=8, ge=1, le=20)
    rel_attr: str = Field(default="noopener")
    ancoras_preferidas: list[str] = Field(default_factory=list, max_length=10)
    permitir_cta_fallback: bool = Field(default=False)
    objetivo_linkagem: str | None = Field(default=None, max_length=300)

    @field_validator("pilar_url")
    @classmethod
    def validar_pilar_url(cls, v: str | None) -> str | None:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("URL do pilar deve usar http ou https")
        return v

    @field_validator("objetivo_linkagem")
    @classmethod
    def validar_objetivo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("ancoras_preferidas")
    @classmethod
    def validar_ancoras(cls, v: list[str]) -> list[str]:
        normalizadas: list[str] = []
        vistos: set[str] = set()
        for raw in v:
            s = (raw or "").strip()
            if not s:
                continue
            if len(s) < 2 or len(s) > 50:
                raise ValueError("Cada ancora deve ter entre 2 e 50 caracteres")
            chave = s.lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            normalizadas.append(s)
        return normalizadas

    @field_validator("candidatas_urls")
    @classmethod
    def validar_candidatas(cls, v: list[str]) -> list[str]:
        for url in v:
            if len(url) > 2048:
                raise ValueError(f"URL excede 2048 caracteres: {url[:50]}...")
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"URL invalida (use http/https): {url[:50]}...")
        return v

    @field_validator("rel_attr")
    @classmethod
    def validar_rel(cls, v: str) -> str:
        validos = {"noopener", "nofollow", "sponsored", "ugc"}
        if v not in validos:
            raise ValueError(f"rel_attr invalido. Validos: {validos}")
        return v


class CustoInlinksResponse(BaseModel):
    custo_base: int
    custo_por_url: int
    custo_maximo: int
    custo_estimado: int
    n_urls: int


class InlinkSugeridoResponse(BaseModel):
    id: UUID
    url_destino: str
    anchor_text: str
    paragrafo_idx: int
    score_total: float
    score_semantico: float
    score_contexto: float
    status: str
    motivo_rejeicao: str | None = None
    trecho_contexto: str | None = None
    titulo_destino: str | None = None
    motivo_contexto: str | None = None
    categoria_match: str | None = None
    motivo_sugestao: str | None = None
    trecho_original: str | None = None
    conector_antes: str | None = None
    conector_depois: str | None = None

    model_config = {"from_attributes": True}
