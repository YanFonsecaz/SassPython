"""Page Experience: checagens por origem (HTTPS, SSL, redirect 301, headers,
Safe Browsing, mixed content, mobile-friendly).

As checagens são propriedades do domínio (não da URL individual), então rodam
uma vez por origem (``scheme://host``) derivada dos jobs da execução. Cada check
é independente e fail-open: exceção/timeout vira ``'erro'`` (inconclusivo), e
nunca derruba o workflow.

Spec: SPEC_CWV_Page_Experience (gaps #12-#15 da planilha NPBR).
"""
from __future__ import annotations

import asyncio
import logging
import ssl
from urllib.parse import urlsplit

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VEREDITOS = ("pass", "fail", "erro", "na")

# User-Agent de browser real — sites atrás de WAF bloqueiam UA de bot.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_TIMEOUT_POR_CHECK = 10  # segundos; cada check envolto em wait_for
_MAX_SALTOS_REDIRECT = 5

# Status que indicam bloqueio anti-bot/WAF, não reprovação do item auditado.
# 401/403/429 = inconclusivo, não fail. 5xx continua fail (indisponibilidade real).
_STATUS_BLOQUEIO = (401, 403, 429)

_CLIENT: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(
            timeout=_TIMEOUT_POR_CHECK,
            verify=True,
            follow_redirects=False,  # controle manual no check de redirect
            headers={"User-Agent": _BROWSER_UA},
        )
    return _CLIENT


def _origem(url: str) -> str:
    """Extrai ``scheme://netloc`` (lowercase) de uma URL."""
    p = urlsplit(url)
    return f"{p.scheme}://{(p.netloc or p.hostname or '').lower()}"


def _host(origem: str) -> str:
    return urlsplit(origem).hostname or ""


async def check_https(origem: str) -> tuple[str, dict]:
    """GET https://host — 2xx/3xx → pass; erro TLS/conexão → fail."""
    try:
        resp = await _get_client().get(origem)
        if resp.status_code in _STATUS_BLOQUEIO:
            return "na", {"status_code": resp.status_code, "motivo": "bloqueio WAF/anti-bot — inconclusivo"}
        if 200 <= resp.status_code < 400:
            return "pass", {"status_code": resp.status_code}
        return "fail", {"status_code": resp.status_code}
    except Exception as e:
        logger.debug("check_https falhou para %s: %s", origem, e)
        return "fail", {"erro": str(e)[:200]}


async def check_ssl(host: str) -> tuple[str, dict]:
    """Handshake SSL — certificado válido, cadeia confiável, não expirando em <14d."""
    if not host:
        return "erro", {"erro": "host vazio"}
    try:
        ctx = ssl.create_default_context()
        cert_info: dict = {}

        def _do_handshake() -> None:
            import socket

            with ctx.wrap_socket(socket.create_connection((host, 443), timeout=_TIMEOUT_POR_CHECK), server_hostname=host) as s:
                cert = s.getpeercert()
                cert_info["not_after"] = cert.get("notAfter") if cert else None

        await asyncio.to_thread(_do_handshake)

        # Verifica expiração (< 14 dias → fail).
        import datetime

        if cert_info.get("not_after"):
            try:
                # Formato OpenSSL: "Jul 13 21:14:00 2026 GMT"
                exp = datetime.datetime.strptime(cert_info["not_after"], "%b %d %H:%M:%S %Y %Z")
                dias = (exp - datetime.datetime.utcnow()).days
                cert_info["dias_ate_expirar"] = dias
                if dias < 14:
                    return "fail", {**cert_info, "motivo": "certificado expirando em < 14 dias"}
            except ValueError:
                pass
        return "pass", cert_info
    except ssl.SSLCertVerificationError as e:
        return "fail", {"erro": f"certificado invalido: {e.verify_message}"}
    except Exception as e:
        logger.debug("check_ssl falhou para %s: %s", host, e)
        return "fail", {"erro": str(e)[:200]}


