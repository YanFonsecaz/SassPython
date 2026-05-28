import pytest
import respx
from app.services.cwv_psi_client import PSIError, fetch_psi


@respx.mock
@pytest.mark.asyncio
async def test_fetch_psi_sucesso_com_key1(monkeypatch):
    monkeypatch.setattr("app.config.settings.api_psi_key", "KEY1")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "KEY2")
    respx.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed").respond(
        json={"lighthouseResult": {"finalUrl": "https://x.com"}}
    )
    data = await fetch_psi("https://x.com")
    assert "lighthouseResult" in data


@respx.mock
@pytest.mark.asyncio
async def test_fetch_psi_429_em_key1_tenta_key2(monkeypatch):
    """REGRESSAO Bug #5: fallback para key2 quando key1 retorna 429"""
    monkeypatch.setattr("app.config.settings.api_psi_key", "KEY1")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "KEY2")
    route1 = respx.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed")
    route2 = respx.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed")

    route1.side_effect = [
        respx.MockResponse(status_code=429, json={"error": {"message": "Quota exceeded"}}),
    ]
    route2.side_effect = [
        respx.MockResponse(json={"lighthouseResult": {"finalUrl": "https://x.com"}}),
    ]
    data = await fetch_psi("https://x.com")
    assert "lighthouseResult" in data


@respx.mock
@pytest.mark.asyncio
async def test_fetch_psi_429_em_todas_keys_levanta_erro(monkeypatch):
    monkeypatch.setattr("app.config.settings.api_psi_key", "KEY1")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "KEY2")
    route = respx.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed")
    route.side_effect = [
        respx.MockResponse(status_code=429, json={"error": {"message": "Quota"}}),
        respx.MockResponse(status_code=429, json={"error": {"message": "Quota"}}),
    ]
    with pytest.raises(PSIError, match="429"):
        await fetch_psi("https://x.com")


@respx.mock
@pytest.mark.asyncio
async def test_fetch_psi_sem_keys_usa_anonimo(monkeypatch):
    monkeypatch.setattr("app.config.settings.api_psi_key", "")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "")
    respx.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed").respond(
        json={"lighthouseResult": {"finalUrl": "x"}}
    )
    data = await fetch_psi("https://x.com")
    assert data["lighthouseResult"]["finalUrl"] == "x"


@respx.mock
@pytest.mark.asyncio
async def test_fetch_psi_resposta_sem_lighthouse_levanta_erro(monkeypatch):
    monkeypatch.setattr("app.config.settings.api_psi_key", "KEY1")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "")
    respx.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed").respond(
        json={"error": {"message": "Bad request"}}
    )
    with pytest.raises(PSIError, match="lighthouseResult"):
        await fetch_psi("https://x.com")


@respx.mock
@pytest.mark.asyncio
async def test_fetch_psi_403_tenta_key2(monkeypatch):
    monkeypatch.setattr("app.config.settings.api_psi_key", "KEY1")
    monkeypatch.setattr("app.config.settings.api_psi_key2", "KEY2")
    route = respx.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed")
    route.side_effect = [
        respx.MockResponse(status_code=403, json={"error": {"message": "Forbidden"}}),
        respx.MockResponse(json={"lighthouseResult": {"finalUrl": "https://x.com"}}),
    ]
    data = await fetch_psi("https://x.com")
    assert "lighthouseResult" in data
