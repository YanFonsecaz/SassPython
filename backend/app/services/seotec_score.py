"""Health score SEOTEC — fórmula da planilha NPBR (base 940).

Pontua peso do item quando status ∈ {aprovado, na}; qualquer outro status
(ou ausência de status) pontua 0 — idêntico às colunas R/S do Checklist.
"""
from collections import defaultdict

from pydantic import BaseModel, Field

from app.services.seotec_checklist import ChecklistSeotec, TOTAL_PESOS_ESPERADO

STATUS_PONTUA = {"aprovado", "na"}


class ScoreResultado(BaseModel):
    score: float
    pontos: int
    total_pontos: int
    por_prioridade: dict[str, dict[str, int]] = Field(default_factory=dict)
    por_categoria: dict[str, dict] = Field(default_factory=dict)


def calcular_health_score(
    checklist: ChecklistSeotec, statuses: dict[str, str | None]
) -> ScoreResultado:
    pontos = 0
    por_prioridade: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    por_categoria: dict[str, dict] = {}

    for cat in checklist.categorias:
        cat_pontos = 0
        cat_total = 0
        for item in cat.itens:
            status = statuses.get(item.slug)
            cat_total += item.peso
            if status is not None:
                por_prioridade[item.prioridade][status] += 1
            if status in STATUS_PONTUA:
                pontos += item.peso
                cat_pontos += item.peso
        por_categoria[cat.categoria] = {
            "pontos": cat_pontos,
            "total_pontos": cat_total,
            "score": round(cat_pontos / cat_total * 100, 2) if cat_total else 0.0,
        }

    return ScoreResultado(
        score=round(pontos / TOTAL_PESOS_ESPERADO * 100, 2),
        pontos=pontos,
        total_pontos=TOTAL_PESOS_ESPERADO,
        por_prioridade={p: dict(v) for p, v in por_prioridade.items()},
        por_categoria=por_categoria,
    )
