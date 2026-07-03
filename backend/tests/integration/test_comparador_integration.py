from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_comparacao_endpoint_com_anterior(test_client: AsyncClient, usuario_autenticado):
    """Testa endpoint de comparação quando existe análise anterior"""

    # Setup: criar cliente e análises de teste
    cliente_id = "test-client-id"

    with patch("app.db.session.execute") as mock_execute:
        # Mock análise atual
        mock_analise_atual = {
            "id": "current-id",
            "cliente_id": cliente_id,
            "usuario_id": str(usuario_autenticado.id),
            "url_canonica": "https://test.com/page",
            "criado_em": datetime.now(UTC),
            "score_performance": 80,
            "lcp_ms": 2000.0,
            "cls": 0.05,
            "inp_ms": 150.0,
            "fcp_ms": 1000.0,
            "ttfb_ms": 700.0,
            "tbt_ms": 120.0
        }

        mock_execute.return_value = AsyncMock()
        mock_analise_obj = AsyncMock()
        mock_analise_obj.id = "current-id"
        mock_analise_obj.cliente_id = cliente_id
        mock_analise_obj.usuario_id = str(usuario_autenticado.id)
        mock_analise_obj.url_canonica = "https://test.com/page"
        mock_analise_obj.criado_em = datetime.now(UTC)
        mock_analise_obj.score_performance = 80
        mock_analise_obj.lcp_ms = 2000.0
        mock_analise_obj.cls = 0.05
        mock_analise_obj.inp_ms = 150.0
        mock_analise_obj.fcp_ms = 1000.0
        mock_analise_obj.ttfb_ms = 700.0
        mock_analise_obj.tbt_ms = 120.0
        mock_analise_obj.status = "sucesso"
        mock_execute.return_value.scalar_one_or_none.return_value = mock_analise_obj

        # Mock problemas
        mock_problemas_atual = []
        mock_problemas_anterior = []

        with patch("app.services.cwv_persistencia.buscar_problemas_analise") as mock_busca_problemas:
            mock_busca_problemas.side_effect = mock_problemas_atual

            with patch("app.services.cwv_persistencia.buscar_analise_anterior") as mock_busca_anterior:
                mock_anterior = AsyncMock()
                mock_anterior.id = "previous-id"
                mock_anterior.criado_em = datetime.now(UTC) - timedelta(days=7)
                mock_anterior.score_performance = 70
                mock_anterior.lcp_ms = 2500.0
                mock_anterior.cls = 0.08
                mock_anterior.inp_ms = 200.0
                mock_anterior.fcp_ms = 1200.0
                mock_anterior.ttfb_ms = 800.0
                mock_anterior.tbt_ms = 150.0
                mock_anterior.status = "sucesso"
                mock_busca_anterior.return_value = mock_anterior

                with patch("app.services.cwv_persistencia.buscar_problemas_analise") as mock_busca_problemas_anterior:
                    mock_busca_problemas_anterior.return_value = mock_problemas_anterior

                # Fazer requisição
                response = await test_client.get(
                    "/api/ferramentas/core-web-vitals/comparacao/current-id",
                    headers={"Authorization": f"Bearer {usuario_autenticado.access_token}"}
                )

                assert response.status_code == 200
                data = response.json()

                assert data["analise_atual_id"] == "current-id"
                assert data["analise_anterior_id"] == "previous-id"
                assert data["dias_decorridos"] == 7

                # Validar métricas
                assert "score_performance" in data["metricas"]
                assert "lcp_ms" in data["metricas"]
                assert "cls" in data["metricas"]

                score = data["metricas"]["score_performance"]
                assert score["antes"] == 70
                assert score["depois"] == 80
                assert score["delta"] == 10
                assert score["melhorou"] == True

                lcp = data["metricas"]["lcp_ms"]
                assert lcp["antes"] == 2500.0
                assert lcp["depois"] == 2000.0
                assert lcp["delta"] == -500.0
                assert lcp["melhorou"] == True

                # Validar problemas
                assert len(data["problemas_resolvidos"]) == 0
                assert len(data["problemas_novos"]) == 0
                assert len(data["problemas_persistentes"]) == 0


