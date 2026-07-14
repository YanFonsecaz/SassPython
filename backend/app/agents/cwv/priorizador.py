"""Priorização e esforço dos problemas CWV.

``priorizar_problemas`` ordena por severidade x soma dos pesos das métricas afetadas
(não alterado por ``SPEC_CWV_Estimador_Esforco``). ``estimar_esforco`` classifica
cada problema em baixo/médio/alto de forma determinística por ``kb_codigo``,
com fallback por família de ``audit_id`` quando não há KB.

Escala:
- **baixo**: config/atributo/plugin — sem refactor de código.
- **médio**: mexe em tema/infra pontual.
- **alto**: refactor de código/arquitetura.

Ajuste fino contextual (LLM) não vive aqui — vai no consolidador
(``SPEC_CWV_Consolidador_Cross_URL``); aqui é só classificação estável.
"""

PESO_METRICA: dict[str, int] = {
    "LCP": 5,
    "CLS": 4,
    "INP": 4,
    "TBT": 3,
    "FCP": 2,
    "TTFB": 2,
}


# Mapa determinístico kb_codigo -> esforço. DEVE cobrir todos os códigos reais
# em app/data/cwv_knowledge_base.yaml — o teste de completude
# (test_cwv_priorizador::test_esforco_cobre_toda_kb) é o guarda. Se a KB ganhar
# entrada, adicione aqui antes de commitar.
ESFORCO_POR_KB: dict[str, str] = {
    # baixo: config/atributo/plugin — sem refactor de código
    "imagens-formato-moderno": "baixo",
    "imagens-tamanho-correto": "baixo",
    "imagens-offscreen": "baixo",
    "lcp-imagem-lazy-load": "baixo",
    "lcp-imagem-sem-dimensoes": "baixo",
    "lcp-imagem-grande": "baixo",
    "cls-imagem-sem-dimensoes-cls": "baixo",
    "lcp-preload-faltando": "baixo",
    "preconnect-origens": "baixo",
    "ttfb-compress-faltando": "baixo",
    "cache-headers-inadequados": "baixo",
    "js-nao-minificado": "baixo",
    "viewport-faltando": "baixo",
    "https-redirecionamento": "baixo",
    "document-write-evitado": "baixo",
    "js-passive-listeners-faltando": "baixo",
    "user-timing": "baixo",
    "eficiente-conteudo-animado": "baixo",
    "meta-description-faltando": "baixo",
    "imagens-sem-alt": "baixo",
    # médio: mexe em tema/infra pontual
    "lcp-fonte-bloqueante": "medio",
    "cls-fonte-web-flash": "medio",
    "fcp-render-blocking": "medio",
    "lcp-css-bloqueante": "medio",
    "recurso-render-blocking-extra": "medio",
    "lcp-script-no-head": "medio",
    "ttfb-sem-cache-cdn": "medio",
    "ttfb-redirect-chain": "medio",
    "servidor-tempo-resposta-lento": "medio",
    "lcp-ttfb-alto": "medio",
    "https-mixed-content": "medio",
    "cls-iframe-sem-dimensoes": "medio",
    "cls-ad-injetado": "medio",
    "polyfill-desnecessario": "medio",
    "js-duplicado": "medio",
    "prioridade-recursos": "medio",
    "cls-animacao-sem-transform": "medio",
    "animacoes-nao-compositadas": "medio",
    "fcp-critical-path-longo": "medio",
    "cookies-thirdparty": "medio",
    "bf-cache-nao-elegivel": "medio",
    "performance-budget": "medio",
    "service-worker-sem-estrategia-cache": "medio",
    # alto: refactor de código/arquitetura
    "js-bundle-grande": "alto",
    "js-bloqueante-thirdparty": "alto",
    "js-long-task": "alto",
    "js-execucao-pesada-no-load": "alto",
    "dom-muito-grande": "alto",
    "dom-profundidade-alta": "alto",
    "event-handler-pesado": "alto",
    "cls-conteudo-injetado-dinamicamente": "alto",
    # informativos/genéricos
    "metrica-lcp-info": "medio",
    "metrica-fcp-info": "medio",
    "metrica-tti-info": "medio",
    "metrica-si-info": "medio",
    "metrica-inp-info": "medio",
    "outros": "medio",
}

# Fallback por substring do audit_id (primeiro match vence). Usado quando o
# problema não tem kb_codigo (cauda longa pesquisada) mas tem audit_id de
# família conhecida.
FALLBACK_FAMILIA: list[tuple[str, str]] = [
    ("image", "baixo"),
    ("cache", "baixo"),
    ("compression", "baixo"),
    ("font", "medio"),
    ("css", "medio"),
    ("redirect", "medio"),
    ("preconnect", "baixo"),
    ("preload", "baixo"),
    ("viewport", "baixo"),
    ("server", "medio"),
    ("third-party", "medio"),
    ("javascript", "alto"),
    ("script", "alto"),
    ("dom", "alto"),
]


def estimar_esforco(kb_codigo: str | None, audit_id: str | None) -> str | None:
    """Classifica esforço em ``baixo``/``medio``/``alto`` ou ``None``.

    1. Se ``kb_codigo`` está no mapa → valor do mapa.
    2. Senão, se ``audit_id`` casa uma família conhecida → fallback.
    3. Senão → ``None`` (sem classificar).
    """
    if kb_codigo and kb_codigo in ESFORCO_POR_KB:
        return ESFORCO_POR_KB[kb_codigo]
    if audit_id:
        aid = audit_id.lower()
        for substring, esforco in FALLBACK_FAMILIA:
            if substring in aid:
                return esforco
    return None


def priorizar_problemas(problemas: list[dict], metricas: dict | None = None) -> list[dict]:
    def score(p: dict) -> float:
        peso = sum(PESO_METRICA.get(m, 1) for m in p.get("metricas_afetadas", []))
        severidade = p.get("severidade", 1)
        return severidade * peso

    ordenados = sorted(problemas, key=score, reverse=True)
    for i, p in enumerate(ordenados):
        p["prioridade_ordem"] = i + 1
        p["esforco"] = estimar_esforco(p.get("kb_codigo"), p.get("audit_id"))
    return ordenados
