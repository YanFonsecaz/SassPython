import contextlib
import logging
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
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


# --- SPEC_CWV_Ownership_Dependencies --------------------------------------
# Ownership centralizado via Depends. Critério de aceite:
#   rg "usuario_id\) != str\(usuario\.id\)" backend/app/routers/ferramentas_cwv*.py
# deve retornar vazio.


def _dono_ou_404(obj: Any, usuario: Usuario, detail: str):
    """404 se objeto não existe OU não pertence ao usuário (não vaza existência)."""
    if not obj or str(obj.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail=detail)
    return obj


async def get_auditoria_do_usuario(
    auditoria_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Resolve ``auditoria_id`` do path, valida ownership e retorna o ORM."""
    from app.models.cwv_auditoria import CwvAuditoria

    res = await db.execute(select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id))
    return _dono_ou_404(res.scalar_one_or_none(), usuario, "Auditoria nao encontrada")


async def get_execucao_do_usuario(
    execucao_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Resolve ``execucao_id`` do path, valida ownership e retorna o ORM."""
    from app.models.execucao_ferramenta import ExecucaoFerramenta

    res = await db.execute(
        select(ExecucaoFerramenta).where(
            ExecucaoFerramenta.id == execucao_id,
            ExecucaoFerramenta.usuario_id == usuario.id,
        )
    )
    execucao = res.scalar_one_or_none()
    if not execucao:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")
    return execucao


async def get_analise_do_usuario(
    analise_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Resolve ``analise_id`` do path, valida ownership e retorna o ORM CwvAnalise."""
    from app.services.cwv_persistencia import buscar_analise_por_id

    analise = await buscar_analise_por_id(db, str(analise_id))
    if not analise or str(analise.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Analise nao encontrada")
    return analise
