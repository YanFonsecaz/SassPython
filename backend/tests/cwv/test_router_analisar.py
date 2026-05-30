import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_analisar_aceita_request_valida(client_autenticado, cliente_teste, mock_redis_pool):
    """REGRESSAO Bug #3: HttpUrl serializavel sem erro 500"""
    with patch("app.core.redis_pool.get_redis_pool", return_value=mock_redis_pool), \
         patch("app.services.credito_service.reservar_creditos", new_callable=AsyncMock), \
         patch("app.services.credito_service.liberar_reserva", new_callable=AsyncMock):

        resp = await client_autenticado.post("/api/ferramentas/core-web-vitals/analisar", json={
            "cliente_id": str(cliente_teste),
            "urls_por_template": {"home": ["https://example.com/"]},
            "estrategia": "mobile",
        })
    assert resp.status_code == 202, f"Bug #3: esperado 202, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "id" in body
    # Mobile + Desktop: 15 base + 1 URL x 2 = 17
    assert body["custo_estimado"] == 17


@pytest.mark.asyncio
async def test_analisar_sem_urls_retorna_422(client_autenticado, cliente_teste):
    resp = await client_autenticado.post("/api/ferramentas/core-web-vitals/analisar", json={
        "cliente_id": str(cliente_teste),
        "urls_por_template": {},
        "estrategia": "mobile",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analisar_max_50_urls(client_autenticado, cliente_teste):
    urls = [f"https://example.com/page-{i}/" for i in range(51)]
    resp = await client_autenticado.post("/api/ferramentas/core-web-vitals/analisar", json={
        "cliente_id": str(cliente_teste),
        "urls_por_template": {"outros": urls},
        "estrategia": "mobile",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analisar_cliente_de_outro_usuario_retorna_404(client_autenticado, cliente_outro_usuario):
    resp = await client_autenticado.post("/api/ferramentas/core-web-vitals/analisar", json={
        "cliente_id": str(cliente_outro_usuario),
        "urls_por_template": {"home": ["https://example.com/"]},
        "estrategia": "mobile",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analisar_sem_auth_retorna_401():
    from httpx import AsyncClient, ASGITransport
    from app.main import application
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/ferramentas/core-web-vitals/analisar", json={
            "cliente_id": "00000000-0000-0000-0000-000000000000",
            "urls_por_template": {"home": ["https://example.com/"]},
        })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_analisar_ignora_estrategia_no_body(client_autenticado, cliente_teste, mock_redis_pool):
    """A analise agora roda SEMPRE mobile+desktop; um campo 'estrategia' no body
    (inclusive valor antigo/invalido como 'tablet') e simplesmente ignorado."""
    with patch("app.core.redis_pool.get_redis_pool", return_value=mock_redis_pool), \
         patch("app.services.credito_service.reservar_creditos", new_callable=AsyncMock), \
         patch("app.services.credito_service.liberar_reserva", new_callable=AsyncMock):
        resp = await client_autenticado.post("/api/ferramentas/core-web-vitals/analisar", json={
            "cliente_id": str(cliente_teste),
            "urls_por_template": {"home": ["https://example.com/"]},
            "estrategia": "tablet",
        })
    assert resp.status_code == 202