async def check_redirect_301(origem: str) -> tuple[str, dict]:
    """Seguir http://host manualmente — pass sse primeiro salto é 301 e termina em https 2xx."""
    http_origem = origem.replace("https://", "http://", 1)
    cadeia: list[dict] = []
    try:
        client = _get_client()
        url = http_origem
        primeiro_salto = True
        for _ in range(_MAX_SALTOS_REDIRECT + 1):
            resp = await client.get(url)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location", "")
                cadeia.append({"status": resp.status_code, "location": location})
                if primeiro_salto and resp.status_code != 301:
                    return "fail", {"cadeia": cadeia, "motivo": f"primeiro salto {resp.status_code} (esperado 301)"}
                primeiro_salto = False
                # Resolve location relativo.
                if location.startswith("/"):
                    p = urlsplit(url)
                    url = f"{p.scheme}://{p.netloc}{location}"
                elif location.startswith("http"):
                    url = location
                else:
                    return "fail", {"cadeia": cadeia, "motivo": f"location invalido: {location}"}
                continue
            # Não-redirect: chegamos ao fim da cadeia.
            if resp.status_code in _STATUS_BLOQUEIO:
                cadeia.append({"status": resp.status_code, "location_final": url})
                return "na", {"cadeia": cadeia, "motivo": f"bloqueio WAF (status {resp.status_code}) — inconclusivo"}
            cadeia.append({"status": resp.status_code, "location_final": url})
            terminou_https = url.startswith("https://")
            if terminou_https and 200 <= resp.status_code < 400:
                return "pass", {"cadeia": cadeia}
            return "fail", {"cadeia": cadeia, "motivo": f"termino em {url} status {resp.status_code}"}
        return "fail", {"cadeia": cadeia, "motivo": f"mais de {_MAX_SALTOS_REDIRECT} saltos"}
    except Exception as e:
        logger.debug("check_redirect_301 falhou para %s: %s", http_origem, e)
        return "fail", {"cadeia": cadeia, "erro": str(e)[:200]}


async def check_security_headers(origem: str) -> tuple[str, dict]:
    """HSTS presente E (CSP OU X-Frame-Options) E X-Content-Type-Options: nosniff."""
    try:
        resp = await _get_client().get(origem)
        if resp.status_code in _STATUS_BLOQUEIO:
            return "na", {"status_code": resp.status_code, "motivo": "bloqueio WAF/anti-bot — headers não representam a aplicação real"}
        h = {k.lower(): v for k, v in resp.headers.items()}
        presentes = []
        ausentes = []
        for required in ("strict-transport-security",):
            (presentes if required in h else ausentes).append(required)
        # CSP ou X-Frame-Options (pelo menos um).
        if "content-security-policy" in h or "x-frame-options" in h:
            if "content-security-policy" in h:
                presentes.append("content-security-policy")
            if "x-frame-options" in h:
                presentes.append("x-frame-options")
        else:
            ausentes.extend(["content-security-policy|ou|x-frame-options"])
        if h.get("x-content-type-options", "").lower() == "nosniff":
            presentes.append("x-content-type-options")
        else:
            ausentes.append("x-content-type-options")
        if ausentes:
            return "fail", {"presentes": presentes, "ausentes": ausentes}
        return "pass", {"presentes": presentes}
    except Exception as e:
        logger.debug("check_security_headers falhou para %s: %s", origem, e)
        return "erro", {"erro": str(e)[:200]}


async def check_safe_browsing(origem: str) -> tuple[str, dict]:
    """POST Safe Browsing API — matches vazio → pass; sem key → 'na' (sem request)."""
    key = settings.api_safe_browsing_key
    if not key:
        return "na", {}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_POR_CHECK) as client:
            resp = await client.post(
                f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={key}",
                json={
                    "threatInfo": {
                        "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
                        "platformTypes": ["ANY_PLATFORM"],
                        "threatEntryTypes": ["URL"],
                        "threatEntries": [{"url": origem}],
                    }
                },
            )
            resp.raise_for_status()
            data = resp.json()
            matches = data.get("matches") or []
            if matches:
                return "fail", {"threats": [m.get("threatType") for m in matches]}
            return "pass", {}
    except Exception as e:
        logger.debug("check_safe_browsing falhou para %s: %s", origem, e)
        return "erro", {"erro": str(e)[:200]}


async def check_mixed_content(payloads: list[dict]) -> tuple[str, dict]:
    """Sem rede — varre network-requests dos payloads por recurso http em página https."""
    http_recursos: list[str] = []
    for payload in payloads:
        lh = payload.get("lighthouseResult") or {}
        final_url = lh.get("finalUrl") or ""
        if not final_url.startswith("https://"):
            continue  # mixed content só aplica a páginas https
        audits = lh.get("audits") or {}
        items = audits.get("network-requests", {}).get("details", {}).get("items", [])
        for item in items:
            url = item.get("url", "")
            if url.startswith("http://") and "localhost" not in url:
                http_recursos.append(url)
    if http_recursos:
        return "fail", {"mixed_content": http_recursos[:10], "total": len(http_recursos)}
    return "pass", {}


