import asyncio
import hashlib
import html as html_lib
import ipaddress
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from app.core.cache import cache_get_json, cache_get_str, cache_set_json, cache_set_str

logger = logging.getLogger(__name__)

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_USER_AGENT = "SeoSaaSBot/1.0 (+https://seo-saas.app/bot)"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_TIMEOUT = 20.0
_MAX_REDIRECTS = 5

_PER_HOST_CONCURRENCY = 2
_GLOBAL_SCRAPE_CONCURRENCY = 10

_SCRAPE_CACHE_TTL = 7 * 24 * 3600  # 7 dias
_ROBOTS_CACHE_TTL = 24 * 3600  # 24 horas

_host_semaphores: dict[str, asyncio.Semaphore] = {}
_host_locks_lock = asyncio.Lock()
_global_semaphore = asyncio.Semaphore(_GLOBAL_SCRAPE_CONCURRENCY)


@dataclass
class ScrapeResult:
    url: str
    url_canonica: str = ""
    html_hash: str = ""
    conteudo_md: str = ""
    titulo: str = ""
    tokens: int = 0
    falhou: bool = False
    erro: str = ""
    cache_hit: bool = False


async def _get_host_semaphore(host: str) -> asyncio.Semaphore:
    if host in _host_semaphores:
        return _host_semaphores[host]
    async with _host_locks_lock:
        if host not in _host_semaphores:
            _host_semaphores[host] = asyncio.Semaphore(_PER_HOST_CONCURRENCY)
        return _host_semaphores[host]


def _check_host(hostname: str) -> str:
    import socket

    if not hostname:
        return "dns_fail"
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return "dns_fail"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                return "blocked"
    return "ok"


def _is_private_host(hostname: str) -> bool:
    return _check_host(hostname) != "ok"


def _normalizar_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return ""
    host = parsed.hostname.lower() if parsed.hostname else ""
    if not host:
        return ""
    port = ""
    if parsed.port and not (
        (scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)
    ):
        port = f":{parsed.port}"
    path = parsed.path.rstrip("/") or "/"
    return f"{scheme}://{host}{port}{path}"


async def _robots_permitido(url_canonica: str) -> bool:
    parsed = urlparse(url_canonica)
    host = parsed.hostname or ""
    if not host:
        return False

    cache_key = f"robots:{parsed.scheme}://{host}"
    cached = await cache_get_str(cache_key)
    robots_txt: str | None = None
    if cached is not None:
        robots_txt = "" if cached == "__EMPTY__" else cached

    if robots_txt is None:
        robots_url = f"{parsed.scheme}://{host}/robots.txt"
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
                verify=True,
            ) as client:
                resp = await client.get(robots_url)
                robots_txt = resp.text[:_MAX_RESPONSE_BYTES] if resp.status_code == 200 and resp.text else ""
        except Exception as e:
            logger.debug("Falha ao buscar robots.txt em %s: %s", robots_url, e)
            robots_txt = ""
        await cache_set_str(cache_key, robots_txt or "__EMPTY__", _ROBOTS_CACHE_TTL)

    if not robots_txt:
        return True

    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    try:
        return parser.can_fetch(_USER_AGENT, url_canonica)
    except Exception:
        return True


