import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.excecoes import CredenciaisInvalidas, EmailJaExiste, SenhaAtualIncorreta, SenhaForteRequerida
from app.core.seguranca import (
    gerar_jwt_access_token,
    gerar_jwt_refresh_token,
    gerar_jwt_temporario,
    gerar_reset_token,
    hash_refresh_token,
    hash_senha,
    hash_token,
    precisa_rehash,
    validar_forca_senha,
    verificar_hash_legado,
    verificar_senha,
)
from app.models.reset_senha_token import ResetSenhaToken
from app.models.sessao import Sessao
from app.models.usuario import Usuario

logger = logging.getLogger(__name__)


async def login(
    db: AsyncSession,
    email: str,
    senha: str,
    ip: str,
    user_agent: str,
) -> dict[str, Any]:
    inicio = time.time()
    email_normalizado = email.strip().lower()

    resultado = await db.execute(select(Usuario).where(Usuario.email == email_normalizado))
    usuario = resultado.scalar_one_or_none()

    if not usuario:
        await _garantir_tempo(inicio)
        logger.info(
            "login_fail_user_not_found",
            extra={
                "event_type": "auth.login.fail",
                "email": email_normalizado,
                "ip": ip,
                "reason": "user_not_found",
            },
        )
        raise CredenciaisInvalidas()

    if not usuario.ativo:
        await _garantir_tempo(inicio)
        raise CredenciaisInvalidas()

    senha_valida = verificar_senha(senha, usuario.senha_hash)

    if not senha_valida:
        senha_valida = verificar_hash_legado(senha, usuario.senha_hash)
        if senha_valida and precisa_rehash(usuario.senha_hash):
            usuario.senha_hash = hash_senha(senha)

    if not senha_valida:
        await _garantir_tempo(inicio)
        logger.info(
            "login_fail_invalid_password",
            extra={
                "event_type": "auth.login.fail",
                "email": email_normalizado,
                "ip": ip,
                "reason": "invalid_password",
            },
        )
        raise CredenciaisInvalidas()

    await _garantir_tempo(inicio)

    if usuario.mfa_ativo:
        token_temp = gerar_jwt_temporario(str(usuario.id))
        return {"mfa_requerido": True, "tipo": "totp", "token_temporario": token_temp}

    access_token = gerar_jwt_access_token(
        str(usuario.id), usuario.email, usuario.mfa_ativo
    )
    refresh_token = gerar_jwt_refresh_token()
    refresh_hash = hash_refresh_token(refresh_token)

    sessao = Sessao(
        usuario_id=usuario.id,
        token_hash=refresh_hash,
        ip=ip,
        user_agent=user_agent,
        expira_em=datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_token_expires),
    )
    db.add(sessao)
    await db.commit()

    logger.info(
        "login_success",
        extra={
            "event_type": "auth.login.success",
            "usuario_id": str(usuario.id),
            "email": email_normalizado,
            "ip": ip,
            "mfa": usuario.mfa_ativo,
        },
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


async def login_mfa_verificar(
    db: AsyncSession,
    token_temporario: str,
    codigo_totp: str,
    ip: str,
    user_agent: str,
) -> dict[str, Any]:
    from app.services.mfa_service import obter_dispositivos_usuario, verificar_totp_codigo

    payload = _decodificar_temporario(token_temporario)
    usuario_id = payload["sub"]

    resultado = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = resultado.scalar_one_or_none()

    if not usuario or not usuario.ativo:
        raise CredenciaisInvalidas()

    dispositivos = await obter_dispositivos_usuario(db, usuario_id)
    if not dispositivos:
        raise CredenciaisInvalidas()

    codigo_valido = False
    for disp in dispositivos:
        if disp.tipo == "totp" and disp.segredo_totp:
            if disp.ultimo_codigo == codigo_totp:
                continue
            if verificar_totp_codigo(disp.segredo_totp, codigo_totp):
                disp.ultimo_codigo = codigo_totp
                disp.ultimo_uso = datetime.now(UTC)
                codigo_valido = True
                break

    if not codigo_valido:
        raise CredenciaisInvalidas()

    access_token = gerar_jwt_access_token(
        str(usuario.id), usuario.email, usuario.mfa_ativo
    )
    refresh_token = gerar_jwt_refresh_token()
    refresh_hash = hash_refresh_token(refresh_token)

    sessao = Sessao(
        usuario_id=usuario.id,
        token_hash=refresh_hash,
        ip=ip,
        user_agent=user_agent,
        expira_em=datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_token_expires),
    )
    db.add(sessao)
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


