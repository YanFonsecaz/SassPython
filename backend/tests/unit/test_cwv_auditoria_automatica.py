"""Testes para _criar_auditoria_automatica."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cwv_auditoria_service import _criar_auditoria_automatica


def _make_execucao(entrada_json=None):
    exec_mock = MagicMock()
    exec_mock.id = "exec-001"
    exec_mock.usuario_id = "user-001"
    exec_mock.entrada_json = entrada_json
    return exec_mock


def _make_session(auditoria_aberta_id=None):
    """Sessão fake cujo ``execute(...).scalar_one_or_none()`` devolve o id da
    auditoria aberta do cliente (ou ``None`` se não houver)."""
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = auditoria_aberta_id
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_cria_nova_auditoria():
    execucao = _make_execucao(entrada_json={})
    mock_auditoria = MagicMock()
    mock_auditoria.id = "aud-nova-001"

    with patch(
        "app.services.cwv_auditoria_service.criar_auditoria",
        new_callable=AsyncMock,
        return_value=mock_auditoria,
    ) as criar_mock:
        criada, existente = await _criar_auditoria_automatica(
            session=_make_session(auditoria_aberta_id=None),
            execucao=execucao,
            cliente_id="cliente-001",
            usuario_id="user-001",
        )

    assert criada == "aud-nova-001"
    assert existente is None
    criar_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_retorna_existente_quando_ja_vinculada():
    """Re-auditoria: ``entrada_json.auditoria_id`` presente — aponta, não cria."""
    execucao = _make_execucao(entrada_json={"auditoria_id": "aud-existente-999"})

    with patch(
        "app.services.cwv_auditoria_service.criar_auditoria",
        new_callable=AsyncMock,
    ) as criar_mock:
        criada, existente = await _criar_auditoria_automatica(
            session=_make_session(),
            execucao=execucao,
            cliente_id="cliente-001",
            usuario_id="user-001",
        )

    assert criada is None
    assert existente == "aud-existente-999"
    criar_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_aponta_auditoria_aberta_do_cliente_sem_empilhar():
    """crit.#2: cliente com auditoria aberta → aponta e NÃO cria outra."""
    execucao = _make_execucao(entrada_json={})

    with patch(
        "app.services.cwv_auditoria_service.criar_auditoria",
        new_callable=AsyncMock,
    ) as criar_mock:
        criada, existente = await _criar_auditoria_automatica(
            session=_make_session(auditoria_aberta_id="aud-aberta-777"),
            execucao=execucao,
            cliente_id="cliente-001",
            usuario_id="user-001",
        )

    assert criada is None
    assert existente == "aud-aberta-777"
    criar_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_fail_open_retorna_none_none():
    execucao = _make_execucao(entrada_json={})

    with patch(
        "app.services.cwv_auditoria_service.criar_auditoria",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB boom"),
    ):
        criada, existente = await _criar_auditoria_automatica(
            session=_make_session(auditoria_aberta_id=None),
            execucao=execucao,
            cliente_id="cliente-001",
            usuario_id="user-001",
        )

    assert criada is None
    assert existente is None
