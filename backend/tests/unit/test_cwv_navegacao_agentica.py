"""Testes SPEC_CWV_Navegacao_Agentica: check_llms_txt, PSI accessibility,
grupo agêntico do checklist."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services import cwv_page_experience as pe
from app.services.cwv_auditoria_service import _itens_agentic
from app.services.cwv_page_experience import check_llms_txt
from app.services.cwv_psi_client import parse_psi


# --- check_llms_txt -------------------------------------------------------


def _fake_client(status_code: int, text: str = "", content_type: str = "text/plain"):
    class FakeResp:
        def __init__(self):
            self.status_code = status_code
            self.headers = {"content-type": content_type}
            self.text = text

    class FakeClient:
        is_closed = False

        async def get(self, url):
            return FakeResp()

    return FakeClient()


def test_llms_txt_200_com_h1_pass(monkeypatch):
    monkeypatch.setattr(pe, "_CLIENT", _fake_client(200, "# Meu site\n\nDescrição para agentes."))
    v, _ = asyncio.run(check_llms_txt("https://ex.com"))
    assert v == "pass"


def test_llms_txt_200_sem_h1_fail(monkeypatch):
    monkeypatch.setattr(pe, "_CLIENT", _fake_client(200, "Sem heading H1\n## Subtítulo"))
    v, det = asyncio.run(check_llms_txt("https://ex.com"))
    assert v == "fail"
    assert "H1" in det["motivo"]


def test_llms_txt_404_fail(monkeypatch):
    monkeypatch.setattr(pe, "_CLIENT", _fake_client(404))
    v, det = asyncio.run(check_llms_txt("https://ex.com"))
    assert v == "fail"
    assert "ausente" in det["motivo"]


def test_llms_txt_nao_textual_fail(monkeypatch):
    monkeypatch.setattr(pe, "_CLIENT", _fake_client(200, "# H1", content_type="application/octet-stream"))
    v, _ = asyncio.run(check_llms_txt("https://ex.com"))
    assert v == "fail"


def test_llms_txt_waf_na(monkeypatch):
    monkeypatch.setattr(pe, "_CLIENT", _fake_client(403))
    v, _ = asyncio.run(check_llms_txt("https://ex.com"))
    assert v == "na"


# --- PSI accessibility ----------------------------------------------------


def _payload_com_a11y():
    return {
        "lighthouseResult": {
            "categories": {
                "performance": {
                    "score": 0.9,
                    "auditRefs": [
                        {"id": "largest-contentful-paint"},
                        {"id": "cumulative-layout-shift"},
                    ],
                },
                "accessibility": {"score": 0.85, "auditRefs": [{"id": "color-contrast"}]},
            },
            "audits": {
                "largest-contentful-paint": {"score": 0.4, "numericValue": 5000, "title": "LCP"},
                "cumulative-layout-shift": {"score": 1.0, "numericValue": 0.05},
                "color-contrast": {"score": 0.0, "title": "Contraste", "scoreDisplayMode": "binary"},
            },
            "finalUrl": "https://ex.com/",
        }
    }


def test_parse_psi_accessibility_score_no_resumo():
    r = parse_psi(_payload_com_a11y())
    assert r["resumo"]["accessibility_score"] == 0.85


def test_parse_psi_a11y_audit_nao_polui_pipeline():
    r = parse_psi(_payload_com_a11y())
    falhos = [a["id"] for a in r["audits_falhos"]]
    assert "largest-contentful-paint" in falhos
    # audit de a11y (fora dos auditRefs de performance) não vira problema
    assert "color-contrast" not in falhos
    assert "color-contrast" not in r["resumo"]["audits_score_map"]


def test_parse_psi_sem_auditrefs_mantem_tudo():
    """Fallback: payload antigo sem auditRefs → comportamento pré-mudança."""
    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.5}},
            "audits": {"largest-contentful-paint": {"score": 0.3, "numericValue": 5000, "title": "LCP"}},
            "finalUrl": "https://ex.com/",
        }
    }
    r = parse_psi(payload)
    assert "largest-contentful-paint" in [a["id"] for a in r["audits_falhos"]]
    assert r["resumo"]["accessibility_score"] is None


# --- checklist agêntico ---------------------------------------------------


def _analise(acc_score):
    a = MagicMock()
    a.raw_resumo_json = {"accessibility_score": acc_score} if acc_score is not None else {}
    return a


def _session_page_experience(rows):
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


def test_itens_agentic_acessibilidade_pass_e_webmcp():
    session = _session_page_experience([])  # sem page_experience → sem agentic_llms_txt
    itens = asyncio.run(_itens_agentic(session, "exec-1", "aud-1", [_analise(0.95), _analise(0.92)]))
    codigos = {i.item_codigo: i.status_before for i in itens}
    assert codigos["agentic_acessibilidade"] == "pass"
    assert codigos["manual_webmcp_forms"] == "na"
    assert codigos["manual_webmcp_tools"] == "na"
    assert codigos["manual_webmcp_schemas"] == "na"
    assert "agentic_llms_txt" not in codigos
    assert all(i.origem == "agentic" for i in itens)


def test_itens_agentic_acessibilidade_fail():
    session = _session_page_experience([])
    itens = asyncio.run(_itens_agentic(session, "e", "a", [_analise(0.95), _analise(0.85)]))
    codigos = {i.item_codigo: i.status_before for i in itens}
    assert codigos["agentic_acessibilidade"] == "fail"


def test_itens_agentic_acessibilidade_na_sem_dado():
    session = _session_page_experience([])
    itens = asyncio.run(_itens_agentic(session, "e", "a", [_analise(None)]))
    codigos = {i.item_codigo: i.status_before for i in itens}
    assert codigos["agentic_acessibilidade"] == "na"


def test_itens_agentic_llms_txt_pior_veredito():
    row_ok = MagicMock(); row_ok.llms_txt = "pass"
    row_fail = MagicMock(); row_fail.llms_txt = "fail"
    session = _session_page_experience([row_ok, row_fail])
    itens = asyncio.run(_itens_agentic(session, "e", "a", []))
    codigos = {i.item_codigo: i.status_before for i in itens}
    assert codigos["agentic_llms_txt"] == "fail"  # pior entre origens
