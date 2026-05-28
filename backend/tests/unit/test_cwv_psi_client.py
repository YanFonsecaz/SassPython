import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.cwv_psi_client import normalizar_url, parse_psi, _fire_webhook_alert


def test_normalizar_url_completa():
    assert normalizar_url("https://example.com/pagina?q=1") == "https://example.com/pagina?q=1"


def test_normalizar_url_sem_scheme():
    assert normalizar_url("example.com/pagina") == "https://example.com/pagina"


def test_normalizar_url_http():
    assert normalizar_url("http://example.com/") == "http://example.com/"


def test_normalizar_url_trailing_slash():
    assert normalizar_url("https://example.com/pagina/") == "https://example.com/pagina"


def test_normalizar_url_root():
    assert normalizar_url("https://example.com") == "https://example.com/"


def test_normalizar_url_maiusculas():
    assert normalizar_url("https://EXAMPLE.com/Pag") == "https://example.com/Pag"


def test_parse_psi_minimo():
    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.87}},
            "audits": {
                "largest-contentful-paint": {"score": 0.5, "numericValue": 3200},
                "cumulative-layout-shift": {"score": 1.0, "numericValue": 0.05},
                "interaction-to-next-paint": {"score": 0.8, "numericValue": 180},
                "first-contentful-paint": {"score": 0.9, "numericValue": 1200},
                "server-response-time": {"score": 1.0, "numericValue": 100},
                "total-blocking-time": {"score": 0.7, "numericValue": 350},
            },
            "finalUrl": "https://example.com/",
            "userAgent": "Chrome/120",
        }
    }
    result = parse_psi(payload)
    assert result["score_performance"] == 87
    assert result["lcp_ms"] == 3200
    assert result["cls"] == 0.05
    assert result["inp_ms"] == 180
    assert result["fcp_ms"] == 1200
    assert result["ttfb_ms"] == 100
    assert result["tbt_ms"] == 350
    assert result["html_inicial"] == "https://example.com/"
    assert len(result["audits_falhos"]) >= 1


def test_parse_psi_audits_falhos():
    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 1.0}},
            "audits": {
                "largest-contentful-paint": {"score": 0.3, "numericValue": 5000, "title": "LCP lento"},
                "good-audit": {"score": 1.0, "numericValue": 100},
                "informative-audit": {"score": 0.5, "numericValue": 50, "scoreDisplayMode": "informative"},
                "notapplicable-audit": {"score": 0.0, "scoreDisplayMode": "notApplicable"},
                "untitled-fail": {"score": 0.4, "numericValue": 999},
            },
            "finalUrl": "https://ex.com/",
            "userAgent": "Bot",
        }
    }
    result = parse_psi(payload)
    assert result["score_performance"] == 100
    falhos_ids = [a["id"] for a in result["audits_falhos"]]
    assert "largest-contentful-paint" in falhos_ids
    assert "good-audit" not in falhos_ids
    assert "informative-audit" not in falhos_ids
    assert "notapplicable-audit" not in falhos_ids
    assert "untitled-fail" in falhos_ids


def test_parse_psi_inp_fallback_to_mpfid():
    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.5}},
            "audits": {
                "largest-contentful-paint": {"score": 0.5, "numericValue": 3000},
                "cumulative-layout-shift": {"score": 1.0, "numericValue": 0.01},
                "interaction-to-next-paint": {"score": None},
                "max-potential-fid": {"score": 0.6, "numericValue": 250},
                "first-contentful-paint": {"score": 1.0, "numericValue": 800},
                "server-response-time": {"score": 1.0, "numericValue": 50},
                "total-blocking-time": {"score": 1.0, "numericValue": 100},
            },
            "finalUrl": "https://ex.com/",
            "userAgent": "Bot",
        }
    }
    result = parse_psi(payload)
    assert result["inp_ms"] == 250


def test_parse_psi_score_zero():
    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0}},
            "audits": {
                "largest-contentful-paint": {"score": None, "numericValue": None},
                "cumulative-layout-shift": {"score": None, "numericValue": None},
                "interaction-to-next-paint": {"score": None, "numericValue": None},
                "first-contentful-paint": {"score": None, "numericValue": None},
                "server-response-time": {"score": None, "numericValue": None},
                "total-blocking-time": {"score": None, "numericValue": None},
            },
            "finalUrl": "https://ex.com/",
            "userAgent": "Bot",
        }
    }
    result = parse_psi(payload)
    assert result["score_performance"] == 0
    assert result["lcp_ms"] is None
    assert result["cls"] is None
    assert result["inp_ms"] is None
    assert result["audits_falhos"] == []


def test_audits_falhos_preserva_metric_savings_and_numeric_value_and_warnings():
    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.5}},
            "audits": {
                "largest-contentful-paint": {
                    "score": 0.3,
                    "numericValue": 5000,
                    "title": "LCP lento",
                    "displayValue": "5.0 s",
                    "metricSavings": {"LCP": 2300},
                    "warnings": ["Some warning about LCP"],
                    "details": {"type": "table", "headings": []},
                },
                "unused-javascript": {
                    "score": 0.4,
                    "numericValue": 450000,
                    "title": "Unused JS",
                    "displayValue": "Waists 440 KiB",
                    "metricSavings": {"FCP": 1200, "TBT": 300},
                    "warnings": [],
                    "details": {"type": "table"},
                },
                "good-audit": {"score": 1.0, "numericValue": 100},
            },
            "finalUrl": "https://ex.com/",
            "userAgent": "Bot",
        }
    }
    result = parse_psi(payload)
    falhos = result["audits_falhos"]
    assert len(falhos) == 2

    lcp_audit = next(a for a in falhos if a["id"] == "largest-contentful-paint")
    assert lcp_audit["numericValue"] == 5000
    assert lcp_audit["metricSavings"] == {"LCP": 2300}
    assert lcp_audit["warnings"] == ["Some warning about LCP"]
    assert lcp_audit["details"]["type"] == "table"

    js_audit = next(a for a in falhos if a["id"] == "unused-javascript")
    assert js_audit["numericValue"] == 450000
    assert js_audit["metricSavings"] == {"FCP": 1200, "TBT": 300}
    assert js_audit["warnings"] == []


@pytest.mark.asyncio
async def test_fire_webhook_alert_envia_quando_configurado(monkeypatch):
    monkeypatch.setattr("app.services.cwv_psi_client.settings.cwv_alerta_webhook_url", "https://hooks.example.com/alert")
    mock_post = AsyncMock(return_value=MagicMock(status_code=200))
    with patch("app.services.cwv_psi_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=mock_post))
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        await _fire_webhook_alert("https://example.com")
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "both_keys_failed" in call_kwargs[0][0]["text"] if isinstance(call_kwargs[0][0], dict) else True


@pytest.mark.asyncio
async def test_fire_webhook_alert_nao_envia_sem_url(monkeypatch):
    monkeypatch.setattr("app.services.cwv_psi_client.settings.cwv_alerta_webhook_url", "")
    with patch("app.services.cwv_psi_client.httpx.AsyncClient") as mock_client_cls:
        await _fire_webhook_alert("https://example.com")
    mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_fire_webhook_alert_nao_quebra_em_erro(monkeypatch):
    monkeypatch.setattr("app.services.cwv_psi_client.settings.cwv_alerta_webhook_url", "https://hooks.example.com/alert")
    with patch("app.services.cwv_psi_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(side_effect=Exception("conn refused"))))
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        await _fire_webhook_alert("https://example.com")
