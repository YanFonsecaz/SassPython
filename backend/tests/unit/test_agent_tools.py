import json

import httpx
import pytest
import respx

from app.core.agent_tools import (
    _ctx7_cache_get,
    _ctx7_cache_set,
    buscar_docs_lib,
    buscar_web,
    fetch_url,
)


@respx.mock
@pytest.mark.asyncio
async def test_buscar_web_sem_api_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "serpapi_key", "")
    result = await buscar_web.ainvoke({"query": "test"})
    assert "ERRO" in result


@respx.mock
@pytest.mark.asyncio
async def test_buscar_web_retorna_resultados(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "serpapi_key", "fake-key")

    mock_resp = {
        "organic_results": [
            {"title": "Result 1", "link": "https://example.com/1", "snippet": "Snippet 1"},
            {"title": "Result 2", "link": "https://example.com/2", "snippet": "Snippet 2"},
        ]
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, json=mock_resp)
    )

    result = await buscar_web.ainvoke({"query": "lighthouse render-blocking", "num": 2})
    assert "Result 1" in result
    assert "https://example.com/1" in result


@respx.mock
@pytest.mark.asyncio
async def test_buscar_web_http_error(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "serpapi_key", "fake-key")

    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(500)
    )

    result = await buscar_web.ainvoke({"query": "test"})
    assert "ERRO" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_url_url_invalida():
    result = await fetch_url.ainvoke({"url": "ftp://invalid", "max_chars": 2000})
    assert "ERRO" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_url_http_error():
    respx.get("https://example.com/broken").mock(
        return_value=httpx.Response(404)
    )

    result = await fetch_url.ainvoke({"url": "https://example.com/broken"})
    assert "ERRO" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_url_content_type_invalido():
    respx.get("https://example.com/pdf").mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4",
            headers={"content-type": "application/pdf"},
        )
    )

    result = await fetch_url.ainvoke({"url": "https://example.com/pdf"})
    assert "ERRO" in result
    assert "content-type" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_url_html_para_markdown():
    html = """<html><head><title>Test Page</title></head><body>
    <h1>Heading</h1>
    <p>Paragraph with <strong>bold</strong> text.</p>
    <p>Another paragraph.</p>
    </body></html>"""

    respx.get("https://example.com/page").mock(
        return_value=httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html"},
        )
    )

    result = await fetch_url.ainvoke({"url": "https://example.com/page", "max_chars": 2000})
    assert "Heading" in result or "Test Page" in result


@respx.mock
@pytest.mark.asyncio
async def test_fetch_url_truncacao():
    long_html = "<html><head><title>Long</title></head><body>"
    for i in range(200):
        long_html += f"<p>Paragraph {i} with enough text to make it long and detailed.</p>"
    long_html += "</body></html>"

    respx.get("https://example.com/long").mock(
        return_value=httpx.Response(
            200,
            text=long_html,
            headers={"content-type": "text/html"},
        )
    )

    result = await fetch_url.ainvoke({"url": "https://example.com/long", "max_chars": 500})
    assert "truncado" in result


@respx.mock
@pytest.mark.asyncio
async def test_buscar_docs_lib_sem_api_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_context7_key", "")
    result = await buscar_docs_lib.ainvoke({"biblioteca": "nextjs", "pergunta": "images"})
    assert "ERRO" in result


@respx.mock
@pytest.mark.asyncio
async def test_buscar_docs_lib_busca_com_sucesso(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_context7_key", "fake-ctx7-key")

    search_resp = {"results": [{"id": "/vercel/next.js"}]}
    respx.get("https://context7.com/api/v1/search").mock(
        return_value=httpx.Response(200, json=search_resp)
    )

    respx.get("https://context7.com/api/v1/vercel/next.js").mock(
        return_value=httpx.Response(200, text="# next/image\nUse priority prop for LCP images.")
    )

    result = await buscar_docs_lib.ainvoke({
        "biblioteca": "nextjs",
        "pergunta": "next/image priority",
        "tokens": 2000,
    })
    assert "next/image" in result or "priority" in result


@respx.mock
@pytest.mark.asyncio
async def test_buscar_docs_lib_biblioteca_nao_encontrada(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_context7_key", "fake-ctx7-key")

    respx.get("https://context7.com/api/v1/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    result = await buscar_docs_lib.ainvoke({
        "biblioteca": "nonexistent-lib-xyz",
        "pergunta": "test",
    })
    assert "nao encontrada" in result


@respx.mock
@pytest.mark.asyncio
async def test_buscar_docs_lib_search_http_error(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_context7_key", "fake-ctx7-key")

    respx.get("https://context7.com/api/v1/search").mock(
        return_value=httpx.Response(500)
    )

    result = await buscar_docs_lib.ainvoke({
        "biblioteca": "nextjs",
        "pergunta": "images",
    })
    assert "ERRO" in result


def test_tools_have_names():
    assert buscar_web.name == "buscar_web"
    assert fetch_url.name == "fetch_url"
    assert buscar_docs_lib.name == "buscar_docs_lib"


def test_tools_have_descriptions():
    assert len(buscar_web.description) > 50
    assert len(fetch_url.description) > 50
    assert len(buscar_docs_lib.description) > 50
