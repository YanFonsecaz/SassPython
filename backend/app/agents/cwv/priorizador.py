PESO_METRICA: dict[str, int] = {
    "LCP": 5,
    "CLS": 4,
    "INP": 4,
    "TBT": 3,
    "FCP": 2,
    "TTFB": 2,
}


def priorizar_problemas(problemas: list[dict], metricas: dict | None = None) -> list[dict]:
    def score(p: dict) -> float:
        peso = sum(PESO_METRICA.get(m, 1) for m in p.get("metricas_afetadas", []))
        severidade = p.get("severidade", 1)
        return severidade * peso

    ordenados = sorted(problemas, key=score, reverse=True)
    for i, p in enumerate(ordenados):
        p["prioridade_ordem"] = i + 1
    return ordenados
