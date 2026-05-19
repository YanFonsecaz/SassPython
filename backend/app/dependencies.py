import contextlib
import logging
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.excecoes import RateLimitExcedido, TokenInvalido
from app.core.middleware import get_client_ip
from app.core.seguranca import decodificar_jwt
from app.core.user_cache import get_user, set_user
from app.db.session import async_session_factory
from app.models.usuario import Usuario

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _usuario_to_dict(usuario: Usuario) -> dict[str, Any]:
    return {
        "id": str(usuario.id),
        "email": usuario.email,
        "nome": usuario.nome,
        "ativo": usuario.ativo,
        "plano_id": str(usuario.plano_id) if usuario.plano_id else None,
        "mfa_ativo": usuario.mfa_ativo,
        "email_verificado": usuario.email_verificado,
        "criado_em": usuario.criado_em.isoformat() if usuario.criado_em else None,
    }


def _dict_to_usuario(data: dict[str, Any]) -> Usuario:
    from datetime import datetime

    usuario = Usuario()
    usuario.id = data["id"]
    usuario.email = data["email"]
    usuario.nome = data["nome"]
    usuario.ativo = data["ativo"]
    usuario.plano_id = data.get("plano_id")
    usuario.mfa_ativo = data.get("mfa_ativo", False)
    usuario.email_verificado = data.get("email_verificado", False)
    criado_em = data.get("criado_em")
    usuario.criado_em = datetime.fromisoformat(criado_em) if criado_em else None
    return usuario


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Usuario:
    if not credentials:
        raise TokenInvalido()

    token = credentials.credentials
    try:
        payload = decodificar_jwt(token)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise TokenInvalido() from None

    if payload.get("tipo") != "access":
        raise TokenInvalido()

    usuario_id = payload.get("sub")
    if not usuario_id:
        raise TokenInvalido()

    try:
        cached = await get_user(str(usuario_id))
        if cached is not None:
            return _dict_to_usuario(cached)
    except Exception:
        pass

    resultado = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = resultado.scalar_one_or_none()

    if not usuario:
        raise TokenInvalido()

    if not usuario.ativo:
        raise TokenInvalido()

    with contextlib.suppress(Exception):
        await set_user(str(usuario_id), _usuario_to_dict(usuario))

    return usuario


def rate_limit(key_prefix: str, max_requests: int, window_seconds: int, progressive: bool = False, fail_mode: str = "open"):
    async def _check(request: Request):
        client_ip = get_client_ip(request)
        try:
            from app.core.rate_limit import check_rate_limit_redis

            key = f"rl:{key_prefix}:{client_ip}"
            if not await check_rate_limit_redis(key, max_requests, window_seconds):
                raise RateLimitExcedido()
        except RateLimitExcedido:
            raise
        except Exception as exc:
            if fail_mode == "closed":
                logger.error("rate_limit_redis_indisponivel_fail_closed", extra={"key_prefix": key_prefix})
                raise RateLimitExcedido("Servico de rate limit indisponivel") from exc
            # fail-open: redis indisponivel mas seguimos (log warning ja feito em check_rate_limit_redis)

    return _check


def rate_limit_autenticado(key_prefix: str, max_requests: int, window_seconds: int):
    async def _check(
        request: Request,
        usuario: Usuario = Depends(get_current_user),
    ):
        bucket = str(usuario.id)
        key = f"rl:{key_prefix}:user:{bucket}"
        try:
            from app.core.rate_limit import check_rate_limit_redis
            if not await check_rate_limit_redis(key, max_requests, window_seconds):
                raise RateLimitExcedido()
        except RateLimitExcedido:
            raise
        except Exception:
            pass

    return _check
