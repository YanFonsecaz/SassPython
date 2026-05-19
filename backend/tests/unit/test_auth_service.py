import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.excecoes import CredenciaisInvalidas


@pytest.mark.asyncio
async def test_login_fails_user_not_found():
    from app.services.auth_service import login

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(CredenciaisInvalidas):
        await login(db=mock_db, email="nao@existe.com", senha="senha123", ip="127.0.0.1", user_agent="test")


@pytest.mark.asyncio
async def test_login_fails_invalid_password():
    from app.services.auth_service import login

    mock_db = AsyncMock()
    mock_user = MagicMock()
    mock_user.ativo = True
    mock_user.mfa_ativo = False

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.auth_service.verificar_senha", return_value=False):
        with patch("app.services.auth_service.verificar_hash_legado", return_value=False):
            with pytest.raises(CredenciaisInvalidas):
                await login(db=mock_db, email="user@test.com", senha="wrong", ip="127.0.0.1", user_agent="test")


def test_seguranca_functions_exist():
    from app.core.seguranca import gerar_csrf_nonce, gerar_jwt_access_token, hash_senha, verificar_senha

    assert callable(gerar_csrf_nonce)
    assert callable(gerar_jwt_access_token)
    assert callable(hash_senha)
    assert callable(verificar_senha)


def test_hash_and_verify_password():
    from app.core.seguranca import hash_senha, verificar_senha

    hashed = hash_senha("senha_forte_123")
    assert hashed != "senha_forte_123"
    assert verificar_senha("senha_forte_123", hashed) is True
    assert verificar_senha("senha_errada", hashed) is False
