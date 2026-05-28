import pytest

from app.agents.cwv.analisador import (
    CWVAnalisadorAgent,
    ProblemaIdentificado,
    _extrair_contexto,
    _formatar_audit_para_prompt,
    _montar_prompt_analise,
    _resumir_items,
)
from app.services.cwv_kb import AUDITS_IGNORADOS


@pytest.fixture
def sample_audit():
    return {
        "id": "unused-javascript",
        "title": "Remove unused JavaScript",
        "description": "Remove unused JavaScript to reduce bytes consumed by network activity.",
        "score": 0.5,
        "displayValue": "450 ms",
        "scoreDisplayMode": "numeric",
        "numericValue": 450,
        "numericUnit": "millisecond",
        "details": {
            "type": "opportunity",
            "overallSavingsMs": 1200,
            "overallSavingsBytes": 50000,
            "items": [
                {
                    "url": "https://example.com/static/app.js",
                    "wastedBytes": 30000,
                    "wastedMs": 800,
                    "node": {"selector": "head > script[src*='app.js']"},
                },
                {
                    "url": "https://example.com/static/vendor.js",
                    "wastedBytes": 20000,
                    "wastedMs": 400,
                    "node": {"selector": "head > script[src*='vendor.js']"},
                },
            ],
        },
        "warnings": ["Some scripts may be loaded dynamically"],
    }


@pytest.fixture
def sample_informative_audit():
    return {
        "id": "largest-contentful-paint-element",
        "title": "Largest Contentful Paint element",
        "description": "This is the largest contentful element painted within the viewport.",
        "score": None,
        "displayValue": "",
        "scoreDisplayMode": "informative",
        "numericValue": None,
        "numericUnit": "",
        "details": {
            "type": "table",
            "items": [
                {
                    "node": {"selector": "main > section.hero > img"},
                    "url": "https://example.com/hero.jpg",
                }
            ],
        },
        "warnings": [],
    }


def test_extrair_contexto_includes_all_fields(sample_audit):
    ctx = _extrair_contexto(sample_audit)

    assert ctx["title"] == "Remove unused JavaScript"
    assert ctx["description"] == "Remove unused JavaScript to reduce bytes consumed by network activity."
    assert ctx["score"] == 0.5
    assert ctx["score_display_mode"] == "numeric"
    assert ctx["numeric_value"] == 450
    assert ctx["numeric_unit"] == "millisecond"
    assert ctx["details_type"] == "opportunity"
    assert ctx["savings_ms"] == 1200
    assert ctx["savings_bytes"] == 50000
    assert ctx["warnings"] == ["Some scripts may be loaded dynamically"]
    assert len(ctx["items"]) == 2


def test_extrair_contexto_informative_audit(sample_informative_audit):
    ctx = _extrair_contexto(sample_informative_audit)

    assert ctx["score"] is None
    assert ctx["score_display_mode"] == "informative"
    assert ctx["numeric_value"] is None
    assert ctx["details_type"] == "table"
    assert ctx["savings_ms"] is None
    assert ctx["savings_bytes"] is None
    assert ctx["warnings"] == []


def test_extrair_contexto_handles_missing_details():
    audit = {"id": "foo", "title": "Foo"}
    ctx = _extrair_contexto(audit)

    assert ctx["title"] == "Foo"
    assert ctx["details_type"] is None
    assert ctx["savings_ms"] is None
    assert ctx["items"] == []


def test_resumir_items_extracts_compact_data():
    items = [
        {
            "url": "https://example.com/app.js",
            "wastedBytes": 30000,
            "wastedMs": 800,
            "node": {"selector": "head > script"},
            "label": "app.js",
        },
        {"url": "https://example.com/image.png", "totalBytes": 500000, "transferSize": 300000},
        {},
    ]
    result = _resumir_items(items)

    assert len(result) == 2
    assert result[0]["url"] == "https://example.com/app.js"
    assert result[0]["selector"] == "head > script"
    assert result[0]["label"] == "app.js"
    assert result[0]["wastedBytes"] == 30000
    assert result[0]["wastedMs"] == 800
    assert result[1]["url"] == "https://example.com/image.png"
    assert result[1]["totalBytes"] == 500000
    assert result[1]["transferSize"] == 300000


def test_resumir_items_truncates_long_values():
    items = [
        {
            "url": "x" * 600,
            "node": {"selector": "y" * 400},
            "label": "z" * 300,
        }
    ]
    result = _resumir_items(items)

    assert len(result[0]["url"]) == 500
    assert len(result[0]["selector"]) == 300
    assert len(result[0]["label"]) == 200


def test_resumir_items_skips_empty_dicts():
    result = _resumir_items([{}])
    assert result == []


def test_resumir_items_skips_items_with_no_relevant_fields():
    result = _resumir_items([{"foo": "bar"}])
    assert result == []


def test_formatar_audit_para_prompt_opportunity(sample_audit):
    text = _formatar_audit_para_prompt(sample_audit)

    assert "### audit: unused-javascript" in text
    assert "Remove unused JavaScript" in text
    assert "1200ms" in text
    assert "opportunity" in text
    assert "head > script" in text
    assert "app.js" in text
    assert "Some scripts may be loaded dynamically" in text


def test_formatar_audit_para_prompt_informative(sample_informative_audit):
    text = _formatar_audit_para_prompt(sample_informative_audit)

    assert "### audit: largest-contentful-paint-element" in text
    assert "audit informativo, sem savings" in text
    assert "main > section.hero > img" in text
    assert "hero.jpg" in text


