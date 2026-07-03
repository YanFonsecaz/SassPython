"""Testes das correções de CWV (SPEC_Billing_CWV + SPEC_Performance_PSI).

Cobre os fixes de maior risco, sem depender de DB:
- reserva = custo real (n_urls * 2), não só a base (corrige vazamento de reserva)
- retry do PSI em 5xx/rede, sem retry em 4xx
"""
from types import SimpleNamespace

import httpx
import pytest

from app.services import cwv_psi_client as psi
from app.services import ferramenta_service as fs

# --- SPEC_Billing_CWV: reserva pelo custo real ---

def _exec_cwv(n_urls: int):
    return SimpleNamespace(
        entrada_json={"urls_por_template": {"blog": ["https://x/" + str(i) for i in range(n_urls)]}},
        creditos_cobrados=0,
    )


def test_reserva_cwv_por_n_urls_vezes_2():
    assert fs._obter_reserva_estimada("core_web_vitals", _exec_cwv(5)) == fs.calcular_custo_cwv(10)
    assert fs._obter_reserva_estimada("core_web_vitals", _exec_cwv(1)) == fs.calcular_custo_cwv(2)


def test_reserva_cwv_satura_no_maximo():
    assert fs._obter_reserva_estimada("core_web_vitals", _exec_cwv(50)) == fs.CUSTO_MAX_CWV


def test_reserva_cwv_entrada_vazia_cai_na_base():
    vazio = SimpleNamespace(entrada_json={}, creditos_cobrados=0)
    assert fs._obter_reserva_estimada("core_web_vitals", vazio) == fs.calcular_custo_cwv(0)


# --- SPEC_Performance_PSI: retry ---

@pytest.fixture(autouse=True)
def _sem_backoff(monkeypatch):
    async def _no_sleep(_s):
        return None
    monkeypatch.setattr(psi.asyncio, "sleep", _no_sleep)


async def test_psi_retry_em_5xx_depois_sucede(monkeypatch):
    req = httpx.Request("GET", psi.PSI_ENDPOINT)
    calls = {"n": 0}

    async def fake_once(url, estrategia, key):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise httpx.HTTPStatusError("500", request=req, response=httpx.Response(500, request=req))
        return {"ok": True}

    monkeypatch.setattr(psi, "_fetch_psi_once", fake_once)
    out = await psi._fetch_com_retry("https://x", "mobile", None)
    assert out == {"ok": True}
    assert calls["n"] == 3  # 2 falhas 5xx + 1 sucesso


async def test_psi_nao_retry_em_4xx(monkeypatch):
    req = httpx.Request("GET", psi.PSI_ENDPOINT)
    calls = {"n": 0}

    async def fake_once(url, estrategia, key):
        calls["n"] += 1
        raise httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, request=req))

    monkeypatch.setattr(psi, "_fetch_psi_once", fake_once)
    with pytest.raises(httpx.HTTPStatusError):
        await psi._fetch_com_retry("https://x", "mobile", None)
    assert calls["n"] == 1  # 4xx re-lanca imediatamente (fallback de key fica no fetch_psi)
