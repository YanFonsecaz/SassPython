from app.services.cwv_psi_client import normalizar_url, parse_psi


def test_parse_psi_extrai_metricas():
    payload = {"lighthouseResult": {
        "categories": {"performance": {"score": 0.62}},
        "audits": {
            "largest-contentful-paint": {"score": 0.5, "numericValue": 4200.0, "scoreDisplayMode": "numeric"},
            "cumulative-layout-shift": {"score": 0.4, "numericValue": 0.18, "scoreDisplayMode": "numeric"},
        },
    }}
    parsed = parse_psi(payload)
    assert parsed["score_performance"] == 62
    assert parsed["lcp_ms"] == 4200.0
    assert parsed["cls"] == 0.18


def test_parse_psi_audits_informativos_excluidos():
    payload = {"lighthouseResult": {
        "categories": {"performance": {"score": 0.5}},
        "audits": {
            "audit-info": {"score": 0.5, "scoreDisplayMode": "informative"},
        },
    }}
    parsed = parse_psi(payload)
    assert all(a["id"] != "audit-info" for a in parsed["audits_falhos"])


def test_parse_psi_audits_notapplicable_excluidos():
    payload = {"lighthouseResult": {
        "categories": {"performance": {"score": 0.5}},
        "audits": {
            "audit-na": {"score": 0.0, "scoreDisplayMode": "notApplicable"},
        },
    }}
    parsed = parse_psi(payload)
    assert len(parsed["audits_falhos"]) == 0


def test_parse_psi_audits_com_score_alto_excluidos():
    payload = {"lighthouseResult": {
        "categories": {"performance": {"score": 0.9}},
        "audits": {
            "good-audit": {"score": 0.95, "numericValue": 100, "scoreDisplayMode": "numeric"},
            "great-audit": {"score": 1.0, "numericValue": 50, "scoreDisplayMode": "numeric"},
        },
    }}
    parsed = parse_psi(payload)
    assert len(parsed["audits_falhos"]) == 0


def test_parse_psi_inp_fallback_mpfid():
    payload = {"lighthouseResult": {
        "categories": {"performance": {"score": 0.5}},
        "audits": {
            "interaction-to-next-paint": {"score": None, "numericValue": None},
            "max-potential-fid": {"score": 0.6, "numericValue": 250, "scoreDisplayMode": "numeric"},
            "largest-contentful-paint": {"score": 0.5, "numericValue": 3000, "scoreDisplayMode": "numeric"},
            "cumulative-layout-shift": {"score": 1.0, "numericValue": 0.01, "scoreDisplayMode": "numeric"},
            "first-contentful-paint": {"score": 1.0, "numericValue": 800, "scoreDisplayMode": "numeric"},
            "server-response-time": {"score": 1.0, "numericValue": 50, "scoreDisplayMode": "numeric"},
            "total-blocking-time": {"score": 1.0, "numericValue": 100, "scoreDisplayMode": "numeric"},
        },
    }}
    parsed = parse_psi(payload)
    assert parsed["inp_ms"] == 250


def test_parse_psi_metricas_nulas():
    payload = {"lighthouseResult": {
        "categories": {"performance": {"score": 0}},
        "audits": {
            "largest-contentful-paint": {"score": None, "numericValue": None},
            "cumulative-layout-shift": {"score": None, "numericValue": None},
            "interaction-to-next-paint": {"score": None, "numericValue": None},
            "first-contentful-paint": {"score": None, "numericValue": None},
            "server-response-time": {"score": None, "numericValue": None},
            "total-blocking-time": {"score": None, "numericValue": None},
        },
    }}
    parsed = parse_psi(payload)
    assert parsed["score_performance"] == 0
    assert parsed["lcp_ms"] is None
    assert parsed["cls"] is None
    assert parsed["inp_ms"] is None


def test_parse_psi_com_fixture_sucesso(psi_payload_sucesso):
    parsed = parse_psi(psi_payload_sucesso)
    assert parsed["score_performance"] == 87
    assert parsed["lcp_ms"] == 3200
    assert parsed["cls"] == 0.02
    assert parsed["inp_ms"] == 150


def test_normalizar_url():
    assert normalizar_url("https://x.com/produto/") == "https://x.com/produto"
    assert normalizar_url("http://EXEMPLO.com/Foo#bar") == "http://exemplo.com/Foo"
    assert normalizar_url("https://x.com") == "https://x.com/"


def test_normalizar_url_com_query():
    assert normalizar_url("https://x.com/page?q=1") == "https://x.com/page?q=1"


def test_normalizar_url_maiusculas():
    assert normalizar_url("https://EXAMPLE.com/Pag") == "https://example.com/Pag"
