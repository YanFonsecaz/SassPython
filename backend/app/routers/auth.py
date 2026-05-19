import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.seguranca import gerar_csrf_nonce
from app.dependencies import get_current_user, get_db, rate_limit
from app.models.usuario import Usuario
from app.schemas.auth import (
    AlterarSenhaRequest,
    CadastroRequest,
    LoginRequest,
    MensagemResponse,
    MfaAtivarRequest,
    MfaConfigurarRequest,
    MfaConfigurarResponse,
    MfaRemoverRequest,
    MfaRequeridoResponse,
    MfaVerificarRequest,
    RecuperarSenhaRequest,
    RefreshTokenResponse,
    ResetarSenhaRequest,
    TokenResponse,
    UsuarioResponse,
)
from app.services import auth_service, mfa_service

logger = logging.getLogger(__name__)
router = APIRouter()

REFRESH_COOKIE_KEY = "refresh_token"
COOKIE_SECURE = settings.ambiente != "desenvolvimento"
COOKIE_SAMESITE: str = "lax" if settings.ambiente == "desenvolvimento" else "strict"
COOKIE_CONFIG = {
    "httponly": True,
    "secure": COOKIE_SECURE,
    "samesite": COOKIE_SAMESITE,
    "path": "/",
    "max_age": 604800,
}


def _set_refresh_cookie(response: Response, refresh_token: str) -> str:
    response.set_cookie(REFRESH_COOKIE_KEY, refresh_token, **COOKIE_CONFIG)
    csrf_token = gerar_csrf_nonce()
    response.set_cookie(
        "csrf_token",
        csrf_token,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=604800,
    )
    return csrf_token


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_KEY, path="/")
    response.delete_cookie("csrf_token", path="/")


def _extract_cookie_from_header(request: Request, name: str) -> str:
    raw = request.headers.get("cookie", "")
    for part in raw.split(";"):
        kv = part.strip()
        if kv.startswith(f"{name}="):
            return kv[len(name) + 1 :]
    return ""


@router.post(
    "/cadastro",
    response_model=TokenResponse,
    status_code=201,
)
async def cadastro(
    body: CadastroRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("cadastro", max_requests=3, window_seconds=900, fail_mode="closed")),
) -> dict[str, Any]:
    resultado = await auth_service.cadastro(
        db=db,
        nome=body.nome,
        email=body.email,
        senha=body.senha,
        senha_confirmacao=body.senha_confirmacao,
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    csrf = _set_refresh_cookie(response, resultado["refresh_token"])
    return {"access_token": resultado["access_token"], "refresh_token": resultado["refresh_token"], "token_type": "bearer", "csrf_token": csrf}


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: {"description": "Credenciais invalidas"}, 200: {"model": MfaRequeridoResponse}},
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("login", max_requests=5, window_seconds=900, progressive=True, fail_mode="closed")),
) -> dict[str, Any]:
    resultado = await auth_service.login(
        db=db,
        email=body.email,
        senha=body.senha,
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )

    if resultado.get("mfa_requerido"):
        return {
            "mfa_requerido": True,
            "tipo": resultado["tipo"],
            "token_temporario": resultado["token_temporario"],
        }

    csrf = _set_refresh_cookie(response, resultado["refresh_token"])
    return {"access_token": resultado["access_token"], "refresh_token": resultado["refresh_token"], "token_type": "bearer", "csrf_token": csrf}


