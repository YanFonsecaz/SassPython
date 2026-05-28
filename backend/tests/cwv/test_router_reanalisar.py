import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_reanalisar_cria_nova_execucao(client_autenticado, analise_teste, mock_redis_pool):
    with patch("app.core.redis_pool.get_redis_pool", return_value=mock_redis_pool), \
         patch("app.services.credito_service.reservar_creditos", new_callable=AsyncMock), \
         patch("app.services.credito_service.liberar_reserva", new_callable=AsyncMock):

        resp = await client_autenticado.post(
            f"/api/ferramentas/core-web-vitals/reanalisar/{analise_teste.id}"
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["n_urls"] == 1
    assert "id" in body


@pytest.mark.asyncio
async def test_reanalisar_analise_inexistente(client_autenticado):
    import uuid
    resp = await client_autenticado.post(
        f"/api/ferramentas/core-web-vitals/reanalisar/{uuid.uuid4()}"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reanalisar_sem_auth():
    from httpx import AsyncClient, ASGITransport
    from app.main import application
    import uuid

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/ferramentas/core-web-vitals/reanalisar/{uuid.uuid4()}"
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_custo_endpoint(client_autenticado):
    resp = await client_autenticado.get("/api/ferramentas/core-web-vitals/custo?n_urls=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["custo"] == 20
    assert body["n_urls"] == 5


@pytest.mark.asyncio
async def test_custo_endpoint_max(client_autenticado):
    resp = await client_autenticado.get("/api/ferramentas/core-web-vitals/custo?n_urls=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["custo"] == 50


@pytest.mark.asyncio
async def test_custo_endpoint_acima_de_50_rejeita(client_autenticado):
    resp = await client_autenticado.get("/api/ferramentas/core-web-vitals/custo?n_urls=100")
    assert resp.status_code == 422
