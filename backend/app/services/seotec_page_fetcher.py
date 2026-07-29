"""Fetcher de páginas para avaliação automática de itens manuais SEOTec.

Baixa páginas chave do domício (homepage, blog, produto/sample) via HTTP e
cacheia o HTML bruto para os avaliadores de itens que não vêm do SF.

Estratégia: descobre URLs representativas do export `internal` (home, página
mais profunda, amostra de blog/produto). Fall-open: se fetch falhar, o item
permanece `manual` (sem dados → "Sem dados", nunca "Reprovado").
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
_HEADS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOTecAuditor/1.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
_MAX_PAGES = 8


@dataclass
class PaginaBaixada:
    url: str
    status_code: int
    html: str
    erro: str | None = None


@dataclass
class PaginasSite:
    """Coleção de páginas baixadas do site auditado."""
    dominio: str
    paginas: dict[str, PaginaBaixada] = field(default_factory=dict)

    @property
    def homepage(self) -> PaginaBaixada | None:
        return self.paginas.get("homepage")

    @property
    def blog(self) -> PaginaBaixada | None:
        return self.paginas.get("blog")

    @property
    def produto(self) -> PaginaBaixada | None:
        return self.paginas.get("produto")

    @property
    def amostra(self) -> list[PaginaBaixada]:
        """Todas as páginas baixadas exceto homepage/blog/produto nomeados."""
        return [p for k, p in self.paginas.items() if k.startswith("amostra_")]


def _descobrir_urls_chave(dominio: str, urls_internas: list[dict]) -> dict[str, str]:
    """Descobre URLs representativas do export `internal` do SF."""
    resultado: dict[str, str] = {"homepage": dominio.rstrip("/")}

    blog_urls = []
    produto_urls = []
    outras = []

    for linha in urls_internas:
        url = str(linha.get("address") or "")
        if not url:
            continue
        url_lower = url.lower()

        # Detectar blog
        if any(seg in url_lower for seg in ["/blog/", "/blog.", "/noticias/", "/artigos/", "/news/"]):
            if len(blog_urls) < 2:
                blog_urls.append(url)
        # Detectar produto (e-commerce)
        elif any(seg in url_lower for seg in ["/produto", "/product", "/p/", "/checkout", "/carrinho"]):
            if len(produto_urls) < 2:
                produto_urls.append(url)
        # Páginas profundas (crawl_depth > 1)
        elif linha.get("crawl_depth", 0) and int(linha.get("crawl_depth", 0)) > 1 and len(outras) < 3:
                outras.append(url)

    if blog_urls:
        resultado["blog"] = blog_urls[0]
    if produto_urls:
        resultado["produto"] = produto_urls[0]
    for i, url in enumerate(outras[:3]):
        resultado[f"amostra_{i}"] = url

    return resultado


async def baixar_paginas_chave(
    dominio: str,
    urls_internas: list[dict],
) -> PaginasSite:
    """Baixa páginas chave do site para avaliação de itens manuais.

    Fail-open: se todas as requisições falharem, retorna PaginasSite vazio.
    """
    urls = _descobrir_urls_chave(dominio, urls_internas)
    if len(urls) > _MAX_PAGES:
        chaves = list(urls.keys())[:_MAX_PAGES]
        urls = {k: urls[k] for k in chaves}

    site = PaginasSite(dominio=dominio)

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[client.get(url, headers=_HEADS) for url in urls.values()],
            return_exceptions=True,
        )

    for (nome, url), result in zip(urls.items(), results, strict=False):
        if isinstance(result, Exception):
            logger.warning("fetch_erro %s: %s", nome, result)
            site.paginas[nome] = PaginaBaixada(
                url=url, status_code=0, html="", erro=str(result),
            )
        else:
            site.paginas[nome] = PaginaBaixada(
                url=url,
                status_code=result.status_code,
                html=result.text if result.status_code == 200 else "",
            )

    logger.info(
        "paginas_baixadas dominio=%s total=%d ok=%d",
        dominio, len(site.paginas),
        sum(1 for p in site.paginas.values() if p.status_code == 200),
    )
    return site
