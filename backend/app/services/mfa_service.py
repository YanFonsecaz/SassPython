import base64
import io
import logging
from typing import Any

import segno
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.excecoes import (
    MfaCodigoInvalido,
    MfaNaoAtivo,
    RecursoNaoEncontrado,
    SenhaAtualIncorreta,
)
from app.core.seguranca import (
    criptografar_segredo,
    descriptografar_segredo,
    gerar_totp_secret,
    verificar_senha,
    verificar_totp,
)
from app.models.mfa_dispositivo import MfaDispositivo
from app.models.usuario import Usuario

logger = logging.getLogger(__name__)


async def configurar_totp(
    db: AsyncSession,
    usuario_id: str,
    nome: str,
    app_name: str = "SEO SaaS",
) -> dict[str, Any]:
    resultado = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = resultado.scalar_one_or_none()
    if not usuario:
        raise RecursoNaoEncontrado()

    segredo = gerar_totp_secret()
    segredo_criptografado = criptografar_segredo(segredo)

    dispositivo = MfaDispositivo(
        usuario_id=usuario_id,
        tipo="totp",
        nome=nome,
        segredo_totp=segredo_criptografado,
    )
    db.add(dispositivo)
    await db.flush()

    totp_uri = f"otpauth://totp/{app_name}:{usuario.email}?secret={segredo}&issuer={app_name}"
    qr = segno.make(totp_uri)
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=5)
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return {
        "dispositivo_id": str(dispositivo.id),
        "qr_code_base64": qr_base64,
        "segredo": segredo,
    }


async def ativar_totp(
    db: AsyncSession,
    usuario_id: str,
    dispositivo_id: str,
    codigo: str,
    senha_confirmacao: str,
) -> None:
    resultado = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = resultado.scalar_one_or_none()
    if not usuario:
        raise RecursoNaoEncontrado()

    if not verificar_senha(senha_confirmacao, usuario.senha_hash):
        raise SenhaAtualIncorreta()

    resultado_disp = await db.execute(
        select(MfaDispositivo).where(
            MfaDispositivo.id == dispositivo_id,
            MfaDispositivo.usuario_id == usuario_id,
        )
    )
    dispositivo = resultado_disp.scalar_one_or_none()
    if not dispositivo:
        raise RecursoNaoEncontrado()

    if dispositivo.tipo != "totp" or not dispositivo.segredo_totp:
        raise MfaNaoAtivo()

    segredo = descriptografar_segredo(dispositivo.segredo_totp)

    if dispositivo.ultimo_codigo == codigo:
        raise MfaCodigoInvalido()

    if not verificar_totp(segredo, codigo):
        raise MfaCodigoInvalido()

    dispositivo.ultimo_codigo = codigo

    usuario.mfa_ativo = True
    await db.commit()

    logger.info("mfa_ativado", extra={"user_id": usuario_id})


async def obter_dispositivos_usuario(db: AsyncSession, usuario_id: str) -> list[MfaDispositivo]:
    resultado = await db.execute(
        select(MfaDispositivo).where(MfaDispositivo.usuario_id == usuario_id)
    )
    return list(resultado.scalars().all())


async def remover_dispositivo(
    db: AsyncSession,
    usuario_id: str,
    dispositivo_id: str,
    codigo_totp: str | None = None,
) -> None:
    resultado_disp = await db.execute(
        select(MfaDispositivo).where(
            MfaDispositivo.id == dispositivo_id,
            MfaDispositivo.usuario_id == usuario_id,
        )
    )
    dispositivo = resultado_disp.scalar_one_or_none()
    if not dispositivo:
        raise RecursoNaoEncontrado()

    if dispositivo.segredo_totp:
        if not codigo_totp:
            raise MfaCodigoInvalido()

        segredo = descriptografar_segredo(dispositivo.segredo_totp)
        if not verificar_totp(segredo, codigo_totp):
            raise MfaCodigoInvalido()

    await db.delete(dispositivo)

    resultado_count = await db.execute(
        select(MfaDispositivo).where(MfaDispositivo.usuario_id == usuario_id)
    )
    restantes = list(resultado_count.scalars().all())

    if not restantes:
        resultado_usuario = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
        usuario = resultado_usuario.scalar_one_or_none()
        if usuario:
            usuario.mfa_ativo = False

    await db.commit()

    logger.info("mfa_dispositivo_removido", extra={"user_id": usuario_id})


def verificar_totp_codigo(segredo_criptografado: str, codigo: str) -> bool:
    from app.core.seguranca import verificar_totp

    segredo = descriptografar_segredo(segredo_criptografado)
    return verificar_totp(segredo, codigo)