async def cadastro(
    db: AsyncSession,
    nome: str,
    email: str,
    senha: str,
    senha_confirmacao: str,
    ip: str,
    user_agent: str,
) -> dict[str, Any]:
    email_normalizado = email.strip().lower()

    if senha != senha_confirmacao:
        raise SenhaForteRequerida("As senhas nao conferem")

    valida, erro = await validar_forca_senha(senha)
    if not valida:
        raise SenhaForteRequerida(erro)

    existente = await db.execute(select(Usuario).where(Usuario.email == email_normalizado))
    if existente.scalar_one_or_none():
        raise EmailJaExiste()

    usuario = Usuario(
        email=email_normalizado,
        nome=nome.strip(),
        senha_hash=hash_senha(senha),
    )
    db.add(usuario)
    await db.flush()

    access_token = gerar_jwt_access_token(
        str(usuario.id), usuario.email, usuario.mfa_ativo
    )
    refresh_token = gerar_jwt_refresh_token()
    refresh_hash = hash_refresh_token(refresh_token)

    sessao = Sessao(
        usuario_id=usuario.id,
        token_hash=refresh_hash,
        ip=ip,
        user_agent=user_agent,
        expira_em=datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_token_expires),
    )
    db.add(sessao)
    await db.commit()

    logger.info(
        "cadastro",
        extra={
            "event_type": "auth.register.success",
            "usuario_id": str(usuario.id),
            "email": email_normalizado,
            "ip": ip,
        },
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "usuario": {
            "id": str(usuario.id),
            "email": usuario.email,
            "nome": usuario.nome,
        },
    }


async def logout(db: AsyncSession, usuario_id: str, refresh_token: str) -> None:
    if refresh_token:
        refresh_hash = hash_refresh_token(refresh_token)
        resultado = await db.execute(
            select(Sessao).where(
                Sessao.usuario_id == usuario_id,
                Sessao.token_hash == refresh_hash,
                Sessao.revogada.is_(False),
            )
        )
        sessao = resultado.scalar_one_or_none()
        if sessao:
            sessao.revogada = True
    else:
        await _revogar_todas_sessoes(db, usuario_id)
    await db.commit()

    try:
        from app.core.user_cache import invalidate_user

        await invalidate_user(usuario_id)
    except Exception:
        pass


async def refresh_access_token(db: AsyncSession, refresh_token: str, ip: str, user_agent: str) -> dict[str, Any]:
    refresh_hash = hash_refresh_token(refresh_token)

    resultado = await db.execute(
        select(Sessao).where(
            Sessao.token_hash == refresh_hash,
            Sessao.revogada.is_(False),
        )
    )
    sessao = resultado.scalar_one_or_none()

    if not sessao:
        raise CredenciaisInvalidas()

    agora = datetime.now(UTC)
    if sessao.expira_em < agora:
        sessao.revogada = True
        await db.commit()
        raise CredenciaisInvalidas()

    resultado_usuario = await db.execute(select(Usuario).where(Usuario.id == sessao.usuario_id))
    usuario = resultado_usuario.scalar_one_or_none()

    if not usuario or not usuario.ativo:
        sessao.revogada = True
        await db.commit()
        raise CredenciaisInvalidas()

    novo_access_token = gerar_jwt_access_token(
        str(usuario.id), usuario.email, usuario.mfa_ativo
    )
    novo_refresh_token = gerar_jwt_refresh_token()
    novo_refresh_hash = hash_refresh_token(novo_refresh_token)

    sessao.revogada = True

    nova_sessao = Sessao(
        usuario_id=usuario.id,
        token_hash=novo_refresh_hash,
        ip=ip,
        user_agent=user_agent,
        expira_em=agora + timedelta(seconds=settings.jwt_refresh_token_expires),
    )
    db.add(nova_sessao)
    await db.commit()

    return {
        "access_token": novo_access_token,
        "refresh_token": novo_refresh_token,
        "token_type": "bearer",
    }


