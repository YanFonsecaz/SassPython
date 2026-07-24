"""KB de soluções SEOTEC (SPEC_SEOTEC_Agentes_IA §2).

Recomendação canônica por item do checklist (base = textos das abas da planilha),
com variações opcionais por plataforma. Cobertura parcial de propósito: item sem
entrada aqui cai no fallback LLM do recomendador (padrão KB→LLM do CWV).

Loader no padrão de `services/cwv_kb.py` / `services/seotec_checklist.py`:
pydantic + lru_cache + falha rápida. Um YAML por categoria em
`app/data/seotec_solucoes/`.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

KB_DIR = Path(__file__).parent.parent / "data" / "seotec_solucoes"

# Alinhada à detecção de plataforma do CWV (services/cwv_kb.py Plataforma).
Plataforma = Literal[
    "geral", "wordpress", "vtex", "shopify", "nextjs", "wix",
    "squarespace", "magento", "webflow",
]


class SolucaoKB(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=3, max_length=140)
    recomendacao: str = Field(min_length=10)
    solucoes: dict[Plataforma, str] = Field(default_factory=dict)


class CategoriaKB(BaseModel):
    categoria: str
    itens: list[SolucaoKB]


class BaseSeotecKB(BaseModel):
    categorias: list[CategoriaKB]

    @model_validator(mode="after")
    def _slugs_unicos(self) -> "BaseSeotecKB":
        slugs = [i.slug for c in self.categorias for i in c.itens]
        dup = {s for s in slugs if slugs.count(s) > 1}
        if dup:
            raise ValueError(f"Slugs duplicados na KB de soluções: {dup}")
        return self

    def itens(self) -> list[SolucaoKB]:
        return [i for c in self.categorias for i in c.itens]

    def por_slug(self) -> dict[str, SolucaoKB]:
        return {i.slug: i for i in self.itens()}


@lru_cache(maxsize=1)
def carregar_kb() -> BaseSeotecKB:
    categorias: list[CategoriaKB] = []
    for arquivo in sorted(KB_DIR.glob("*.yaml")):
        raw = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
        categorias.append(CategoriaKB(**raw))
    # KB parcial é válida (miss => LLM). Lista vazia também: nenhum YAML ainda.
    return BaseSeotecKB(categorias=categorias)


def recarregar_kb() -> None:
    carregar_kb.cache_clear()


def buscar(slug: str, plataforma: str = "geral") -> SolucaoKB | None:
    """Entrada canônica do item, ou None (recomendador cai no LLM)."""
    return carregar_kb().por_slug().get(slug)


def render_recomendacao(entrada: SolucaoKB, plataforma: str = "geral") -> str:
    """Variação da plataforma quando existe; senão a recomendação canônica."""
    return entrada.solucoes.get(plataforma) or entrada.recomendacao


def slugs_orfaos(checklist_slugs: set[str]) -> set[str]:
    """Slugs na KB que não existem no checklist — deve ser sempre vazio (test)."""
    return {s for s in carregar_kb().por_slug()} - checklist_slugs
