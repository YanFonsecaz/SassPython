"""Health Score de uma execução CWV.

Regra portada da planilha NPBR (``Checklist!B2 = H2/G2*100``): proporção de
audits saudáveis sobre o total de audits com score das análises de sucesso.

Desde a paridade total PSI (``SPEC_CWV_Paridade_Total_PSI``), problemas ≈
audits falhos 1:1, então ``n_problemas`` da análise é um proxy fiel de
"audits Fail" — logo ``n_pass = audits_totais - n_problemas``.
"""

from __future__ import annotations


def calcular_health_score(analises: list[dict]) -> dict | None:
    """Calcula o health score agregado de uma execução.

    Entrada: lista de dicts com ao menos ``status``, ``estrategia``,
    ``audits_totais`` e ``n_problemas`` (o chamador fornece — ver
    ``cwv_persistencia.contar_problemas_por_analise``).

    Considera apenas análises ``status == "sucesso"`` com
    ``audits_totais > 0``. Se nenhuma qualificar, retorna ``None`` (a
    execução não tem score significativo — ex.: todas falharam no PSI).
    """
    qualificadas = [
        a for a in analises
        if a.get("status") == "sucesso" and (a.get("audits_totais") or 0) > 0
    ]
    if not qualificadas:
        return None

    n_pass = sum(
        max(int(a.get("audits_totais") or 0) - int(a.get("n_problemas") or 0), 0)
        for a in qualificadas
    )
    n_total = sum(int(a.get("audits_totais") or 0) for a in qualificadas)
    if n_total <= 0:
        return None

    health = round(100 * n_pass / n_total, 1)

    por_estrategia: dict[str, float] = {}
    for estrategia in ("mobile", "desktop"):
        subset = [a for a in qualificadas if a.get("estrategia") == estrategia]
        if not subset:
            continue
        pass_est = sum(
            max(int(a.get("audits_totais") or 0) - int(a.get("n_problemas") or 0), 0)
            for a in subset
        )
        total_est = sum(int(a.get("audits_totais") or 0) for a in subset)
        if total_est > 0:
            por_estrategia[estrategia] = round(100 * pass_est / total_est, 1)

    return {
        "health_score": health,
        "n_pass": n_pass,
        "n_total": n_total,
        "por_estrategia": por_estrategia,
    }
