import re

from app.core.middleware import is_private_ip


def validar_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return False
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if not parsed.hostname:
            return False
        if is_private_ip(parsed.hostname):
            return False
        if parsed.hostname.endswith(".local") or parsed.hostname.endswith(".internal"):
            return False
        if not re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?$", parsed.hostname):
            return False
        if parsed.port and parsed.port not in (80, 443, 8080, 8443, 3000, 8000):
            return False
    except Exception:
        return False
    return True


def sanitizar_string(valor: str, max_length: int = 500) -> str:
    valor = valor.strip()
    if len(valor) > max_length:
        valor = valor[:max_length]
    return valor