async def check_mobile_friendly(payloads: list[dict]) -> tuple[str, dict]:
    """Sem rede — audit viewport dos payloads mobile: todo score==1 → pass; algum 0 → fail."""
    scores: list[float] = []
    for payload in payloads:
        lh = payload.get("lighthouseResult") or {}
        config = lh.get("configSettings") or {}
        if config.get("formFactor") != "mobile":
            continue
        audits = lh.get("audits") or {}
        viewport = audits.get("viewport")
        if viewport is None or viewport.get("score") is None:
            continue
        scores.append(float(viewport["score"]))
    if not scores:
        return "na", {}
    if all(s == 1 for s in scores):
        return "pass", {"scores": scores}
    return "fail", {"scores": scores}


_LLMS_TXT_MAX_BYTES = 256 * 1024  # parse até 256KB do corpo


async def check_llms_txt(origem: str) -> tuple[str, dict]:
    """GET ``{origem}/llms.txt`` (SPEC_CWV_Navegacao_Agentica).

    200 textual com H1 Markdown (``^# `` em alguma linha) → ``pass``;
    200 sem H1 (ou não-textual) → ``fail``; 404/erro de rede → ``fail``
    (arquivo ausente — recomendado criar); 401/403/429 (WAF) → ``na``.
    Timeout vira ``erro`` no ``_com_timeout``.
    """
    url = f"{origem}/llms.txt"
    try:
        resp = await _get_client().get(url)
        if resp.status_code in _STATUS_BLOQUEIO:
            return "na", {"status_code": resp.status_code, "motivo": "bloqueio WAF/anti-bot — inconclusivo"}
        if resp.status_code != 200:
            return "fail", {"status_code": resp.status_code, "motivo": "arquivo ausente — recomendado criar"}
        ctype = resp.headers.get("content-type", "").lower()
        if "text" not in ctype and "markdown" not in ctype:
            return "fail", {"status_code": 200, "content_type": ctype, "motivo": "Content-Type não textual"}
        corpo = resp.text[:_LLMS_TXT_MAX_BYTES]
        tem_h1 = any(linha.startswith("# ") for linha in corpo.splitlines())
        if tem_h1:
            return "pass", {"status_code": 200}
        return "fail", {"status_code": 200, "motivo": "sem cabeçalho H1 obrigatório"}
    except Exception as e:
        logger.debug("check_llms_txt falhou para %s: %s", url, e)
        return "fail", {"erro": str(e)[:200], "motivo": "arquivo ausente — recomendado criar"}


async def _com_timeout(coro, nome: str) -> tuple[str, dict]:
    """Envolve um check em wait_for + try/except → 'erro' (fail-open)."""
    try:
        return await asyncio.wait_for(coro, timeout=_TIMEOUT_POR_CHECK)
    except TimeoutError:
        logger.warning("page_experience check %s excedeu timeout", nome)
        return "erro", {"erro": "timeout"}
    except Exception as e:
        logger.warning("page_experience check %s falhou: %s", nome, e)
        return "erro", {"erro": str(e)[:200]}


async def auditar_origem(origem: str, payloads: list[dict]) -> dict:
    """Roda os 7 checks para uma origem. Cada check fail-open → 'erro'.

    ``payloads`` são os payloads PSI brutos (com lighthouseResult) das análises
    de sucesso daquela origem — usados pelos checks sem rede (mixed content,
    mobile friendly).
    """
    host = _host(origem)
    https, ssl_v, redirect, headers, safe, mixed, mobile, llms = await asyncio.gather(
        _com_timeout(check_https(origem), "https"),
        _com_timeout(check_ssl(host), "ssl"),
        _com_timeout(check_redirect_301(origem), "redirect_301"),
        _com_timeout(check_security_headers(origem), "security_headers"),
        _com_timeout(check_safe_browsing(origem), "safe_browsing"),
        _com_timeout(check_mixed_content(payloads), "mixed_content"),
        _com_timeout(check_mobile_friendly(payloads), "mobile_friendly"),
        _com_timeout(check_llms_txt(origem), "llms_txt"),
    )
    return {
        "https": https[0],
        "ssl": ssl_v[0],
        "redirect_301": redirect[0],
        "security_headers": headers[0],
        "safe_browsing": safe[0],
        "mixed_content": mixed[0],
        "mobile_friendly": mobile[0],
        "llms_txt": llms[0],
        "detalhes": {
            "https": https[1],
            "ssl": ssl_v[1],
            "redirect_301": redirect[1],
            "security_headers": headers[1],
            "safe_browsing": safe[1],
            "mixed_content": mixed[1],
            "mobile_friendly": mobile[1],
            "llms_txt": llms[1],
        },
    }
