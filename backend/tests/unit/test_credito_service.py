import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_credito_service_imports():
    from app.services.credito_service import (
        confirmar_debito,
        creditar_extras,
        liberar_reserva,
        reservar_creditos,
    )

    assert callable(reservar_creditos)
    assert callable(confirmar_debito)
    assert callable(liberar_reserva)
    assert callable(creditar_extras)


@pytest.mark.asyncio
async def test_reservar_creditos_insuficiente():
    from app.services.credito_service import reservar_creditos

    mock_db = MagicMock()

    mock_conta = MagicMock()
    mock_conta.saldo_disponivel = 1
    mock_conta.saldo_reservado = 0

    with patch("app.services.credito_service.buscar_ou_criar_conta", new_callable=AsyncMock, return_value=mock_conta):
        with pytest.raises(ValueError, match="Saldo insuficiente"):
            await reservar_creditos(mock_db, "user-1", quantidade=10)

    mock_db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_liberar_reserva_clamps_negative():
    from app.services.credito_service import liberar_reserva

    mock_db = MagicMock()
    mock_db.flush = AsyncMock()

    mock_conta = MagicMock()
    mock_conta.saldo_reservado = 2

    with patch("app.services.credito_service.buscar_ou_criar_conta", new_callable=AsyncMock, return_value=mock_conta):
        await liberar_reserva(mock_db, "user-1", quantidade=100)

    assert mock_conta.saldo_reservado == 0
    mock_db.flush.assert_called_once()
