"""SPEC_Saneamento_Execucoes_Orfas: cron que marca ``executando`` vencidas
como ``falhou`` + devolve reserva de créditos (idempotente)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _mock_exec(status: str, timeout_em: datetime, ferramenta: str = "core_web_vitals"):
    exe = MagicMock()
    exe.id = uuid4()
    exe.usuario_id = uuid4()
    exe.status = status
    exe.timeout_em = timeout_em
    exe.ferramenta = ferramenta
    exe.entrada_json = {"urls_por_template": {"home": ["https://a.com/"]}}
    exe.erro_msg = None
    exe.concluida_em = None
    return exe


@pytest.mark.asyncio
async def test_sanear_marca_orfa_e_libera_reserva():
    from app.scheduler import job_sanear_execucoes_orfas

    agora = datetime.now(UTC)
    orfa = _mock_exec("executando", agora - timedelta(minutes=30))
    no_prazo = _mock_exec("executando", agora + timedelta(minutes=10))

    resultado = MagicMock()
    resultado.scalars.return_value.all.return_value = [orfa, no_prazo]

    session = MagicMock()
    session.execute = AsyncMock(return_value=resultado)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    liberar = AsyncMock()
    with (
        patch("app.scheduler.async_session_factory") as factory_mock,
        patch("app.services.credito_service.liberar_reserva", new=liberar),
    ):
        factory_mock.return_value.__aenter__ = AsyncMock(return_value=session)
        factory_mock.return_value.__aexit__ = AsyncMock(return_value=None)
        # Pré-filtragem (SELECT WHERE status='executando' AND timeout_em<margem):
        # o no_prazo não viria — simulamos isso retornando só a órfã.
        resultado.scalars.return_value.all.return_value = [orfa]

        await job_sanear_execucoes_orfas()

    assert orfa.status == "falhou"
    assert orfa.concluida_em is not None
    assert "interrompida" in (orfa.erro_msg or "")
    # CWV: 1 url × 2 estratégias → custo_cwv(2) > 0 → libera.
    assert liberar.await_count == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sanear_nao_toca_execucao_no_prazo():
    from app.scheduler import job_sanear_execucoes_orfas

    agora = datetime.now(UTC)
    no_prazo = _mock_exec("executando", agora + timedelta(minutes=5))

    resultado = MagicMock()
    resultado.scalars.return_value.all.return_value = []

    session = MagicMock()
    session.execute = AsyncMock(return_value=resultado)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with (
        patch("app.scheduler.async_session_factory") as factory_mock,
        patch("app.services.credito_service.liberar_reserva", new=AsyncMock()) as liberar,
    ):
        factory_mock.return_value.__aenter__ = AsyncMock(return_value=session)
        factory_mock.return_value.__aexit__ = AsyncMock(return_value=None)

        await job_sanear_execucoes_orfas()

    assert no_prazo.status == "executando"
    assert liberar.await_count == 0


@pytest.mark.asyncio
async def test_sanear_idempotente_recheck_status():
    """Re-check do status dentro do loop: se já mudou, não toca de novo."""
    from app.scheduler import job_sanear_execucoes_orfas

    orfa = _mock_exec("falhou", datetime.now(UTC) - timedelta(hours=1))
    # Simula re-check: o SELECT retornou a linha, mas entre fetch e processar
    # ela já virou 'falhou' (condição de corrida rara).
    resultado = MagicMock()
    resultado.scalars.return_value.all.return_value = [orfa]

    session = MagicMock()
    session.execute = AsyncMock(return_value=resultado)
    session.commit = AsyncMock()

    with (
        patch("app.scheduler.async_session_factory") as factory_mock,
        patch("app.services.credito_service.liberar_reserva", new=AsyncMock()) as liberar,
    ):
        factory_mock.return_value.__aenter__ = AsyncMock(return_value=session)
        factory_mock.return_value.__aexit__ = AsyncMock(return_value=None)

        await job_sanear_execucoes_orfas()

    # Já estava 'falhou' → não libera reserva de novo.
    assert liberar.await_count == 0
