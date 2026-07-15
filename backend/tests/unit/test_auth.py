import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cadastro_sucesso(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/cadastro",
        json={
            "nome": "Joao Silva",
            "email": "joao@example.com",
            "senha": "SenhaForte123!@#",
            "senha_confirmacao": "SenhaForte123!@#",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_cadastro_senhas_diferentes(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/cadastro",
        json={
            "nome": "Joao Silva",
            "email": "joao2@example.com",
            "senha": "SenhaForte123!@#",
            "senha_confirmacao": "OutraSenha456!@#",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cadastro_senha_fraca(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/cadastro",
        json={
            "nome": "Joao Silva",
            "email": "joao3@example.com",
            "senha": "fraca",
            "senha_confirmacao": "fraca",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cadastro_senha_fraca_zxcvbn(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/cadastro",
        json={
            "nome": "Joao Silva",
            "email": "joao3b@example.com",
            "senha": "Aaaaaaaaaaaaa1!",
            "senha_confirmacao": "Aaaaaaaaaaaaa1!",
        },
    )
    assert response.status_code == 400
    assert "fraca" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cadastro_email_duplicado(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.post(
        "/api/auth/cadastro",
        json={
            "nome": "Outro User",
            "email": usuario_teste["email"],
            "senha": "SenhaForte123!@#",
            "senha_confirmacao": "SenhaForte123!@#",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_sucesso(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.post(
        "/api/auth/login",
        json={
            "email": usuario_teste["email"],
            "senha": "SenhaForte123!@#",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "set-cookie" in response.headers


@pytest.mark.asyncio
async def test_login_credenciais_invalidas(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.post(
        "/api/auth/login",
        json={
            "email": usuario_teste["email"],
            "senha": "SenhaErrada123!@#",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_email_inexistente(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={
            "email": "naoexiste@example.com",
            "senha": "SenhaForte123!@#",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_anti_enumeration(client: AsyncClient, usuario_teste: dict) -> None:
    import time

    inicio = time.time()
    await client.post(
        "/api/auth/login",
        json={"email": usuario_teste["email"], "senha": "Errada123!@#"},
    )
    tempo_existente = time.time() - inicio

    inicio2 = time.time()
    await client.post(
        "/api/auth/login",
        json={"email": "naoexiste@example.com", "senha": "Errada123!@#"},
    )
    tempo_inexistente = time.time() - inicio2

    diff = abs(tempo_existente - tempo_inexistente)
    assert diff < 0.5


@pytest.mark.asyncio
async def test_me_autenticado(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.get("/api/auth/me", headers=usuario_teste["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == usuario_teste["email"]
    assert "plano" in data
    assert data["mfa_ativo"] is False
    assert data["email_verificado"] is False


@pytest.mark.asyncio
async def test_me_nao_autenticado(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, usuario_teste: dict) -> None:
    refresh_token = usuario_teste["refresh_token"]
    assert refresh_token, "refresh_token ausente no fixture usuario_teste"

    refresh_resp = await client.post(
        "/api/auth/refresh",
        headers={"Cookie": f"refresh_token={refresh_token}"},
    )
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.post("/api/auth/logout", headers=usuario_teste["headers"])
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_logout_sem_cookie(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.post("/api/auth/logout", headers=usuario_teste["headers"])
    assert response.status_code == 200
    logout2 = await client.post("/api/auth/logout", headers=usuario_teste["headers"])
    assert logout2.status_code == 200


@pytest.mark.asyncio
async def test_recuperar_senha(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.post(
        "/api/auth/recuperar-senha",
        json={"email": usuario_teste["email"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "instrucoes" in data["mensagem"].lower()


@pytest.mark.asyncio
async def test_recuperar_senha_anti_enumeration(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/recuperar-senha",
        json={"email": "naoexiste@example.com"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_alterar_senha(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.put(
        "/api/auth/alterar-senha",
        headers=usuario_teste["headers"],
        json={
            "senha_atual": "SenhaForte123!@#",
            "nova_senha": "NovaSenhaForte456!@#",
            "nova_senha_confirmacao": "NovaSenhaForte456!@#",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_alterar_senha_historico(client: AsyncClient, usuario_teste: dict) -> None:
    response1 = await client.put(
        "/api/auth/alterar-senha",
        headers=usuario_teste["headers"],
        json={
            "senha_atual": "SenhaForte123!@#",
            "nova_senha": "SegundaSenha789!@#",
            "nova_senha_confirmacao": "SegundaSenha789!@#",
        },
    )
    assert response1.status_code == 200

    response2 = await client.put(
        "/api/auth/alterar-senha",
        headers=usuario_teste["headers"],
        json={
            "senha_atual": "SegundaSenha789!@#",
            "nova_senha": "SenhaForte123!@#",
            "nova_senha_confirmacao": "SenhaForte123!@#",
        },
    )
    assert response2.status_code == 400
    assert "ultimas senhas" in response2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_alterar_senha_necessita_totp_com_mfa(client: AsyncClient, monkeypatch) -> None:
    import pyotp

    cadastro = await client.post(
        "/api/auth/cadastro",
        json={
            "nome": "MFA User",
            "email": "mfatest@example.com",
            "senha": "SenhaForteMFA123!@#",
            "senha_confirmacao": "SenhaForteMFA123!@#",
        },
    )
    assert cadastro.status_code == 201
    headers = {"Authorization": f"Bearer {cadastro.json()['access_token']}"}

    config = await client.post(
        "/api/auth/mfa/configurar",
        headers=headers,
        json={"nome": "Meu Celular"},
    )
    assert config.status_code == 200
    segredo = config.json()["segredo"]
    dispositivo_id = config.json()["dispositivo_id"]

    totp = pyotp.TOTP(segredo)
    codigo = totp.now()

    ativar = await client.post(
        "/api/auth/mfa/ativar",
        headers=headers,
        json={
            "dispositivo_id": dispositivo_id,
            "codigo": codigo,
            "senha_confirmacao": "SenhaForteMFA123!@#",
        },
    )
    assert ativar.status_code == 200

    alterar = await client.put(
        "/api/auth/alterar-senha",
        headers=headers,
        json={
            "senha_atual": "SenhaForteMFA123!@#",
            "nova_senha": "NovaSenhaMFA456!@#",
            "nova_senha_confirmacao": "NovaSenhaMFA456!@#",
        },
    )
    assert alterar.status_code == 401

    # Anti-replay: o código usado na ativação não pode ser reutilizado
    # (ultimo_codigo) e valid_window=0 só aceita a janela atual. Desloca o
    # relógio do pyotp em +30s (cliente e servidor — mesmo processo) para obter
    # um código novo e válido sem esperar a próxima janela real.
    import datetime as _dt

    orig_timecode = pyotp.TOTP.timecode

    def timecode_adiantado(self, for_time):
        return orig_timecode(self, for_time + _dt.timedelta(seconds=30))

    monkeypatch.setattr(pyotp.TOTP, "timecode", timecode_adiantado)
    codigo2 = totp.now()
    alterar2 = await client.put(
        "/api/auth/alterar-senha",
        headers=headers,
        json={
            "senha_atual": "SenhaForteMFA123!@#",
            "nova_senha": "NovaSenhaMFA456!@#",
            "nova_senha_confirmacao": "NovaSenhaMFA456!@#",
            "codigo_totp": codigo2,
        },
    )
    assert alterar2.status_code == 200


@pytest.mark.asyncio
async def test_mfa_remover_necessita_totp(client: AsyncClient) -> None:
    import pyotp

    cadastro = await client.post(
        "/api/auth/cadastro",
        json={
            "nome": "MFA Remove User",
            "email": "mfaremove@example.com",
            "senha": "SenhaForteMFAR123!@#",
            "senha_confirmacao": "SenhaForteMFAR123!@#",
        },
    )
    assert cadastro.status_code == 201
    headers = {"Authorization": f"Bearer {cadastro.json()['access_token']}"}

    config = await client.post(
        "/api/auth/mfa/configurar",
        headers=headers,
        json={"nome": "Celular Remover"},
    )
    assert config.status_code == 200
    segredo = config.json()["segredo"]
    dispositivo_id = config.json()["dispositivo_id"]

    totp = pyotp.TOTP(segredo)
    codigo = totp.now()

    ativar = await client.post(
        "/api/auth/mfa/ativar",
        headers=headers,
        json={
            "dispositivo_id": dispositivo_id,
            "codigo": codigo,
            "senha_confirmacao": "SenhaForteMFAR123!@#",
        },
    )
    assert ativar.status_code == 200

    remover_sem_totp = await client.request(
        "DELETE",
        f"/api/auth/mfa/{dispositivo_id}",
        headers={**headers, "Content-Type": "application/json"},
        json={"codigo_totp": "000000"},
    )
    assert remover_sem_totp.status_code == 401

    codigo2 = totp.now()
    remover = await client.request(
        "DELETE",
        f"/api/auth/mfa/{dispositivo_id}",
        headers={**headers, "Content-Type": "application/json"},
        json={"codigo_totp": codigo2},
    )
    assert remover.status_code == 200


@pytest.mark.asyncio
async def test_cache_control_header(client: AsyncClient, usuario_teste: dict) -> None:
    response = await client.get("/api/auth/me", headers=usuario_teste["headers"])
    assert response.status_code == 200
    cache_control = response.headers.get("cache-control", "")
    assert "no-store" in cache_control
    assert "no-cache" in cache_control
