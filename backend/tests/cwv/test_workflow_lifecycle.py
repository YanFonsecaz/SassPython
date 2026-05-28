"""Tests dos lifecycle handlers do workflow CWV: timeout e cancelamento.

Estes cenários nunca foram exercitados em E2E real. Aqui são validados via
asyncio direto sem depender de PSI real.
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.cwv_analise import CwvAnalise
from app.models.execucao_ferramenta import ExecucaoFerramenta


@pytest.mark.asyncio
async def test_workflow_timeout_marca_execucao_e_motivo(
    db_engine, db_session, usuario_teste, cliente_teste, execucao_teste, monkeypatch
):
    """Quando workflow excede settings.cwv_workflow_timeout, status=falhou + motivo_falha=timeout."""
    from app.config import settings

    monkeypatch.setattr(settings, "cwv_workflow_timeout", 1)

    async def fetch_lento(url, estrategia):
        await asyncio.sleep(10)  # Maior que o timeout
        return {}

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    real_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    with patch("app.services.cwv_psi_client.fetch_psi", side_effect=fetch_lento), \
         patch("app.core.workflow_events.publish_event", new_callable=AsyncMock), \
         patch("app.services.credito_service.liberar_reserva", new_callable=AsyncMock), \
         patch("app.db.session.async_session_factory") as mock_sf:
        mock_sf.side_effect = lambda: real_factory()

        from app.agents.cwv.workflow import executar_workflow_cwv
        await executar_workflow_cwv(str(execucao_teste.id))

    async with real_factory() as check:
        execucao = await check.get(ExecucaoFerramenta, execucao_teste.id)
        assert execucao.status == "falhou"
        assert execucao.erro_msg and "tempo limite" in execucao.erro_msg.lower()
        assert execucao.resultado_json.get("motivo_falha") == "timeout"


@pytest.mark.asyncio
async def test_workflow_cancelamento_libera_creditos_e_marca_cancelada(
    db_engine, db_session, usuario_teste, cliente_teste, execucao_teste
):
    """CancelledError mid-flight deve liberar creditos reservados e marcar status=cancelada."""
    cancelou = asyncio.Event()

    async def fetch_que_dorme(url, estrategia):
        cancelou.set()
        await asyncio.sleep(60)  # Permite tempo para cancelar
        return {}

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    real_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    liberar_mock = AsyncMock()

    with patch("app.services.cwv_psi_client.fetch_psi", side_effect=fetch_que_dorme), \
         patch("app.core.workflow_events.publish_event", new_callable=AsyncMock), \
         patch("app.services.credito_service.liberar_reserva", liberar_mock), \
         patch("app.db.session.async_session_factory") as mock_sf:
        mock_sf.side_effect = lambda: real_factory()

        from app.agents.cwv.workflow import executar_workflow_cwv

        task = asyncio.create_task(executar_workflow_cwv(str(execucao_teste.id)))
        await cancelou.wait()  # Espera workflow começar PSI
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async with real_factory() as check:
        execucao = await check.get(ExecucaoFerramenta, execucao_teste.id)
        assert execucao.status == "cancelada"
        assert execucao.resultado_json.get("motivo_falha") == "cancelada"
    assert liberar_mock.called, "liberar_reserva deveria ser chamado ao cancelar"


@pytest.mark.asyncio
async def test_workflow_cliente_removido_handler_defensivo_existe():
    """O handler para 'cliente_removido' existe no workflow.py mesmo que FK impeça o caso real.
    Garante que código defensivo não seja removido em refactor.
    """
    import inspect
    from app.agents.cwv import workflow

    src = inspect.getsource(workflow.executar_workflow_cwv)
    assert "cliente_removido" in src
    assert "cliente foi removido" in src.lower() or "removido" in src.lower()
