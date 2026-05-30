import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.cwv_analise import CwvAnalise
from app.models.execucao_ferramenta import ExecucaoFerramenta


@pytest.mark.asyncio
async def test_workflow_completo_persiste_e_atualiza_execucao(
    db_engine, db_session, usuario_teste, cliente_teste, execucao_teste
):
    """REGRESSAO Bugs #6 e #7: workflow completa e persiste resultado_json + analises"""
    from unittest.mock import patch

    eid = str(execucao_teste.id)

    psi_response = {
        "lighthouseResult": {
            "finalUrl": "https://example.com/",
            "categories": {"performance": {"score": 0.62}},
            "audits": {
                "largest-contentful-paint": {
                    "id": "largest-contentful-paint",
                    "title": "LCP element",
                    "score": 0.4,
                    "numericValue": 4200,
                    "scoreDisplayMode": "numeric",
                    "displayValue": "4.2s",
                },
                "cumulative-layout-shift": {
                    "id": "cumulative-layout-shift",
                    "title": "CLS",
                    "score": 0.5,
                    "numericValue": 0.18,
                    "scoreDisplayMode": "numeric",
                    "displayValue": "0.18",
                },
                "first-contentful-paint": {"score": 0.9, "numericValue": 1000, "scoreDisplayMode": "numeric"},
                "server-response-time": {"score": 1.0, "numericValue": 100, "scoreDisplayMode": "numeric"},
                "total-blocking-time": {"score": 0.8, "numericValue": 200, "scoreDisplayMode": "numeric"},
                "interaction-to-next-paint": {"score": 0.85, "numericValue": 180, "scoreDisplayMode": "numeric"},
            },
            "stackPacks": [{"id": "wordpress"}],
            "userAgent": "Chrome/120",
        }
    }

    mock_credito = AsyncMock()
    mock_credito.confirmar_debito = AsyncMock()
    mock_credito.liberar_reserva = AsyncMock()
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()

    with patch("app.services.cwv_psi_client.fetch_psi", new_callable=AsyncMock, return_value=psi_response) as mock_fetch, \
         patch("app.services.credito_service.confirmar_debito", mock_credito.confirmar_debito), \
         patch("app.services.credito_service.liberar_reserva", mock_credito.liberar_reserva), \
         patch("app.core.workflow_events.publish_event", new_callable=AsyncMock), \
         patch("app.agents.cwv.analisador.CWVAnalisadorAgent.analisar", new_callable=AsyncMock, return_value=([], {"llm_usado": False, "processados": 0, "descartados": 0})), \
         patch("app.db.session.async_session_factory") as mock_session_factory:

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        real_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_session_factory.side_effect = lambda: real_factory()

        from app.agents.cwv.workflow import executar_workflow_cwv
        await executar_workflow_cwv(eid)

    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    check_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with check_factory() as check_session:
        execucao = await check_session.get(ExecucaoFerramenta, execucao_teste.id)
        assert execucao.status == "concluida", f"Bug #7: status={execucao.status}, erro={execucao.erro_msg}"
        assert execucao.resultado_json is not None, "Bug #6: resultado_json e None"
        analise_ids = execucao.resultado_json.get("analise_ids", [])
        # Mobile + Desktop: 1 URL gera 2 analises
        assert len(analise_ids) == 2, f"esperado 2 analises (mobile+desktop), got {len(analise_ids)}"

        analise = await check_session.get(CwvAnalise, uuid.UUID(analise_ids[0]))
        assert analise is not None
        assert analise.status == "sucesso"
        assert analise.plataforma_detectada == "wordpress"

        estrategias = set()
        for aid in analise_ids:
            a = await check_session.get(CwvAnalise, uuid.UUID(aid))
            estrategias.add(a.estrategia)
        assert estrategias == {"mobile", "desktop"}, f"esperado mobile+desktop, got {estrategias}"


@pytest.mark.asyncio
async def test_workflow_falha_psi_persiste_status(db_engine, db_session, usuario_teste, cliente_teste, execucao_teste):
    """Workflow com PSI falhando deve persistir analises com status falhou_psi"""
    from unittest.mock import AsyncMock, patch
    from app.agents.cwv.workflow import executar_workflow_cwv

    mock_credito = AsyncMock()
    mock_credito.confirmar_debito = AsyncMock()
    mock_credito.liberar_reserva = AsyncMock()

    from app.services.cwv_psi_client import PSIError

    async def fake_fetch(url, estrategia):
        raise PSIError("PSI 429")

    with patch("app.services.cwv_psi_client.fetch_psi", side_effect=fake_fetch), \
         patch("app.services.credito_service.confirmar_debito", mock_credito.confirmar_debito), \
         patch("app.services.credito_service.liberar_reserva", mock_credito.liberar_reserva), \
         patch("app.core.workflow_events.publish_event", new_callable=AsyncMock), \
         patch("app.db.session.async_session_factory") as mock_sf:

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        real_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_sf.side_effect = lambda: real_factory()

        await executar_workflow_cwv(str(execucao_teste.id))

    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    check_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with check_factory() as check_session:
        execucao = await check_session.get(ExecucaoFerramenta, execucao_teste.id)
        # Quando 100% das URLs falham PSI, workflow marca como "falhou" (pós SPEC #17)
        assert execucao.status == "falhou"
        assert execucao.resultado_json is not None
        assert execucao.resultado_json.get("motivo_falha") == "psi_total"
        # Mesmo com falha, persistir cria registro de cwv_analise com status=falhou_psi
        analise_ids = execucao.resultado_json.get("analise_ids", [])
        assert len(analise_ids) >= 1
        analise = await check_session.get(CwvAnalise, uuid.UUID(analise_ids[0]))
        assert analise is not None
        assert analise.status == "falhou_psi"