@pytest.mark.asyncio
async def test_comparacao_endpoint_sem_anterior(test_client: AsyncClient, usuario_autenticado):
    """Testa endpoint de comparação quando não existe análise anterior"""

    with patch("app.db.session.execute") as mock_execute:
        # Mock análise atual sem anterior
        mock_analise_atual = {
            "id": "current-id",
            "cliente_id": "test-client-id",
            "usuario_id": str(usuario_autenticado.id),
            "url_canonica": "https://test.com/page",
            "criado_em": datetime.now(UTC),
            "score_performance": 80
        }

        mock_execute.return_value = AsyncMock()
        mock_analise_obj = AsyncMock()
        mock_analise_obj.id = "current-id"
        mock_analise_obj.usuario_id = str(usuario_autenticado.id)
        mock_analise_obj.criado_em = datetime.now(UTC)
        mock_analise_obj.score_performance = 80
        mock_analise_obj.status = "sucesso"
        mock_execute.return_value.scalar_one_or_none.return_value = mock_analise_obj

        with patch("app.services.cwv_persistencia.buscar_problemas_analise") as mock_busca_problemas:
            mock_busca_problemas.return_value = []

            with patch("app.services.cwv_persistencia.buscar_analise_anterior") as mock_busca_anterior:
                mock_busca_anterior.return_value = None

                response = await test_client.get(
                    "/api/ferramentas/core-web-vitals/comparacao/current-id",
                    headers={"Authorization": f"Bearer {usuario_autenticado.access_token}"}
                )

                assert response.status_code == 200
                data = response.json()

                assert data["analise_atual_id"] == "current-id"
                assert data["analise_anterior_id"] is None
                assert data["dias_decorridos"] is None
                assert len(data["metricas"]) == 0
                assert len(data["problemas_resolvidos"]) == 0
                assert len(data["problemas_novos"]) == 0
                assert len(data["problemas_persistentes"]) == 0


@pytest.mark.asyncio
async def test_comparacao_endpoint_nao_encontrado(test_client, usuario_autenticado):
    """Testa endpoint de comparação quando análise não existe"""

    with patch("app.db.session.execute") as mock_execute:
        mock_execute.return_value = AsyncMock()
        mock_execute.return_value.scalar_one_or_none.return_value = None

        response = await test_client.get(
            "/api/ferramentas/core-web-vitals/comparacao/non-existent-id",
            headers={"Authorization": f"Bearer {usuario_autenticado.access_token}"}
        )

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_comparacao_endpoint_nao_autorizado(test_client, usuario_autenticado):
    """Testa endpoint de comparação sem autenticação"""

    response = await test_client.get("/api/ferramentas/core-web-vitals/comparacao/test-id")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_comparacao_endpoint_com_problemas(test_client: AsyncClient, usuario_autenticado):
    """Testa endpoint de comparação com problemas resolvidos/novos"""

    with patch("app.db.session.execute") as mock_execute:
        mock_analise_obj = AsyncMock()
        mock_analise_obj.id = "current-id"
        mock_analise_obj.usuario_id = str(usuario_autenticado.id)
        mock_analise_obj.criado_em = datetime.now(UTC)
        mock_analise_obj.score_performance = 80
        mock_analise_obj.status = "sucesso"
        mock_execute.return_value.scalar_one_or_none.return_value = mock_analise_obj

        # Mock problemas atuais
        problemas_atual = [
            {"id": "1", "kb_codigo": "PROBLEMA_1", "titulo": "Problema 1"},
            {"id": "2", "kb_codigo": "PROBLEMA_2", "titulo": "Problema 2"}
        ]

        # Mock problemas anteriores
        problemas_anterior = [
            {"id": "1", "kb_codigo": "PROBLEMA_1", "titulo": "Problema 1"},
            {"id": "3", "kb_codigo": "PROBLEMA_3", "titulo": "Problema 3"}
        ]

        with patch("app.services.cwv_persistencia.buscar_problemas_analise") as mock_busca_problemas:
            mock_busca_problemas.side_effect = [problemas_atual, problemas_anterior]

            with patch("app.services.cwv_persistencia.buscar_analise_anterior") as mock_busca_anterior:
                mock_anterior = AsyncMock()
                mock_anterior.id = "previous-id"
                mock_anterior.criado_em = datetime.now(UTC) - timedelta(days=7)
                mock_busca_anterior.return_value = mock_anterior

                response = await test_client.get(
                    "/api/ferramentas/core-web-vitals/comparacao/current-id",
                    headers={"Authorization": f"Bearer {usuario_autenticado.access_token}"}
                )

                assert response.status_code == 200
                data = response.json()

                # Problema 1: persistente (está nos dois)
                assert any(p["kb_codigo"] == "PROBLEMA_1" for p in data["problemas_persistentes"])

                # Problema 2: novo (está só nos atuais)
                assert any(p["kb_codigo"] == "PROBLEMA_2" for p in data["problemas_novos"])

                # Problema 3: resolvido (está só nos anteriores)
                assert any(p["kb_codigo"] == "PROBLEMA_3" for p in data["problemas_resolvidos"])
