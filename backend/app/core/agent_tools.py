"""Tools reutilizáveis para agentes LLM com LangChain tool-calling."""

import asyncio
import hashlib
import logging
from typing import Annotated

import httpx
from langchain_core.tools import tool

from app.config import settings

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15.0
_MAX_CONCURRENT_FETCHES = 3
_fetch_sem = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

_CTX7_BASE = "https://context7.com/api/v1"
_CTX7_TIMEOUT = 15.0
_CTX7_CACHE_TTL = 86400


@tool
async def buscar_web(
    query: Annotated[str, "Termo de busca em ingles ou portugues, especifico"],
    num: Annotated[int, "Numero de resultados (1-10)"] = 5,
) -> str:
    """Busca na web via SerpAPI. Retorna lista de URLs + snippets em formato Markdown.

    Use para encontrar documentacao oficial, posts de blog tecnico, ou web.dev.
    Prefira queries em INGLES para temas tecnicos (mais resultados de qualidade).
    """
    if not settings.serpapi_key:
        return "ERRO: SerpAPI nao configurada."
    num = max(1, min(10, num))
    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "api_key": settings.serpapi_key,
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get("https://serpapi.com/search", params=params)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("buscar_web falhou: %s", e)
        return f"ERRO: busca falhou ({type(e).__name__})"

    organicos = data.get("organic_results", [])[:num]
    if not organicos:
        return f"Nenhum resultado para: {query}"

    linhas = [f"# Resultados para: {query}\n"]
    for i, item in enumerate(organicos, 1):
        titulo = item.get("title", "")
        url = item.get("link", "")
        snippet = item.get("snippet", "")[:200]
        linhas.append(f"{i}. **{titulo}**\n   {url}\n   {snippet}\n")
    return "\n".join(linhas)


@tool
async def fetch_url(
    url: Annotated[str, "URL completa (https://...) a buscar"],
    max_chars: Annotated[int, "Limite de caracteres da resposta (1000-15000)"] = 8000,
) -> str:
    """Busca o conteudo de uma URL e retorna o texto extraido em Markdown.

    Use APOS `buscar_web` para ler em detalhe uma URL relevante.
    Limita resposta a max_chars (default 8000) para nao estourar contexto.
    HTML e simplificado para texto.
    """
    if not url.startswith(("http://", "https://")):
        return "ERRO: URL invalida (precisa http/https)"
    max_chars = max(1000, min(15000, max_chars))

    async with _fetch_sem:
        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "SEO-SaaS-CWV-Analyzer/1.0"},
            ) as client:
                r = await client.get(url)
                r.raise_for_status()
                content_type = r.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    return f"ERRO: content-type nao suportado ({content_type})"
                html = r.text
        except httpx.HTTPError as e:
            logger.warning("fetch_url falhou para %s: %s", url, e)
            return f"ERRO: fetch falhou ({type(e).__name__})"

    from readability import Document
    from markdownify import markdownify

    try:
        doc = Document(html)
        title = doc.short_title()
        content_html = doc.summary()
        md = markdownify(content_html, heading_style="ATX").strip()
    except Exception as e:
        logger.warning("Extracao de readability falhou: %s", e)
        md = html
    if len(md) > max_chars:
        md = md[:max_chars] + f"\n\n[...truncado em {max_chars} chars]"
    return f"# {title}\n\n{md}"


async def _ctx7_cache_get(key: str) -> str | None:
    try:
        from app.core.redis_pool import get_redis_commands

        redis = await get_redis_commands()
        val = await redis.get(f"ctx7:{key}")
        return val if val else None
    except Exception:
        return None


async def _ctx7_cache_set(key: str, value: str, ttl: int = _CTX7_CACHE_TTL):
    try:
        from app.core.redis_pool import get_redis_commands

        redis = await get_redis_commands()
        await redis.set(f"ctx7:{key}", value, ex=ttl)
    except Exception as e:
        logger.warning("ctx7 cache set falhou: %s", e)


@tool
async def buscar_docs_lib(
    biblioteca: Annotated[str, "Nome da lib/framework (ex: 'nextjs', 'shopify hydrogen', 'tailwind')"],
    pergunta: Annotated[str, "O que voce quer saber (ex: 'lazy load images', 'preload font')"],
    tokens: Annotated[int, "Tamanho aproximado da doc retornada (500-5000)"] = 2000,
) -> str:
    """Busca documentacao oficial atualizada de uma biblioteca/framework via Context7.

    Use APENAS quando o audit envolve uma lib/framework especifico (Next.js, Shopify,
    Tailwind, React, etc.). Para audits genericos de Lighthouse use `buscar_web`.

    Retorna trechos da doc oficial em texto.
    """
    if not settings.api_context7_key:
        return "ERRO: Context7 nao configurado."
    tokens = max(500, min(5000, tokens))

    cache_key = hashlib.sha256(f"{biblioteca}|{pergunta}|{tokens}".encode()).hexdigest()[:16]
    cached = await _ctx7_cache_get(cache_key)
    if cached:
        logger.info("ctx7_query lib=%s topic=%s hit=cache", biblioteca, pergunta)
        return cached

    headers = {"Authorization": f"Bearer {settings.api_context7_key}"}

    try:
        async with httpx.AsyncClient(timeout=_CTX7_TIMEOUT, headers=headers) as client:
            r = await client.get(f"{_CTX7_BASE}/search", params={"query": biblioteca})
            r.raise_for_status()
            search = r.json()
    except httpx.HTTPError as e:
        return f"ERRO ao resolver biblioteca: {type(e).__name__}"

    results = search.get("results") or []
    if not results:
        return f"Biblioteca '{biblioteca}' nao encontrada no Context7."

    library_id = results[0].get("id")
    if not library_id:
        return "ERRO: resposta sem library_id."

    try:
        async with httpx.AsyncClient(timeout=_CTX7_TIMEOUT, headers=headers) as client:
            r = await client.get(
                f"{_CTX7_BASE}{library_id}",
                params={"type": "txt", "tokens": tokens, "topic": pergunta},
            )
            r.raise_for_status()
            docs = r.text
    except httpx.HTTPError as e:
        return f"ERRO ao buscar docs ({library_id}): {type(e).__name__}"

    if len(docs) > tokens * 8:
        docs = docs[:tokens * 8] + "\n\n[...truncado]"

    result = f"# Docs: {biblioteca} — {pergunta}\n\n{docs}"
    logger.info("ctx7_query lib=%s topic=%s hit=live", biblioteca, pergunta)

    await _ctx7_cache_set(cache_key, result)
    return result