async def scrape_url(url: str) -> ScrapeResult:
    resultado = ScrapeResult(url=url)

    normalizada = _normalizar_url(url)
    if not normalizada:
        resultado.falhou = True
        resultado.erro = "URL invalida"
        return resultado

    parsed = urlparse(normalizada)
    host_status = _check_host(parsed.hostname)
    if host_status == "dns_fail":
        resultado.falhou = True
        resultado.erro = "Dominio nao encontrado (DNS falhou). Verifique se a URL esta correta."
        return resultado
    if host_status == "blocked":
        resultado.falhou = True
        resultado.erro = "Host bloqueado (IP privado ou loopback)"
        return resultado

    resultado.url_canonica = normalizada

    cache_key = f"scrape:v2:{normalizada}"
    cached = await cache_get_json(cache_key)
    if cached and isinstance(cached, dict) and cached.get("conteudo_md"):
        resultado.html_hash = cached.get("html_hash", "")
        resultado.conteudo_md = cached.get("conteudo_md", "")
        resultado.titulo = cached.get("titulo", "")
        resultado.tokens = cached.get("tokens", 0)
        resultado.cache_hit = True
        logger.info("scrape cache hit: %s", normalizada)
        return resultado

    permitido = await _robots_permitido(normalizada)
    if not permitido:
        resultado.falhou = True
        resultado.erro = "Bloqueado por robots.txt"
        return resultado

    host = parsed.hostname or ""
    host_sem = await _get_host_semaphore(host)

    async with _global_semaphore, host_sem:
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT,
                follow_redirects=True,
                max_redirects=_MAX_REDIRECTS,
                headers={"User-Agent": _USER_AGENT},
                verify=True,
            ) as client:
                response = await client.get(normalizada)

                if response.status_code in (429, 503):
                    retry_after = response.headers.get("Retry-After")
                    espera = 5.0
                    if retry_after:
                        try:
                            espera = min(float(retry_after), 30.0)
                        except ValueError:
                            espera = 5.0
                    logger.info("rate-limited %s, aguardando %.1fs", host, espera)
                    await asyncio.sleep(espera)
                    response = await client.get(normalizada)

                response.raise_for_status()

                total_bytes = 0
                chunks = []
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total_bytes += len(chunk)
                    if total_bytes > _MAX_RESPONSE_BYTES:
                        resultado.falhou = True
                        resultado.erro = "Resposta excede 5MB"
                        return resultado
                    chunks.append(chunk)

                html = b"".join(chunks).decode("utf-8", errors="replace")

        except httpx.HTTPError as e:
            resultado.falhou = True
            resultado.erro = f"Erro HTTP: {e}"
            return resultado

    resultado.html_hash = hashlib.sha256(html.encode()).hexdigest()

    conteudo = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=False,
        include_images=False,
        favor_precision=True,
    )

    if not conteudo or len(conteudo.strip()) < 50:
        resultado.falhou = True
        resultado.erro = "Conteudo extraido vazio ou insuficiente"
        return resultado

    metadata = trafilatura.extract(html, output_format="json", include_links=False, include_images=False)
    titulo = ""
    if metadata:
        try:
            import json

            meta = json.loads(metadata)
            titulo = (meta.get("title") or "").strip()
        except Exception:
            pass

    if not titulo:
        titulo = _extrair_titulo_html(html)

    resultado.conteudo_md = conteudo.strip()
    resultado.titulo = titulo or (parsed.hostname or "")
    resultado.tokens = _estimate_tokens(conteudo)

    await cache_set_json(
        cache_key,
        {
            "html_hash": resultado.html_hash,
            "conteudo_md": resultado.conteudo_md,
            "titulo": resultado.titulo,
            "tokens": resultado.tokens,
        },
        _SCRAPE_CACHE_TTL,
    )

    return resultado


_TITULO_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TITULO_OG_REV_RE = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
    re.IGNORECASE,
)
_TITULO_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


def _extrair_titulo_html(html: str) -> str:
    candidatos: list[str] = []
    for m in _TITULO_OG_RE.finditer(html):
        candidatos.append(m.group(1))
        break
    if not candidatos:
        for m in _TITULO_OG_REV_RE.finditer(html):
            candidatos.append(m.group(1))
            break
    m = _TITULO_TAG_RE.search(html)
    if m:
        candidatos.append(m.group(1))
    m = _H1_RE.search(html)
    if m:
        candidatos.append(_STRIP_TAGS_RE.sub("", m.group(1)))

    for bruto in candidatos:
        limpo = html_lib.unescape(bruto).strip()
        limpo = re.sub(r"\s+", " ", limpo)
        # en-dash e em-dash sao proposital: separadores tipograficos comuns em titulos
        limpo = re.sub(r"\s+[\|\-–—]\s+[^|\-–—]{1,60}$", "", limpo).strip()  # noqa: RUF001
        if 3 <= len(limpo) <= 200:
            return limpo
    return ""


def _estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)
