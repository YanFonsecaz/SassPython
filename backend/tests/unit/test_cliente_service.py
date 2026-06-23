"""Testes do cliente_service — focados em identificar bugs de concorrencia/limite.

Cobre:
  - verificar_limite_clientes (casos -1 ilimitado, abaixo/igual/acima do limite, sem plano)
  - atualizar_cliente (bug do exclude_none que impede limpar campos)
  - remover_cliente (soft delete via ativo=False)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_verificar_limite_ilimitado_quando_menos_um():
    """Plano com cliente_limite=-1 nao bloqueia nunca."""
    from app.services import cliente_service

    plano = MagicMock()
    plano.cliente_limite = -1
    usuario = MagicMock()
    usuario.plano_id = uuid.uuid4()

    db = AsyncMock()
    # execute retorna um resultado novo a cada chamada (usuario, plano, count)
    resultados = []
    for valor in [usuario, plano, 999]:
        r = MagicMock()
        r.scalar_one_or_none.return_value = valor
        r.scalar.return_value = valor
        resultados.append(r)
    db.execute = AsyncMock(side_effect=resultados)

    ok = await cliente_service.verificar_limite_clientes(db, str(uuid.uuid4()))
    assert ok is True


@pytest.mark.asyncio
async def test_verificar_limite_abaixo_do_maximo_permite():
    from app.services import cliente_service

    plano = MagicMock()
    plano.cliente_limite = 5
    usuario = MagicMock()
    usuario.plano_id = uuid.uuid4()

    db = AsyncMock()
    resultados = []
    for valor in [usuario, plano, 3]:  # 3 < 5
        r = MagicMock()
        r.scalar_one_or_none.return_value = valor
        r.scalar.return_value = valor
        resultados.append(r)
    db.execute = AsyncMock(side_effect=resultados)

    assert await cliente_service.verificar_limite_clientes(db, str(uuid.uuid4())) is True


@pytest.mark.asyncio
async def test_verificar_limite_no_maximo_bloqueia():
    from app.services import cliente_service

    plano = MagicMock()
    plano.cliente_limite = 5
    usuario = MagicMock()
    usuario.plano_id = uuid.uuid4()

    db = AsyncMock()
    resultados = []
    for valor in [usuario, plano, 5]:  # 5 >= 5
        r = MagicMock()
        r.scalar_one_or_none.return_value = valor
        r.scalar.return_value = valor
        resultados.append(r)
    db.execute = AsyncMock(side_effect=resultados)

    assert await cliente_service.verificar_limite_clientes(db, str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_verificar_limite_sem_plano_bloqueia():
    """Usuario sem plano_id nao pode criar cliente (defesa)."""
    from app.services import cliente_service

    usuario = MagicMock()
    usuario.plano_id = None

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = usuario
    db.execute = AsyncMock(return_value=r)

    assert await cliente_service.verificar_limite_clientes(db, str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_remover_cliente_faz_soft_delete():
    """Remocao e logica: apenas seta ativo=False, nao apaga a row."""
    from app.services import cliente_service

    cliente = MagicMock()
    cliente.ativo = True

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = cliente
    db.execute = AsyncMock(return_value=r)
    db.flush = AsyncMock()

    removido = await cliente_service.remover_cliente(db, str(uuid.uuid4()), str(uuid.uuid4()))
    assert removido is True
    assert cliente.ativo is False
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_remover_cliente_inexistente_retorna_false():
    from app.services import cliente_service

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=r)

    assert await cliente_service.remover_cliente(db, str(uuid.uuid4()), str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_atualizar_cliente_com_none_nao_sobrescreve():
    """BUG CONHECIDO/DOCUMENTADO: o router usa exclude_none=True, entao enviar
    site_url=None (frontend) NAO limpa o campo. Este teste documenta o comportamento:
    o service so aplica valores nao-None. Limpar site_url via PUT nao funciona hoje.
    """
    from app.services import cliente_service

    cliente = MagicMock()
    cliente.site_url = "https://antigo.com.br/"
    cliente.nome = "Antigo"

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = cliente
    db.execute = AsyncMock(return_value=r)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    # Simula o que chega no service apos exclude_none=True
    resultado = await cliente_service.atualizar_cliente(
        db, str(uuid.uuid4()), str(uuid.uuid4()), nome="Novo"
    )
    assert resultado is not None
    assert cliente.nome == "Novo"
    # site_url nao foi tocado
    assert cliente.site_url == "https://antigo.com.br/"
