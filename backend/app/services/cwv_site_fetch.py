"""Fetch leve do conteúdo do site do cliente para a geração agêntica.

SPEC_CWV_Navegacao_Agentica_Geracao_IA §3.1. Busca homepage + llms.txt +
sitemap (top 30 URLs) e devolve um resumo compacto (~1-2KB) para o prompt —
NUNCA o HTML inteiro. Fail-open: qualquer erro de rede vira campo vazio, nunca
levanta. **Anti-SSRF:** só acessa as URLs recebidas (do próprio cliente da
auditoria) e caminhos same-origin (``/llms.txt``, ``/sitemap.xml``); jamais uma
URL vinda do request.
"""
from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_TIMEOUT = 10
_MAX_HTML_BYTES = 512 * 1024  # parse até 512KB do HTML
_MAX_LLMS_BYTES = 32 * 1024
_MAX_SITEMAP_URLS = 30

_CLIENT: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA},
        )
    return _CLIENT


class _SiteParser(HTMLParser):
    """Extrai title, meta description, H1/H2 e textos de links de navegação."""

    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.meta_description: str | None = None
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.nav_links: list[str] = []
        self._capture: str | None = None
        self._buf: list[str] = []
        self._in_nav = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._capture, self._buf = "title", []
        elif tag == "meta" and d.get("name", "").lower() == "description":
            if self.meta_description is None:
                self.meta_description = d.get("content", "").strip()[:300]
        elif tag in ("h1", "h2"):
            self._capture, self._buf = tag, []
        elif tag == "nav":
            self._in_nav = True
        elif tag == "a" and self._in_nav:
            self._capture, self._buf = "a", []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._capture == "title":
            self.title = "".join(self._buf).strip()[:200]
            self._capture = None
        elif tag in ("h1", "h2") and self._capture == tag:
            txt = " ".join("".join(self._buf).split())
            if txt:
                (self.h1 if tag == "h1" else self.h2).append(txt[:150])
            self._capture = None
        elif tag == "a" and self._capture == "a":
            txt = " ".join("".join(self._buf).split())
            if txt:
                self.nav_links.append(txt[:80])
            self._capture = None
        elif tag == "nav":
            self._in_nav = False

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)


def _extrair_locs(xml: str) -> list[str]:
    """URLs de um sitemap.xml (tags ``<loc>``), sem parser XML pesado."""
    return [m.strip() for m in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.IGNORECASE)]


# Sinais heurísticos de WebMCP no HTML servido. "Não detectado" = "não achado
# no HTML estático", NUNCA prova de ausência (registro é runtime via JS).
_WEBMCP_SINAIS = (
    "navigator.modelcontext",
    "registertool",
    "window.agent",
    "<tool",
    "webmcp",
    "mcp-manifest",
)


def detectar_sinais_webmcp(html: str) -> dict:
    """Heurística sobre HTML estático — retorna {sinal: bool} + agregado."""
    low = html.lower()
    sinais = {s: (s in low) for s in _WEBMCP_SINAIS}
    return {"sinais": sinais, "detectado": any(sinais.values())}


async def coletar_conteudo_site(urls: list[str]) -> dict:
    """Resumo compacto do site do cliente para o prompt agêntico. Fail-open.

    ``urls`` são as URLs canônicas auditadas (do cliente dono) — a homepage é a
    primeira; ``/llms.txt`` e ``/sitemap.xml`` derivam da mesma origem.
    """
    resumo: dict = {
        "origem": None,
        "homepage_url": None,
        "title": None,
        "meta_description": None,
        "h1": [],
        "h2": [],
        "nav_links": [],
        "llms_txt_atual": None,
        "sitemap_urls": [],
        "urls_auditadas": [u for u in urls[:10]],
        "webmcp": {"sinais": {}, "detectado": False},
    }
    if not urls:
        return resumo

    homepage = urls[0]
    p = urlsplit(homepage)
    origem = f"{p.scheme}://{p.netloc}"
    resumo["origem"] = origem
    resumo["homepage_url"] = homepage
    client = _get_client()

    # Homepage HTML → title/meta/headings/nav.
    try:
        r = await client.get(homepage)
        if r.status_code == 200:
            html = r.text[:_MAX_HTML_BYTES]
            parser = _SiteParser()
            parser.feed(html)
            resumo["title"] = parser.title
            resumo["meta_description"] = parser.meta_description
            resumo["h1"] = parser.h1[:5]
            resumo["h2"] = parser.h2[:15]
            resumo["nav_links"] = parser.nav_links[:30]
            resumo["webmcp"] = detectar_sinais_webmcp(html)
    except Exception as e:
        logger.debug("coletar_conteudo_site: homepage falhou (%s): %s", homepage, e)

    # llms.txt atual (se houver).
    try:
        r = await client.get(f"{origem}/llms.txt")
        ctype = r.headers.get("content-type", "").lower()
        if r.status_code == 200 and ("text" in ctype or "markdown" in ctype):
            resumo["llms_txt_atual"] = r.text[:_MAX_LLMS_BYTES]
    except Exception as e:
        logger.debug("coletar_conteudo_site: llms.txt falhou (%s): %s", origem, e)

    # Sitemap → top N URLs.
    try:
        r = await client.get(f"{origem}/sitemap.xml")
        if r.status_code == 200:
            resumo["sitemap_urls"] = _extrair_locs(r.text)[:_MAX_SITEMAP_URLS]
    except Exception as e:
        logger.debug("coletar_conteudo_site: sitemap falhou (%s): %s", origem, e)

    return resumo
