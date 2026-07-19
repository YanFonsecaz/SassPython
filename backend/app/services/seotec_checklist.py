"""Loader do checklist SEOTEC (SPEC_SEOTEC_Checklist_Motor_Regras).

Carrega e valida os YAMLs de backend/app/data/seotec_checklist/ no padrão
da KB do CWV (services/cwv_kb.py): pydantic + cache + falha rápida no startup.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

CHECKLIST_DIR = Path(__file__).parent.parent / "data" / "seotec_checklist"

TOTAL_PESOS_ESPERADO = 940

Fonte = Literal["sf", "manual", "gsc", "cwv-link"]
Prioridade = Literal["low", "medium", "high", "very-high"]
OpFiltro = Literal[
    "vazio", "nao_vazio", "igual", "regex", "duplicado",
    "maior", "menor", "entre", "len_maior",
]


class RegraFiltro(BaseModel):
    model_config = {"extra": "forbid"}

    campo: str
    op: OpFiltro
    valor: int | float | str | list[int | float] | None = None

    @model_validator(mode="after")
    def _entre_exige_par_de_numeros(self) -> "RegraFiltro":
        if self.op == "entre":
            if not isinstance(self.valor, (list, tuple)) or len(self.valor) != 2:
                raise ValueError("regra op 'entre' exige valor como lista de 2 números")
            if not all(isinstance(v, (int, float)) for v in self.valor):
                raise ValueError("regra op 'entre' exige valor como lista de 2 números")
        return self


class RegraItem(BaseModel):
    model_config = {"extra": "forbid"}

    export: str
    tipo: Literal["contagem", "limiar", "existencia", "proporcao", "custom"]
    filtro: RegraFiltro | None = None
    campo: str | None = None
    funcao: str | None = None
    limite_proporcao: float | None = None
    atencao_max: int = 0
    na_se_export_vazio: bool = False

    @model_validator(mode="after")
    def _consistencia(self) -> "RegraItem":
        if self.tipo in ("contagem", "limiar", "proporcao") and self.filtro is None:
            raise ValueError(f"regra tipo {self.tipo} exige filtro")
        if self.tipo == "existencia" and not self.campo:
            raise ValueError("regra existencia exige campo")
        if self.tipo == "custom" and not self.funcao:
            raise ValueError("regra custom exige funcao")
        return self


class EvidenciaDef(BaseModel):
    colunas: list[str] = Field(default_factory=list)


class ImpactoItem(BaseModel):
    direto: bool = False
    indireto: bool = False
    ia: bool = False


class ItemChecklist(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=3, max_length=140)
    nome: str
    peso: int = Field(ge=1, le=10)
    prioridade: Prioridade
    implementacao: Literal["obrigatoria", "bom-ter", "nao-essencial"]
    responsavel: list[Literal["dev", "marketing"]]
    impacto: ImpactoItem
    fonte: Fonte
    descricao: str | None = None
    importancia: str | None = None
    regra: RegraItem | None = None
    evidencia: EvidenciaDef | None = None
    categoria: str = ""  # preenchido no load


class CategoriaChecklist(BaseModel):
    categoria: str
    itens: list[ItemChecklist]


class ChecklistSeotec(BaseModel):
    categorias: list[CategoriaChecklist]

    @model_validator(mode="after")
    def _invariantes(self) -> "ChecklistSeotec":
        slugs = [i.slug for c in self.categorias for i in c.itens]
        dup = {s for s in slugs if slugs.count(s) > 1}
        if dup:
            raise ValueError(f"Slugs duplicados no checklist: {dup}")
        total = sum(i.peso for c in self.categorias for i in c.itens)
        if total != TOTAL_PESOS_ESPERADO:
            raise ValueError(f"Soma de pesos {total} != {TOTAL_PESOS_ESPERADO}")
        return self

    def itens(self) -> list[ItemChecklist]:
        return [i for c in self.categorias for i in c.itens]

    def itens_por_slug(self) -> dict[str, ItemChecklist]:
        return {i.slug: i for i in self.itens()}


@lru_cache(maxsize=1)
def carregar_checklist() -> ChecklistSeotec:
    categorias = []
    for arquivo in sorted(CHECKLIST_DIR.glob("*.yaml")):
        raw = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
        cat = CategoriaChecklist(**raw)
        for item in cat.itens:
            item.categoria = cat.categoria
        categorias.append(cat)
    if not categorias:
        raise ValueError(f"Nenhum YAML de checklist em {CHECKLIST_DIR}")
    return ChecklistSeotec(categorias=categorias)


def recarregar_checklist() -> None:
    carregar_checklist.cache_clear()
