"""Testes de Page Experience (SPEC_CWV_Page_Experience).

Funções puras + checks sem rede (mixed content, mobile friendly) e safe browsing
sem key. Zero rede real — usa monkeypatch nos checks que precisariam de httpx.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services.cwv_page_experience import (
    _origem,
    auditar_origem,
    check_mixed_content,
    check_mobile_friendly,
    check_redirect_301,
    check_safe_browsing,
    check_security_headers,
)


def test_origem_extrai_scheme_host():
    assert _origem("https://www.exemplo.com/pagina?q=1") == "https://www.exemplo.com"
    assert _origem("http://exemplo.com:8080/x") == "http://exemplo.com:8080"


def _payload_mobile_final(final_url, network_items=None, viewport_score=None):
    audits = {}
    if network_items is not None:
        audits["network-requests"] = {"details": {"items": network_items}}
    if viewport_score is not None:
        audits["viewport"] = {"score": viewport_score}
    return {
        "lighthouseResult": {
            "finalUrl": final_url,
            "configSettings": {"formFactor": "mobile"},
            "audits": audits,
        }
    }


def test_mixed_content_detecta_recurso_http():
    payload = _payload_mobile_final(
        "https://exemplo.com/",
        network_items=[
            {"url": "http://exemplo.com/inseguro.js"},
            {"url": "https://exemplo.com/seguro.js"},
        ],
    )
    v, detalhes = asyncio.run(check_mixed_content([payload]))
    assert v == "fail"
    assert "http://exemplo.com/inseguro.js" in detalhes["mixed_content"]


def test_mixed_content_sem_recurso_http_pass():
    payload = _payload_mobile_final(
        "https://exemplo.com/",
        network_items=[{"url": "https://exemplo.com/seguro.js"}],
    )
    v, _ = asyncio.run(check_mixed_content([payload]))
    assert v == "pass"


def test_mixed_content_pagina_http_ignora():
    # Página final http:// — mixed content não aplica.
    payload = _payload_mobile_final(
        "http://exemplo.com/",
        network_items=[{"url": "http://exemplo.com/x.js"}],
    )
    v, _ = asyncio.run(check_mixed_content([payload]))
    assert v == "pass"


def test_mobile_friendly_score_1_pass():
    payload = _payload_mobile_final("https://exemplo.com/", viewport_score=1)
    v, detalhes = asyncio.run(check_mobile_friendly([payload]))
    assert v == "pass"
    assert detalhes["scores"] == [1.0]


def test_mobile_friendly_score_0_fail():
    payload = _payload_mobile_final("https://exemplo.com/", viewport_score=0)
    v, _ = asyncio.run(check_mobile_friendly([payload]))
    assert v == "fail"


def test_mobile_friendly_sem_viewport_na():
    payload = _payload_mobile_final("https://exemplo.com/")  # sem viewport
    v, _ = asyncio.run(check_mobile_friendly([payload]))
    assert v == "na"


def test_safe_browsing_sem_key_e_na(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_safe_browsing_key", "")
    v, detalhes = asyncio.run(check_safe_browsing("https://exemplo.com/"))
    assert v == "na"
    assert detalhes == {}


def test_security_headers_completo_pass(monkeypatch):
    """Mocka o cliente httpx para responder com headers completos."""
    from app.services import cwv_page_experience as pe

    class FakeResp:
        headers = {
            "strict-transport-security": "max-age=31536000",
            "content-security-policy": "default-src 'self'",
            "x-content-type-options": "nosniff",
        }
        status_code = 200

    class FakeClient:
        is_closed = False

        async def get(self, url):
            return FakeResp()

    monkeypatch.setattr(pe, "_CLIENT", FakeClient())
    v, detalhes = asyncio.run(check_security_headers("https://exemplo.com/"))
    assert v == "pass"
    assert "strict-transport-security" in detalhes["presentes"]


def test_security_headers_sem_hsts_fail(monkeypatch):
    from app.services import cwv_page_experience as pe

    class FakeResp:
        headers = {
            "content-security-policy": "default-src 'self'",
            "x-content-type-options": "nosniff",
            # sem strict-transport-security
        }
        status_code = 200

    class FakeClient:
        is_closed = False

        async def get(self, url):
            return FakeResp()

    monkeypatch.setattr(pe, "_CLIENT", FakeClient())
    v, detalhes = asyncio.run(check_security_headers("https://exemplo.com/"))
    assert v == "fail"
    assert "strict-transport-security" in detalhes["ausentes"]


def test_check_que_lanca_vira_erro(monkeypatch):
    """Fail-open: check que lança exceção retorna 'erro', não propaga."""
    from app.services import cwv_page_experience as pe

    async def explode(origem):
        raise RuntimeError("boom")

    monkeypatch.setattr(pe, "check_https", explode)
    # auditar_origem envolve cada check em _com_timeout que captura exceção.
    resultado = asyncio.run(auditar_origem("https://exemplo.com/", []))
    assert resultado["https"] == "erro"
    # Demais checks completam (também vão falhar porque mock quebrou tudo, mas
    # o ponto é que auditar_origem não levanta).
    assert "detalhes" in resultado


def test_redirect_301_primeiro_salto_302_fail(monkeypatch):
    from app.services import cwv_page_experience as pe

    class FakeResp:
        def __init__(self, status, location=None):
            self.status_code = status
            self.headers = {"location": location} if location else {}

    class FakeClient:
        is_closed = False

        async def get(self, url):
            return FakeResp(302, location="https://exemplo.com/")

    monkeypatch.setattr(pe, "_CLIENT", FakeClient())
    v, detalhes = asyncio.run(check_redirect_301("https://exemplo.com/"))
    assert v == "fail"
    assert "302" in detalhes["motivo"]
