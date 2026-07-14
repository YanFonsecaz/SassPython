"""Descoberta de URLs via sitemap.xml (SPEC_Inlinks_Descoberta_Automatica_Candidatas).

Suporta sitemap-index (<sitemapindex>) e urlset (<urlset>). Respeita o SSRF guard
do scraper (_check_host) e deduplica. v1 = só sitemap, sem crawl de links.
"""
import logging
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from app.core.scraper import _USER_AGENT, _check_host

logger = logging.getLogger(__name__)

_SITEMAP_TIMEOUT = 20.0
_MAX_BYTES = 2 * 1024 * 1024
# Profundidade de recursão para sitemap-index aninhados (raro, mas existe).
_MAX_INDEX_DEPTH = 3


def _norm_host(host: str) -> str:
    """Trata www.dominio e dominio como equivalentes (sitemaps misturam os dois)."""
    return host.lower().removeprefix("www.")


def _mesmo_dominio(url: str, dominio: str) -> bool:
    host = urlparse(url).hostname or ""
    return _norm_host(host) == _norm_host(dominio)


async def _fetch(url: str) -> str | None:
    """Baixa o conteúdo do sitemap. Retorna None se vazio/erro."""
    try:
        async with httpx.AsyncClient(
            timeout=_SITEMAP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            verify=True,
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            return resp.text[:_MAX_BYTES]
    except Exception as e:
        logger.warning("fetch sitemap %s falhou: %s", url, e)
        return None


def _parse(texto: str) -> tuple[list[str], list[str]]:
    """Extrai (urls, sub_sitemaps) de um documento sitemap.

    Detecta sitemap-index (<sitemapindex><sitemap><loc>) vs urlset (<urlset><url><loc>).
    Robusto a namespaces (o ElementTree expande {namespace}tag).
    """
    urls: list[str] = []
    sub_sitemaps: list[str] = []
    try:
        root = ET.fromstring(texto)
    except ET.ParseError as e:
        logger.warning("sitemap XML inválido: %s", e)
        return [], []

    tag_local = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if tag_local == "sitemapindex":
        for sitemap in root.iter():
            if sitemap.tag.split("}")[-1] != "sitemap":
                continue
            for child in sitemap:
                if child.tag.split("}")[-1] == "loc" and child.text:
                    sub_sitemaps.append(child.text.strip())
    else:
        # urlset (ou qualquer coisa com <url><loc>)
        for url_el in root.iter():
            if url_el.tag.split("}")[-1] != "url":
                continue
            for child in url_el:
                if child.tag.split("}")[-1] == "loc" and child.text:
                    urls.append(child.text.strip())
    return urls, sub_sitemaps


async def _sitemaps_do_robots(dominio: str) -> list[str]:
    """Descobre sitemaps pela diretiva `Sitemap:` do robots.txt (mecanismo padrão).

    É o que o Google usa; cobre sites cujo sitemap não está em /sitemap.xml
    (ex.: /wp-sitemap.xml do WordPress). A diretiva pode aparecer várias vezes.
    """
    texto = await _fetch(f"https://{dominio}/robots.txt")
    if not texto:
        return []
    encontrados: list[str] = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha.lower().startswith("sitemap:"):
            u = linha.split(":", 1)[1].strip()
            if u.startswith(("http://", "https://")) and u not in encontrados:
                encontrados.append(u)
    return encontrados[:10]


def _profundidade_path(url: str) -> int:
    """Heurística de prioridade: páginas rasas (poucos segmentos de path) primeiro."""
    path = urlparse(url).path or "/"
    return len([p for p in path.split("/") if p])


async def coletar_urls_do_sitemap(
    dominio: str,
    *,
    teto: int = 500,
    sitemap_url: str | None = None,
) -> list[str]:
    """Baixa o sitemap do domínio e devolve até `teto` URLs do mesmo domínio.

    Ordem de descoberta: `sitemap_url` explícito (override do usuário) →
    diretivas `Sitemap:` do robots.txt → chutes /sitemap.xml e
    /sitemap_index.xml. Sitemap-index é recursivo (até _MAX_INDEX_DEPTH).
    URLs de outro domínio (cross-domain no sitemap) são descartadas
    (www./não-www são equivalentes). Ordena por profundidade de path.
    """
    if _check_host(dominio) != "ok":
        logger.info("sitemap: host %s bloqueado pelo SSRF guard", dominio)
        return []

    candidatos: list[str] = []
    visitados: set[str] = set()

    async def _explorar(sitemap_url: str, depth: int) -> None:
        if depth > _MAX_INDEX_DEPTH or sitemap_url in visitados:
            return
        visitados.add(sitemap_url)
        # SSRF guard também nos sub-sitemaps: um sitemap-index pode listar
        # <loc> apontando para host privado/interno — bloquear antes do fetch.
        host_sub = urlparse(sitemap_url).hostname or ""
        if _check_host(host_sub) != "ok":
            logger.info("sitemap: sub-sitemap %s bloqueado pelo SSRF guard", sitemap_url)
            return
        texto = await _fetch(sitemap_url)
        if not texto:
            return
        urls, subs = _parse(texto)
        for u in urls:
            if _mesmo_dominio(u, dominio) and u not in candidatos:
                candidatos.append(u)
        if len(candidatos) >= teto:
            return
        for sub in subs:
            if len(candidatos) >= teto:
                return
            await _explorar(sub, depth + 1)

    if sitemap_url:
        fontes = [sitemap_url]
    else:
        fontes = await _sitemaps_do_robots(dominio)
        fontes += [f"https://{dominio}/sitemap.xml", f"https://{dominio}/sitemap_index.xml"]

    for fonte in fontes:
        if len(candidatos) >= teto:
            break
        await _explorar(fonte, depth=0)

    # Prioriza páginas rasas; corta no teto.
    candidatos.sort(key=_profundidade_path)
    return candidatos[:teto]