async def obter_usuario_atual(db: AsyncSession, usuario_id: str) -> Usuario:
    resultado = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = resultado.scalar_one_or_none()
    if not usuario:
        from app.core.excecoes import TokenInvalido
        raise TokenInvalido()
    return usuario


async def alterar_senha(
    db: AsyncSession,
    usuario_id: str,
    senha_atual: str,
    nova_senha: str,
    nova_senha_confirmacao: str,
    codigo_totp: str | None = None,
) -> None:
    if nova_senha != nova_senha_confirmacao:
        raise SenhaForteRequerida("As senhas nao conferem")

    valida, erro = await validar_forca_senha(nova_senha)
    if not valida:
        raise SenhaForteRequerida(erro)

    resultado = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = resultado.scalar_one_or_none()
    if not usuario:
        from app.core.excecoes import TokenInvalido
        raise TokenInvalido()

    if not verificar_senha(senha_atual, usuario.senha_hash):
        raise SenhaAtualIncorreta()

    if usuario.mfa_ativo:
        await _verificar_mfa_se_ativo(db, usuario_id, codigo_totp)

    await _verificar_historico_senhas(db, usuario_id, nova_senha)

    await _salvar_historico_senha(db, usuario_id, usuario.senha_hash)

    usuario.senha_hash = hash_senha(nova_senha)

    await _revogar_todas_sessoes(db, usuario_id)
    await db.commit()

    logger.info(
        "senha_alterada",
        extra={
            "event_type": "auth.password_changed",
            "usuario_id": usuario_id,
        },
    )

    try:
        from app.core.user_cache import invalidate_user

        await invalidate_user(usuario_id)
    except Exception:
        pass


