
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import application


@pytest.mark.asyncio
async def test_reload_kb_sem_token_configurado_retorna_403(monkeypatch):
    monkeypatch.setattr(settings, "cwv_admin_reload_token", "")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        r = await c.post("/api/admin/cwv/kb/reload", headers={"X-Admin-Token": "qualquer"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_reload_kb_token_errado_retorna_403(monkeypatch):
    monkeypatch.setattr(settings, "cwv_admin_reload_token", "correto")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        r = await c.post("/api/admin/cwv/kb/reload", headers={"X-Admin-Token": "errado"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_reload_kb_token_correto_recarrega(monkeypatch):
    monkeypatch.setattr(settings, "cwv_admin_reload_token", "correto")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        r = await c.post("/api/admin/cwv/kb/reload", headers={"X-Admin-Token": "correto"})
    assert r.status_code == 200
    body = r.json()
    assert body["reloaded"] is True
    assert body["n_codigos"] > 0


@pytest.mark.asyncio
async def test_reload_kb_sem_header_retorna_403(monkeypatch):
    monkeypatch.setattr(settings, "cwv_admin_reload_token", "correto")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        r = await c.post("/api/admin/cwv/kb/reload")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_health_sem_token_retorna_403(monkeypatch):
    monkeypatch.setattr(settings, "cwv_admin_reload_token", "correto")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        r = await c.get("/api/admin/cwv/health")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_health_token_errado_retorna_403(monkeypatch):
    monkeypatch.setattr(settings, "cwv_admin_reload_token", "correto")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        r = await c.get("/api/admin/cwv/health", headers={"X-Admin-Token": "errado"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_health_token_correto_retorna_ok(monkeypatch):
    monkeypatch.setattr(settings, "cwv_admin_reload_token", "correto")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as c:
        r = await c.get("/api/admin/cwv/health", headers={"X-Admin-Token": "correto"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded", "down")
    assert "psi" in body
    assert "llm" in body
    assert "kb" in body
    assert body["kb"]["entries_loaded"] > 0
    assert "aliases" in body["kb"]
    assert "ultimas_24h" in body
    assert "alerta_webhook_configurado" in body
