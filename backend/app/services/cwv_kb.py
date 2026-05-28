from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

Plataforma = Literal[
    "geral", "vtex", "wordpress", "nextjs", "shopify", "wix",
    "squarespace", "magento", "hugo", "jekyll", "webflow",
]
Metrica = Literal["LCP", "CLS", "INP", "TBT", "FCP", "TTFB"]


class LinkReferencia(BaseModel):
    titulo: str
    url: str


class EntradaKB(BaseModel):
    codigo: str = Field(pattern=r"^[a-z0-9-]+$", min_length=3, max_length=80)
    titulo: str = Field(min_length=5, max_length=200)
    severidade: int = Field(ge=1, le=5)
    metricas_afetadas: list[Metrica] = Field(min_length=1)
    audits_lighthouse: list[str] = Field(default_factory=list)
    descricao: str = Field(min_length=20)
    solucoes: dict[Plataforma, str]
    links_referencia: list[LinkReferencia] = Field(default_factory=list)

    @field_validator("solucoes")
    @classmethod
    def precisa_solucao_geral(cls, v: dict) -> dict:
        if "geral" not in v:
            raise ValueError("Toda entrada precisa de solução 'geral'")
        return v


class BaseKB(BaseModel):
    entradas: list[EntradaKB]

    @field_validator("entradas")
    @classmethod
    def codigos_unicos(cls, v: list[EntradaKB]) -> list[EntradaKB]:
        codigos = [e.codigo for e in v]
        dup = {c for c in codigos if codigos.count(c) > 1}
        if dup:
            raise ValueError(f"Códigos duplicados na KB: {dup}")
        return v


KB_PATH = Path(__file__).parent.parent / "data" / "cwv_knowledge_base.yaml"

AUDITS_IGNORADOS = {
    "metrics",
    "diagnostics",
    "screenshot-thumbnails",
    "final-screenshot",
    "full-page-screenshot",
    "network-requests",
    "network-rtt",
    "main-thread-tasks",
    "script-treemap-data",
    "network-server-latency",
}

AUDIT_ALIASES: dict[str, str] = {
    "cache-insight": "uses-long-cache-ttl",
    "render-blocking-insight": "render-blocking-resources",
    "legacy-javascript-insight": "legacy-javascript",
    "image-delivery-insight": "modern-image-formats",
    "third-parties-insight": "third-party-summary",
    "dom-size-insight": "dom-size",
    "lcp-discovery-insight": "prioritize-lcp-image",
    "viewport-insight": "viewport",
    "font-display-insight": "font-display",
    "duplicated-javascript-insight": "duplicated-javascript",
    "max-potential-fid": "total-blocking-time",
}


@lru_cache(maxsize=1)
def carregar_kb() -> BaseKB:
    with open(KB_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return BaseKB(entradas=raw)


def buscar_entrada(codigo: str) -> dict | None:
    kb = carregar_kb()
    for entrada in kb.entradas:
        if entrada.codigo == codigo:
            return entrada.model_dump()
    return None


def listar_kb_codigos() -> list[dict]:
    kb = carregar_kb()
    return [
        {"codigo": e.codigo, "titulo": e.titulo, "metricas_afetadas": e.metricas_afetadas}
        for e in kb.entradas
    ]


def listar_kb_codigos_descritos(max_desc_chars: int = 80) -> list[dict]:
    kb = carregar_kb()
    out = []
    for e in kb.entradas:
        desc_curta = e.descricao.split("\n")[0][:max_desc_chars]
        out.append({
            "codigo": e.codigo,
            "titulo": e.titulo,
            "descricao_curta": desc_curta,
            "metricas_afetadas": e.metricas_afetadas,
        })
    return out


def mapeamento_audit_kb() -> dict[str, str]:
    kb = carregar_kb()
    mapa: dict[str, str] = {}
    for entrada in kb.entradas:
        for audit in entrada.audits_lighthouse:
            if audit not in mapa:
                mapa[audit] = entrada.codigo
    return mapa


def mapeamento_audit_kb_com_aliases() -> dict[str, str]:
    base = mapeamento_audit_kb()
    out = dict(base)
    for alias, clasico in AUDIT_ALIASES.items():
        if alias not in out and clasico in base:
            out[alias] = base[clasico]
    return out


def recarregar_kb() -> None:
    carregar_kb.cache_clear()
