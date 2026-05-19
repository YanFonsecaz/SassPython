import datetime
import hashlib
import hmac
import logging
import re
import secrets
from typing import Any

import argon2
import jwt
import pyotp
from cryptography.fernet import Fernet
from zxcvbn import zxcvbn

from app.config import settings

logger = logging.getLogger(__name__)

ph = argon2.PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    salt_len=16,
    hash_len=32,
    type=argon2.Type.ID,
)


def hash_senha(senha: str) -> str:
    return ph.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        return ph.verify(senha_hash, senha)
    except argon2.exceptions.VerifyMismatchError:
        return False


def precisa_rehash(senha_hash: str) -> bool:
    return ph.check_needs_rehash(senha_hash)


LEGACY_HASH_CUTOFF = datetime.datetime(2026, 7, 15, tzinfo=datetime.UTC)


def verificar_hash_legado(senha: str, senha_hash: str) -> bool:
    if datetime.datetime.now(datetime.UTC) >= LEGACY_HASH_CUTOFF:
        logger.warning("legacy_hash_cutoff_bloqueado")
        return False
    logger.info("legacy_hash_verificado")
    legacy_hash = hashlib.sha256(senha.encode()).hexdigest()
    return secrets.compare_digest(legacy_hash, senha_hash)


def gerar_jwt_access_token(usuario_id: str, email: str, mfa_ativo: bool) -> str:
    agora = _agora_timestamp()
    payload = {
        "sub": usuario_id,
        "email": email,
        "mfa_ativo": mfa_ativo,
        "tipo": "access",
        "iat": agora,
        "exp": agora + settings.jwt_access_token_expires,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def gerar_jwt_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def gerar_jwt_temporario(usuario_id: str) -> str:
    agora = _agora_timestamp()
    payload = {
        "sub": usuario_id,
        "tipo": "temp",
        "iat": agora,
        "exp": agora + 300,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decodificar_jwt(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_refresh_token(token: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()


def gerar_reset_token() -> str:
    return secrets.token_urlsafe(32)


def gerar_totp_secret() -> str:
    return pyotp.random_base32()


def criar_totp(segredo: str) -> pyotp.TOTP:
    return pyotp.TOTP(segredo)


def verificar_totp(segredo: str, codigo: str) -> bool:
    totp = pyotp.TOTP(segredo)
    return totp.verify(codigo, valid_window=0)


def criptografar_segredo(segredo: str) -> str:
    fernet = _get_fernet()
    return fernet.encrypt(segredo.encode()).decode()


def descriptografar_segredo(segredo_criptografado: str) -> str:
    fernet = _get_fernet()
    return fernet.decrypt(segredo_criptografado.encode()).decode()


async def validar_forca_senha(senha: str) -> tuple[bool, str]:
    if len(senha) < 12:
        return False, "Senha deve ter no minimo 12 caracteres"
    if len(senha) > 64:
        return False, "Senha deve ter no maximo 64 caracteres"
    if not re.search(r"[A-Z]", senha):
        return False, "Senha deve ter pelo menos uma letra maiuscula"
    if not re.search(r"[a-z]", senha):
        return False, "Senha deve ter pelo menos uma letra minuscula"
    if not re.search(r"\d", senha):
        return False, "Senha deve ter pelo menos um numero"
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", senha):
        return False, "Senha deve ter pelo menos um caractere especial"

    resultado_zxcvbn = zxcvbn(senha)
    if resultado_zxcvbn["score"] < 3:
        return False, "Senha muito fraca. Escolha uma senha mais complexa e diferente de informacoes pessoais."

    if settings.ambiente != "teste":
        hibp = await _verificar_hibp(senha)
        if hibp is True:
            return False, "Senha comprometida em vazamentos conhecidos"
        if hibp is None:
            if settings.hibp_fail_mode == "closed":
                return False, "Servico de verificacao indisponivel, tente novamente"
            if settings.hibp_fail_mode == "queue":
                logger.warning("hibp_fail_queue_senha_nao_validada")

    return True, ""


def gerar_csrf_nonce() -> str:
    return secrets.token_hex(16)


def _agora_timestamp() -> int:
    import time
    return int(time.time())


def _get_fernet() -> Fernet:
    return Fernet(settings.encryption_key.encode())


async def _verificar_hibp(senha: str) -> bool | None:
    import httpx

    sha1 = hashlib.sha256(senha.encode()).hexdigest().upper()[:40]
    prefixo, sufixo = sha1[:5], sha1[5:]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"https://api.pwnedpasswords.com/range/{prefixo}")
            resp.raise_for_status()
    except Exception:
        logger.warning("HIBP indisponivel")
        return None

    for linha in resp.text.splitlines():
        hash_parte, _ = linha.split(":")
        if hash_parte == sufixo:
            return True

    return False
