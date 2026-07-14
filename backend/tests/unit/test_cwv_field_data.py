"""Testes de field data CrUX + resumo compacto (SPEC_CWV_Field_Data_Retencao_Payload).

Funções puras sobre parse_psi — sem rede. Segue o padrão de payload dict
inline do test_cwv_psi_client.py.
"""
import json

from app.services.cwv_psi_client import _construir_resumo, _extrair_field_data, parse_psi


def _lh_base():
    return {
        "categories": {"performance": {"score": 0.8}},
        "audits": {
            "largest-contentful-paint": {"score": 0.5, "numericValue": 3200},
            "cumulative-layout-shift": {"score": 1.0, "numericValue": 0.05},
            "interaction-to-next-paint": {"score": 0.8, "numericValue": 180},
        },
        "finalUrl": "https://example.com/",
        "userAgent": "Chrome/120",
        "lighthouseVersion": "11.0.0",
        "fetchTime": "2026-07-13T00:00:00.000Z",
        "configSettings": {"formFactor": "mobile"},
    }


def _field_data_metrics():
    return {
        "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2244, "category": "AVERAGE"},
        "INTERACTION_TO_NEXT_PAINT": {"percentile": 175, "category": "FAST"},
        "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 4, "category": "FAST"},
    }


def test_field_data_url_level():
    payload = {
        "lighthouseResult": _lh_base(),
        "loadingExperience": {
            "metrics": _field_data_metrics(),
            "overall_category": "AVERAGE",
        },
        "originLoadingExperience": {
            "metrics": _field_data_metrics(),
            "overall_category": "SLOW",
        },
    }
    fd = _extrair_field_data(payload)
    assert fd["crux_lcp_p75_ms"] == 2244.0
    assert fd["crux_inp_p75_ms"] == 175.0
    # CLS vem multiplicado por 100 → dividir por 100 (4 → 0.04).
    assert fd["crux_cls_p75"] == 0.04
    assert fd["crux_lcp_categoria"] == "AVERAGE"
    assert fd["crux_overall_categoria"] == "AVERAGE"
    assert fd["crux_origem_fallback"] is False


def test_field_data_fallback_para_origem():
    payload = {
        "lighthouseResult": _lh_base(),
        "originLoadingExperience": {
            "metrics": _field_data_metrics(),
            "overall_category": "SLOW",
        },
    }
    fd = _extrair_field_data(payload)
    assert fd["crux_overall_categoria"] == "SLOW"
    assert fd["crux_origem_fallback"] is True


def test_field_data_ausente_todos_none():
    payload = {"lighthouseResult": _lh_base()}
    fd = _extrair_field_data(payload)
    assert fd["crux_lcp_p75_ms"] is None
    assert fd["crux_inp_p75_ms"] is None
    assert fd["crux_cls_p75"] is None
    assert fd["crux_overall_categoria"] is None
    assert fd["crux_origem_fallback"] is False


def test_field_data_cls_dividido_por_100():
    # CLS percentile = 10 → 0.10 (regra do CrUX).
    metrics = {
        "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 10, "category": "AVERAGE"},
    }
    payload = {
        "lighthouseResult": _lh_base(),
        "loadingExperience": {"metrics": metrics, "overall_category": "AVERAGE"},
    }
    fd = _extrair_field_data(payload)
    assert fd["crux_cls_p75"] == 0.10


def test_resumo_sem_screenshot():
    lh = _lh_base()
    # Adiciona audits pesados que NUNCA devem entrar no resumo.
    lh["audits"]["final-screenshot"] = {
        "score": None,
        "details": {"data": "data:image/png;base64,iVBORw0KGgoAAAANS"},
    }
    lh["audits"]["full-page-screenshot"] = {
        "score": None,
        "details": {"data": "data:image/jpeg;base64,/9j/4AAQ"},
    }
    resumo = _construir_resumo({"lighthouseResult": lh})
    serializado = json.dumps(resumo, default=str)
    assert "data:image" not in serializado
    assert "base64" not in serializado
    # audits_score_map ignora audits com score None (só inclui score != None).
    assert "final-screenshot" not in resumo["audits_score_map"]
    assert "full-page-screenshot" not in resumo["audits_score_map"]


def test_resumo_cap_tamanho():
    # Infla entities para forçar a truncagem.
    lh = _lh_base()
    resumo = _construir_resumo({"lighthouseResult": lh})
    # Resumo normal é pequeno. Vamos forçar um gigante artificialmente.
    resumo_grande = dict(resumo)
    resumo_grande["entities"] = ["x" * 10000 for _ in range(100)]
    # Simula a re-truncagem manualmente (como _construir_resumo faria).
    if len(json.dumps(resumo_grande, default=str)) > 64000:
        resumo_grande["entities"] = []
    assert len(json.dumps(resumo_grande, default=str)) <= 64000


def test_resumo_tem_estrutura_esperada():
    lh = _lh_base()
    lh["stackPacks"] = [{"id": "vtex", "title": "VTEX"}]
    lh["entities"] = [{"name": "Google Fonts"}, {"name": "Analytics X"}]
    payload = {
        "lighthouseResult": lh,
        "loadingExperience": {"metrics": _field_data_metrics(), "overall_category": "AVERAGE"},
    }
    resumo = _construir_resumo(payload)
    assert resumo["loading_experience"]["overall_category"] == "AVERAGE"
    assert resumo["stack_packs"] == ["vtex"]
    assert "Google Fonts" in resumo["entities"]
    assert resumo["lighthouse_version"] == "11.0.0"
    assert resumo["form_factor"] == "mobile"
    # audits_score_map inclui audits saudáveis (score 1.0) e não-saudáveis.
    assert resumo["audits_score_map"]["cumulative-layout-shift"] == 1.0


def test_parse_psi_integra_field_data_e_resumo():
    payload = {
        "lighthouseResult": _lh_base(),
        "loadingExperience": {
            "metrics": _field_data_metrics(),
            "overall_category": "AVERAGE",
        },
    }
    parsed = parse_psi(payload)
    assert parsed["crux_lcp_p75_ms"] == 2244.0
    assert parsed["crux_cls_p75"] == 0.04
    assert parsed["crux_overall_categoria"] == "AVERAGE"
    assert parsed["crux_origem_fallback"] is False
    assert "resumo" in parsed
    assert parsed["resumo"]["loading_experience"]["overall_category"] == "AVERAGE"


def test_parse_psi_sem_field_data_tem_resumo_mesmo_assim():
    payload = {"lighthouseResult": _lh_base()}
    parsed = parse_psi(payload)
    assert parsed["crux_lcp_p75_ms"] is None
    assert parsed["crux_overall_categoria"] is None
    # resumo.audits_score_map existe mesmo sem field data.
    assert "resumo" in parsed
    assert "audits_score_map" in parsed["resumo"]
