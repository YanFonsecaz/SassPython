import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_historico_url_retorna_plataforma_e_template(client_autenticado, cliente_teste, analise_teste):
    """REGRESSAO Bug #2: historico-url retorna plataforma e template da ultima analise"""
    resp = await client_autenticado.get(
        f"/api/ferramentas/core-web-vitals/historico-url?cliente_id={cliente_teste}&url=https://example.com/"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plataforma_detectada"] == "wordpress"
    assert body["template_tipo"] == "home"


@pytest.mark.asyncio
async def test_historico_url_cliente_de_outro_usuario_retorna_404(client_autenticado, cliente_outro_usuario):
    """REGRESSAO Bug #2 (security)"""
    resp = await client_autenticado.get(
        f"/api/ferramentas/core-web-vitals/historico-url?cliente_id={cliente_outro_usuario}&url=https://x.com/"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_historico_url_vazio(client_autenticado, cliente_teste):
    resp = await client_autenticado.get(
        f"/api/ferramentas/core-web-vitals/historico-url?cliente_id={cliente_teste}&url=https://nao-existe.com/"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["template_tipo"] == ""
    assert body["plataforma_detectada"] == ""
    assert body["analises"] == []


@pytest.mark.asyncio
async def test_historico_lista_urls(client_autenticado, cliente_teste, analise_teste):
    resp = await client_autenticado.get(
        f"/api/ferramentas/core-web-vitals/historico?cliente_id={cliente_teste}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["urls"], list)
    assert len(body["urls"]) >= 1
