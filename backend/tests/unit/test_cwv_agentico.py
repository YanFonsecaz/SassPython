"""Testes SPEC_CWV_Navegacao_Agentica_Geracao_IA: agente + fetch de site.

LLM e httpx mockados (padrão test_cwv_consolidador / test_page_experience).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.cwv.agentico import CWVAgenticoAgent, LlmsTxtOut, WebMcpOut
from app.services import cwv_site_fetch as sf
from app.services.cwv_site_fetch import coletar_conteudo_site, detectar_sinais_webmcp


def _agente_sem_llm() -> CWVAgenticoAgent:
    """Instancia sem __init__ (não constrói o LLM) — só invoke_structured é usado."""
    return CWVAgenticoAgent.__new__(CWVAgenticoAgent)


# --- agente llms.txt ------------------------------------------------------


@pytest.mark.asyncio
async def test_gerar_llms_txt_injeta_h1_se_llm_esquecer():
    agente = _agente_sem_llm()
    agente.invoke_structured = AsyncMock(return_value=LlmsTxtOut(
        diagnostico="ausente",
        conteudo_llms_txt="Sem heading aqui, só texto.",
        justificativa="não havia arquivo",
    ))
    out = await agente.gerar_llms_txt({"origem": "https://ex.com", "title": "Loja X"}, None)
    assert out.conteudo_llms_txt.startswith("# Loja X")
    assert out.diagnostico == "ausente"


@pytest.mark.asyncio
async def test_gerar_llms_txt_preserva_h1_existente():
    agente = _agente_sem_llm()
    agente.invoke_structured = AsyncMock(return_value=LlmsTxtOut(
        diagnostico="coerente",
        conteudo_llms_txt="# Já tem H1\n\nconteúdo bom",
        justificativa="ok",
    ))
    out = await agente.gerar_llms_txt({"origem": "https://ex.com", "title": "X"}, "# atual")
    assert out.conteudo_llms_txt.startswith("# Já tem H1")


@pytest.mark.asyncio
async def test_gerar_llms_txt_h1_fallback_para_host_sem_title():
    agente = _agente_sem_llm()
    agente.invoke_structured = AsyncMock(return_value=LlmsTxtOut(
        diagnostico="ausente", conteudo_llms_txt="texto sem h1", justificativa="x",
    ))
    out = await agente.gerar_llms_txt({"origem": "https://ex.com", "title": None}, None)
    assert out.conteudo_llms_txt.startswith("# ex.com")


# --- agente webmcp --------------------------------------------------------


@pytest.mark.asyncio
async def test_gerar_webmcp_repassa_saida():
    agente = _agente_sem_llm()
    agente.invoke_structured = AsyncMock(return_value=WebMcpOut(
        detectado=False,
        ferramentas_sugeridas=["buscar_produto", "contato"],
        codigo="// WebMCP scaffold\nnavigator.modelContext.registerTool(...)",
        linguagem="javascript",
        explicacao_md="explicação",
        como_aplicar_md="passos",
    ))
    out = await agente.gerar_webmcp({"origem": "https://ex.com"}, "vtex", {"detectado": False, "sinais": {}})
    assert out.detectado is False
    assert "buscar_produto" in out.ferramentas_sugeridas
    assert "registerTool" in out.codigo


# --- site fetch -----------------------------------------------------------


def test_detectar_sinais_webmcp_positivo():
    r = detectar_sinais_webmcp("<script>navigator.modelContext.registerTool()</script>")
    assert r["detectado"] is True
    assert r["sinais"]["navigator.modelcontext"] is True


def test_detectar_sinais_webmcp_negativo():
    r = detectar_sinais_webmcp("<html><body>site comum sem agentes</body></html>")
    assert r["detectado"] is False


class _FakeResp:
    def __init__(self, status: int, text: str, ctype: str = "text/html"):
        self.status_code = status
        self.text = text
        self.headers = {"content-type": ctype}


class _FakeClient:
    is_closed = False

    async def get(self, url: str):
        if url.endswith("/llms.txt"):
            return _FakeResp(200, "# Atual\n\nconteúdo", "text/plain")
        if url.endswith("/sitemap.xml"):
            return _FakeResp(200, "<urlset><url><loc>https://ex.com/a</loc></url></urlset>", "application/xml")
        return _FakeResp(
            200,
            "<html><head><title>Loja X</title>"
            "<meta name='description' content='melhor loja'></head>"
            "<body><h1>Bem-vindo</h1><nav><a href='/p'>Produtos</a></nav>"
            "<script>navigator.modelContext.registerTool()</script></body></html>",
        )


@pytest.mark.asyncio
async def test_coletar_conteudo_site_extrai_tudo(monkeypatch):
    monkeypatch.setattr(sf, "_CLIENT", _FakeClient())
    site = await coletar_conteudo_site(["https://ex.com/"])
    assert site["origem"] == "https://ex.com"
    assert site["title"] == "Loja X"
    assert site["meta_description"] == "melhor loja"
    assert "Bem-vindo" in site["h1"]
    assert "Produtos" in site["nav_links"]
    assert site["llms_txt_atual"] == "# Atual\n\nconteúdo"
    assert "https://ex.com/a" in site["sitemap_urls"]
    assert site["webmcp"]["detectado"] is True


@pytest.mark.asyncio
async def test_coletar_conteudo_site_sem_urls_nao_quebra():
    site = await coletar_conteudo_site([])
    assert site["origem"] is None
    assert site["title"] is None


@pytest.mark.asyncio
async def test_coletar_conteudo_site_fail_open(monkeypatch):
    """Erro de rede na homepage → resumo parcial, nunca levanta."""
    class _BoomClient:
        is_closed = False

        async def get(self, url: str):
            raise RuntimeError("network down")

    monkeypatch.setattr(sf, "_CLIENT", _BoomClient())
    site = await coletar_conteudo_site(["https://ex.com/"])
    assert site["origem"] == "https://ex.com"  # derivado da URL, sem rede
    assert site["title"] is None