def test_montar_prompt_includes_kb_descriptions():
    kb_descritos = [
        {
            "codigo": "js-bundle-grande",
            "titulo": "Bundle JavaScript excessivamente grande",
            "descricao_curta": "JS grande causa INP e TBT ruins",
            "metricas_afetadas": ["INP", "TBT"],
        },
        {
            "codigo": "outros",
            "titulo": "Audit nao catalogado",
            "descricao_curta": "Nao se encaixa em nenhum outro codigo",
            "metricas_afetadas": ["LCP", "CLS", "INP", "TBT", "FCP", "TTFB"],
        },
    ]
    audits = [
        {
            "id": "test-audit",
            "title": "Test Audit",
            "description": "Test description",
            "score": 0.3,
            "displayValue": "100 ms",
            "scoreDisplayMode": "numeric",
            "numericValue": 100,
            "numericUnit": "millisecond",
            "details": {"type": "opportunity", "overallSavingsMs": 500},
        }
    ]
    metricas = {"lcp_ms": 5000, "cls": 0.1, "inp_ms": 200, "fcp_ms": 2000, "ttfb_ms": 300, "tbt_ms": 600}

    prompt = _montar_prompt_analise(audits, kb_descritos, "shopify", metricas)

    assert "Plataforma: shopify" in prompt
    assert "LCP=5000ms" in prompt
    assert "js-bundle-grande — Bundle JavaScript excessivamente grande (INP, TBT)" in prompt
    assert "outros — Audit nao catalogado (LCP, CLS, INP, TBT, FCP, TTFB)" in prompt
    assert "### audit: test-audit" in prompt
    assert "Test description" in prompt
    assert "500ms" in prompt
    assert "savings_ms" in prompt.lower() or "ganho potencial" in prompt.lower()
    assert "use APENAS estes codigos" in prompt
    assert ">500ms" in prompt


def test_montar_prompt_no_kb():
    prompt = _montar_prompt_analise([], [], "geral", {"lcp_ms": 0, "cls": 0, "inp_ms": 0, "fcp_ms": 0, "ttfb_ms": 0, "tbt_ms": 0})

    assert "Plataforma: geral" in prompt
    assert "## Base de conhecimento" in prompt
    assert "## Audits falhos" in prompt


def test_extrair_contexto_items_with_non_dict_node():
    audit = {
        "id": "test",
        "title": "Test",
        "details": {
            "type": "table",
            "items": [
                {"url": "https://example.com", "node": "not a dict"},
            ],
        },
    }
    ctx = _extrair_contexto(audit)
    assert len(ctx["items"]) == 1
    assert ctx["items"][0]["url"] == "https://example.com"
    assert "selector" not in ctx["items"][0]


def test_analisador_uses_dedicated_llm_model(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "cwv_analisador_llm_model", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "cwv_analisador_llm_temperature", 0.1)
    monkeypatch.setattr(settings, "openai_api_key", "fake-key")

    agent = CWVAnalisadorAgent(usuario_id="test-user")
    assert agent.llm.model_name == "gpt-4.1-mini"
    assert agent.llm.temperature == 0.1


def test_analisador_uses_dedicated_temperature_default():
    from app.config import settings

    assert settings.cwv_analisador_llm_temperature == 0.1
    assert settings.cwv_analisador_llm_model == "gpt-4o-mini"


def test_analisador_no_override_when_not_openai(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "zhipuai")
    monkeypatch.setattr(settings, "cwv_analisador_llm_model", "gpt-4.1-mini")

    agent = CWVAnalisadorAgent(usuario_id="test-user")
    assert agent.llm.model_name != "gpt-4.1-mini"


def test_problema_identificado_kb_codigo_nullable():
    p = ProblemaIdentificado(kb_codigo=None, audit_id="some-audit")
    assert p.kb_codigo is None
    assert p.audit_id == "some-audit"


def test_problema_identificado_with_kb_codigo():
    p = ProblemaIdentificado(kb_codigo="js-duplicado", audit_id="duplicated-javascript")
    assert p.kb_codigo == "js-duplicado"
    assert p.audit_id == "duplicated-javascript"


def test_problema_identificado_model_dump_includes_none():
    p = ProblemaIdentificado(kb_codigo=None, audit_id="x")
    d = p.model_dump()
    assert d["kb_codigo"] is None
    assert d["audit_id"] == "x"


def test_montar_prompt_no_consolidation_instruction():
    kb_descritos = [
        {"codigo": "js-bundle-grande", "titulo": "Bundle grande", "descricao_curta": "JS grande", "metricas_afetadas": ["INP"]},
    ]
    audits = [
        {"id": "a1", "title": "A1", "description": "d", "score": 0.5, "displayValue": "100ms", "scoreDisplayMode": "numeric", "numericValue": 100, "numericUnit": "ms", "details": {"type": "opportunity", "overallSavingsMs": 500}},
        {"id": "a2", "title": "A2", "description": "d2", "score": 0.3, "displayValue": "200ms", "scoreDisplayMode": "numeric", "numericValue": 200, "numericUnit": "ms", "details": {"type": "opportunity", "overallSavingsMs": 300}},
    ]
    metricas = {"lcp_ms": 5000, "cls": 0.1, "inp_ms": 200, "fcp_ms": 2000, "ttfb_ms": 300, "tbt_ms": 600}
    prompt = _montar_prompt_analise(audits, kb_descritos, "geral", metricas)
    assert "CADA audit" in prompt
    assert "1:1" in prompt


def test_speed_index_not_ignored():
    assert "speed-index" not in AUDITS_IGNORADOS


def test_lcp_not_ignored():
    assert "largest-contentful-paint" not in AUDITS_IGNORADOS


def test_interactive_not_ignored():
    assert "interactive" not in AUDITS_IGNORADOS


def test_cls_not_ignored():
    assert "cumulative-layout-shift" not in AUDITS_IGNORADOS