async def recuperar_senha(db: AsyncSession, email: str) -> None:
    inicio = time.time()
    email_normalizado = email.strip().lower()

    resultado = await db.execute(select(Usuario).where(Usuario.email == email_normalizado))
    usuario = resultado.scalar_one_or_none()

    if usuario:
        token = gerar_reset_token()
        token_hash = hash_token(token)

        reset = ResetSenhaToken(
            usuario_id=usuario.id,
            token_hash=token_hash,
            expira_em=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(reset)
        await db.commit()

        logger.info(
            "reset_senha_solicitado",
            extra={
                "event_type": "auth.password_reset.requested",
                "usuario_id": str(usuario.id),
                "email": email_normalizado,
            },
        )

    await _garantir_tempo(inicio)


async def resetar_senha(
    db: AsyncSession,
    token: str,
    nova_senha: str,
    nova_senha_confirmacao: str,
) -> None:
    if nova_senha != nova_senha_confirmacao:
        raise SenhaForteRequerida("As senhas nao conferem")

    valida, erro = await validar_forca_senha(nova_senha)
    if not valida:
        raise SenhaForteRequerida(erro)

    token_hash = hash_token(token)
    agora = datetime.now(UTC)

    resultado = await db.execute(
        select(ResetSenhaToken).where(
            ResetSenhaToken.token_hash == token_hash,
            ResetSenhaToken.usado.is_(False),
            ResetSenhaToken.expira_em > agora,
        )
    )
    reset_token = resultado.scalar_one_or_none()

    if not reset_token:
        from app.core.excecoes import TokenInvalido
        raise TokenInvalido("Token invalido ou expirado")

    reset_token.usado = True

    resultado_usuario = await db.execute(select(Usuario).where(Usuario.id == reset_token.usuario_id))
    usuario = resultado_usuario.scalar_one_or_none()

    if not usuario:
        from app.core.excecoes import TokenInvalido
        raise TokenInvalido()

    senha_hash_antiga = usuario.senha_hash

    await _verificar_historico_senhas(db, str(usuario.id), nova_senha)

    await _salvar_historico_senha(db, str(usuario.id), senha_hash_antiga)
    usuario.senha_hash = hash_senha(nova_senha)

    await _revogar_todas_sessoes(db, str(usuario.id))
    await db.commit()

    logger.info(
        "senha_resetada",
        extra={
            "event_type": "auth.password_reset.completed",
            "usuario_id": str(usuario.id),
        },
    )

    try:
        from app.core.user_cache import invalidate_user

        await invalidate_user(str(usuario.id))
    except Exception:
        pass


async def _revogar_todas_sessoes(db: AsyncSession, usuario_id: str) -> None:
    resultado = await db.execute(
        select(Sessao).where(Sessao.usuario_id == usuario_id, Sessao.revogada.is_(False))
    )
    sessoes = resultado.scalars().all()
    for sessao in sessoes:
        sessao.revogada = True


async def _garantir_tempo(inicio: float) -> None:
    import asyncio
    decorrido = time.time() - inicio
    tempo_minimo = settings.login_response_time
    if decorrido < tempo_minimo:
        await asyncio.sleep(tempo_minimo - decorrido)


def _decodificar_temporario(token_temporario: str) -> dict[str, Any]:
    import jwt as pyjwt
    try:
        return pyjwt.decode(
            token_temporario,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except pyjwt.ExpiredSignatureError:
        from app.core.excecoes import TokenInvalido
        raise TokenInvalido("Token temporario expirado") from None
    except pyjwt.InvalidTokenError:
        from app.core.excecoes import TokenInvalido
        raise TokenInvalido("Token temporario invalido") from None


async def _verificar_mfa_se_ativo(db: AsyncSession, usuario_id: str, codigo_totp: str | None) -> None:
    from app.services.mfa_service import obter_dispositivos_usuario, verificar_totp_codigo

    if not codigo_totp:
        from app.core.excecoes import MfaCodigoInvalido
        raise MfaCodigoInvalido()

    dispositivos = await obter_dispositivos_usuario(db, usuario_id)
    codigo_valido = False
    for disp in dispositivos:
        if disp.tipo == "totp" and disp.segredo_totp:
            if disp.ultimo_codigo == codigo_totp:
                continue
            if verificar_totp_codigo(disp.segredo_totp, codigo_totp):
                disp.ultimo_codigo = codigo_totp
                disp.ultimo_uso = datetime.now(UTC)
                codigo_valido = True
                break

    if not codigo_valido:
        from app.core.excecoes import MfaCodigoInvalido
        raise MfaCodigoInvalido()


async def _verificar_historico_senhas(db: AsyncSession, usuario_id: str, nova_senha: str) -> None:
    from app.models.historico_senha import HistoricoSenha

    resultado = await db.execute(
        select(HistoricoSenha.senha_hash)
        .where(HistoricoSenha.usuario_id == usuario_id)
        .order_by(HistoricoSenha.criado_em.desc())
        .limit(5)
    )
    hashes = resultado.scalars().all()

    for h in hashes:
        if verificar_senha(nova_senha, h):
            raise SenhaForteRequerida("Nova senha nao pode ser igual a uma das 5 ultimas senhas")


async def _salvar_historico_senha(db: AsyncSession, usuario_id: str, senha_hash: str) -> None:
    from app.models.historico_senha import HistoricoSenha

    registro = HistoricoSenha(usuario_id=usuario_id, senha_hash=senha_hash)
    db.add(registro)
