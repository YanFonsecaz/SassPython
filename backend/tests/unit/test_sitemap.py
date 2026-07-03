"""SPEC_Inlinks_Descoberta_Automatica_Candidatas — testes do parser de sitemap.

Cobre: sitemap-index + urlset, dedup, malformado, filtro de mesmo domínio,
teto de páginas, e bloqueio de host privado pelo SSRF guard.
"""

import pytest

from app.core import sitemap as sm

_URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://exemplo.com.br/</loc></url>
  <url><loc>https://exemplo.com.br/blog/post-1</loc></url>
  <url><loc>https://exemplo.com.br/blog/post-2</loc></url>
  <url><loc>https://outro-dominio.com/x</loc></url>
</urlset>
"""

_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://exemplo.com.br/sitemap-posts.xml</loc></sitemap>
</sitemapindex>
"""


def test_parse_urlset_extrai_urls_e_descarta_cross_domain():
    urls, subs = sm._parse(_URLSET)
    assert "https://exemplo.com.br/blog/post-1" in urls
    assert "https://exemplo.com.br/" in urls
    assert subs == []
    # cross-domain também é extraído aqui; o filtro de domínio é aplicado em coletar_urls_do_sitemap.
    assert "https://outro-dominio.com/x" in urls


def test_parse_index_extrai_sub_sitemaps():
    urls, subs = sm._parse(_INDEX)
    assert urls == []
    assert subs == ["https://exemplo.com.br/sitemap-posts.xml"]


def test_parse_malformado_retorna_vazio():
    urls, subs = sm._parse("<<< not xml >>>")
    assert urls == []
    assert subs == []


def test_coletar_descarta_outro_dominio(monkeypatch):
    """URLs de outro domínio no sitemap são descartadas."""
    async def fake_fetch(url):
        return _URLSET if url.endswith("/sitemap.xml") else None
    monkeypatch.setattr(sm, "_fetch", fake_fetch)
    # _check_host precisa passar para o domínio válido.
    monkeypatch.setattr(sm, "_check_host", lambda d: "ok")

    urls = [u for u in __import__("asyncio").run(
        sm.coletar_urls_do_sitemap("exemplo.com.br", teto=500)
    )]
    assert all("exemplo.com.br" in u for u in urls)
    assert "https://outro-dominio.com/x" not in urls


def test_coletar_respeita_teto(monkeypatch):
    """O teto corta o número de URLs retornadas."""
    many = "\n".join(
        f"<url><loc>https://exemplo.com.br/p{i}</loc></url>" for i in range(50)
    )
    doc = f"<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{many}</urlset>"

    async def fake_fetch(url):
        return doc if url.endswith("/sitemap.xml") else None
    monkeypatch.setattr(sm, "_fetch", fake_fetch)
    monkeypatch.setattr(sm, "_check_host", lambda d: "ok")

    import asyncio
    urls = asyncio.run(sm.coletar_urls_do_sitemap("exemplo.com.br", teto=10))
    assert len(urls) == 10


def test_coletar_bloqueia_host_privado(monkeypatch):
    """Host privado (loopback/private) é bloqueado pelo SSRF guard — retorna []."""
    # Não mockamos _check_host: o valor real rejeita 127.0.0.1 e 10.x.
    import asyncio
    urls = asyncio.run(sm.coletar_urls_do_sitemap("127.0.0.1", teto=10))
    assert urls == []


@pytest.mark.asyncio
async def test_coletar_index_recursivo(monkeypatch):
    """Sitemap-index apontando para um urlset é seguido recursivamente."""
    posts = """<?xml version='1.0'?>
<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
  <url><loc>https://exemplo.com.br/blog/a</loc></url>
  <url><loc>https://exemplo.com.br/blog/b</loc></url>
</urlset>"""

    async def fake_fetch(url):
        if url.endswith("/sitemap.xml"):
            return _INDEX
        if url.endswith("/sitemap-posts.xml"):
            return posts
        return None

    monkeypatch.setattr(sm, "_fetch", fake_fetch)
    monkeypatch.setattr(sm, "_check_host", lambda d: "ok")

    urls = await sm.coletar_urls_do_sitemap("exemplo.com.br", teto=500)
    assert "https://exemplo.com.br/blog/a" in urls
    assert "https://exemplo.com.br/blog/b" in urls
