from pydantic import BaseModel, Field, field_validator


class DistribuirInlinksRequest(BaseModel):
    url_alvo: str = Field(..., max_length=2048)
    candidatas_urls: list[str] = Field(..., min_length=1, max_length=100)
    threshold_score: float = Field(default=0.6, ge=0.0, le=1.0)
    max_inlinks_por_candidata: int = Field(default=1, ge=1, le=3)
    rel_attr: str = Field(default="noopener")
    ancoras_preferidas: list[str] = Field(default_factory=list, max_length=10)
    permitir_cta_fallback: bool = Field(default=True)
    objetivo_linkagem: str | None = Field(default=None, max_length=300)

    @field_validator("objetivo_linkagem")
    @classmethod
    def validar_objetivo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        return s

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

    @field_validator("url_alvo")
    @classmethod
    def validar_url_alvo(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL alvo deve usar http ou https")
        return v

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


class CustoDistribuirInlinksResponse(BaseModel):
    custo_base: int
    custo_por_candidata: int
    custo_maximo: int
    custo_estimado: int
    n_candidatas: int
