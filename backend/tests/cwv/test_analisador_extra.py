"""Testes do _resumir_items e AUDIT_ALIASES introduzidos nas SPECs #17/#18."""


def test_resumir_items_sem_limite_de_quantidade():
    """SPEC #18: items sem cap (antes era 5, depois 30, agora ilimitado)."""
    from app.agents.cwv.analisador import _resumir_items

    items = [{"url": f"https://x.com/{i}", "totalBytes": 1000} for i in range(60)]
    resumo = _resumir_items(items)
    assert len(resumo) == 60


def test_resumir_items_preserva_sub_items_aninhados():
    """SPEC #18: legacy-javascript-insight tem sub_items (estilo Facebook/Babel)."""
    from app.agents.cwv.analisador import _resumir_items

    items = [{
        "url": "https://connect.facebook.net/config/824",
        "totalBytes": 22500,
        "subItems": {
            "items": [
                {"signal": "@babel/plugin-transform-classes"},
                {"signal": "Array.from"},
                {"signal": "Object.create"},
            ],
        },
    }]
    resumo = _resumir_items(items)
    assert len(resumo) == 1
    assert "sub_items" in resumo[0]
    signals = [s["signal"] for s in resumo[0]["sub_items"]]
    assert "@babel/plugin-transform-classes" in signals
    assert "Object.create" in signals


def test_resumir_items_preserva_campos_ricos_spec18():
    """SPEC #18: group_label, wastedPercent, cacheLifetimeMs, nodeLabel."""
    from app.agents.cwv.analisador import _resumir_items

    items = [
        {"group": "scriptEvaluation", "groupLabel": "Script Evaluation", "duration": 1500},
        {"url": "https://x.com/a.js", "wastedBytes": 1000, "totalBytes": 2000, "wastedPercent": 50.0},
        {"url": "https://x.com/img.png", "cacheLifetimeMs": 604800000, "totalBytes": 3000},
        {"node": {"selector": "#hero", "nodeLabel": "Hero image", "snippet": "<img src='hero.png'>"}},
    ]
    resumo = _resumir_items(items)
    assert resumo[0]["group_label"] == "Script Evaluation"
    assert resumo[0]["group"] == "scriptEvaluation"
    assert resumo[1]["wastedPercent"] == 50.0
    assert resumo[2]["cacheLifetimeMs"] == 604800000
    assert resumo[3]["node_label"] == "Hero image"
    assert resumo[3]["selector"] == "#hero"


def test_audit_aliases_mapeia_insight_para_kb_classica():
    """SPEC #17: AUDIT_ALIASES traduz IDs *-insight novos para entradas KB existentes."""
    from app.services.cwv_kb import AUDIT_ALIASES, mapeamento_audit_kb_com_aliases

    assert "image-delivery-insight" in AUDIT_ALIASES
    assert "cache-insight" in AUDIT_ALIASES
    assert "render-blocking-insight" in AUDIT_ALIASES
    assert "font-display-insight" in AUDIT_ALIASES

    mapa = mapeamento_audit_kb_com_aliases()
    assert mapa.get("image-delivery-insight"), "image-delivery-insight nao mapeia para KB via alias"
    assert mapa.get("cache-insight")
    assert mapa.get("render-blocking-insight")
    assert mapa.get("font-display-insight")


def test_extrair_contexto_inclui_headings_e_metric_savings():
    """SPEC #18: headings (cols) + metric_savings (LCP/INP/TBT) preservados."""
    from app.agents.cwv.analisador import _extrair_contexto

    audit = {
        "title": "Reduce unused JS",
        "displayValue": "Est savings of 500 KiB",
        "metricSavings": {"LCP": 1200, "TBT": 400},
        "details": {
            "type": "opportunity",
            "items": [],
            "overallSavingsBytes": 500000,
            "headings": [
                {"key": "url", "label": "URL", "valueType": "url"},
                {"key": "wastedBytes", "label": "Bytes desperdiçados", "valueType": "bytes"},
            ],
        },
    }
    ctx = _extrair_contexto(audit)
    assert ctx["metric_savings"] == {"LCP": 1200, "TBT": 400}
    assert len(ctx["headings"]) == 2
    assert ctx["headings"][0]["label"] == "URL"


def test_severidade_por_savings_escalas():
    """Severidade ordena criticos antes de informativos."""
    from app.agents.cwv.documentador import _severidade_por_savings

    assert _severidade_por_savings(1500, None) == 5  # > 1000ms
    assert _severidade_por_savings(600, None) == 4   # >= 500ms
    assert _severidade_por_savings(300, None) == 3
    assert _severidade_por_savings(80, None) == 2
    assert _severidade_por_savings(None, None) == 1  # sem savings
    assert _severidade_por_savings(None, 250 * 1024) == 5  # >= 200 KiB