@router.post("/mfa/verificar", response_model=TokenResponse)
async def mfa_verificar(
    body: MfaVerificarRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("mfa_verify", max_requests=10, window_seconds=900, fail_mode="closed")),
) -> dict[str, Any]:
    resultado = await auth_service.login_mfa_verificar(
        db=db,
        token_temporario=body.token_temporario,
        codigo_totp=body.codigo_totp,
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    _set_refresh_cookie(response, resultado["refresh_token"])
    return {"access_token": resultado["access_token"], "refresh_token": resultado["refresh_token"], "token_type": "bearer"}


@router.post("/logout", response_model=MensagemResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    refresh_token = (
        request.cookies.get(REFRESH_COOKIE_KEY, "")
        or _extract_cookie_from_header(request, REFRESH_COOKIE_KEY)
    )
    await auth_service.logout(db, str(usuario.id), refresh_token)
    _clear_refresh_cookie(response)
    return {"mensagem": "Logout realizado"}


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    refresh_token = (
        request.cookies.get(REFRESH_COOKIE_KEY)
        or _extract_cookie_from_header(request, REFRESH_COOKIE_KEY)
    )
    if not refresh_token:
        try:
            body = await request.json()
            refresh_token = body.get("refresh_token") if body else None
        except Exception:
            pass
    if not refresh_token:
        from app.core.excecoes import TokenInvalido

        raise TokenInvalido()

    resultado = await auth_service.refresh_access_token(
        db=db,
        refresh_token=refresh_token,
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    csrf = _set_refresh_cookie(response, resultado["refresh_token"])
    return {"access_token": resultado["access_token"], "refresh_token": resultado["refresh_token"], "token_type": "bearer", "csrf_token": csrf}


@router.get("/me", response_model=UsuarioResponse)
async def me(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    plano = None
    if usuario.plano_id:
        from sqlalchemy import select

        from app.models.plano import Plano

        resultado = await db.execute(select(Plano).where(Plano.id == usuario.plano_id))
        plano_obj = resultado.scalar_one_or_none()
        if plano_obj:
            plano = plano_obj.nome
    return {
        "id": usuario.id,
        "email": usuario.email,
        "nome": usuario.nome,
        "mfa_ativo": usuario.mfa_ativo,
        "email_verificado": usuario.email_verificado,
        "plano": plano,
        "criado_em": usuario.criado_em,
    }


@router.put("/alterar-senha", response_model=MensagemResponse)
async def alterar_senha(
    body: AlterarSenhaRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    await auth_service.alterar_senha(
        db=db,
        usuario_id=str(usuario.id),
        senha_atual=body.senha_atual,
        nova_senha=body.nova_senha,
        nova_senha_confirmacao=body.nova_senha_confirmacao,
        codigo_totp=body.codigo_totp,
    )
    return {"mensagem": "Senha alterada com sucesso"}


@router.post("/recuperar-senha", response_model=MensagemResponse)
async def recuperar_senha(
    body: RecuperarSenhaRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("forgot", max_requests=3, window_seconds=3600, fail_mode="closed")),
) -> dict[str, Any]:
    await auth_service.recuperar_senha(db=db, email=body.email)
    return {"mensagem": "Se este e-mail esta cadastrado, voce recebera as instrucoes."}


@router.post("/resetar-senha", response_model=MensagemResponse)
async def resetar_senha(
    body: ResetarSenhaRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("reset", max_requests=5, window_seconds=60, fail_mode="closed")),
) -> dict[str, Any]:
    await auth_service.resetar_senha(
        db=db,
        token=body.token,
        nova_senha=body.nova_senha,
        nova_senha_confirmacao=body.nova_senha_confirmacao,
    )
    return {"mensagem": "Senha alterada com sucesso"}


@router.post("/mfa/configurar", response_model=MfaConfigurarResponse)
async def mfa_configurar(
    body: MfaConfigurarRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    resultado = await mfa_service.configurar_totp(
        db=db,
        usuario_id=str(usuario.id),
        nome=body.nome,
    )
    return resultado


@router.post("/mfa/ativar", response_model=MensagemResponse)
async def mfa_ativar(
    body: MfaAtivarRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    await mfa_service.ativar_totp(
        db=db,
        usuario_id=str(usuario.id),
        dispositivo_id=body.dispositivo_id,
        codigo=body.codigo,
        senha_confirmacao=body.senha_confirmacao,
    )
    return {"mensagem": "MFA ativado com sucesso"}


@router.delete("/mfa/{dispositivo_id}", response_model=MensagemResponse)
async def mfa_remover(
    dispositivo_id: str,
    body: MfaRemoverRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    await mfa_service.remover_dispositivo(
        db=db,
        usuario_id=str(usuario.id),
        dispositivo_id=dispositivo_id,
        codigo_totp=body.codigo_totp,
    )
    return {"mensagem": "Dispositivo MFA removido"}
