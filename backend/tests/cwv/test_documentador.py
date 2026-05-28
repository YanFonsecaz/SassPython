import pytest


@pytest.mark.asyncio
async def test_documentador_gera_markdown_com_secoes():
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    problemas = [{"kb_codigo": "lcp-imagem-grande", "contexto_especifico": {"display_value": "4.2s", "items": []}}]
    docs = await CWVDocumentadorAgent().documentar(problemas=problemas, plataforma="vtex")
    assert len(docs) == 1
    md = docs[0]["documentacao_md"]
    assert "## Problema" in md
    assert "## Solu" in md
    assert "VTEX" in md or "vtex" in md


@pytest.mark.asyncio
async def test_documentador_kb_codigo_invalido_gera_skeleton():
    """Pos SPEC #17: kb_codigo nao encontrado vira problema com doc skeleton, nao e filtrado."""
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    problemas = [{
        "kb_codigo": "codigo-inventado",
        "audit_id": "qualquer-audit",
        "contexto_especifico": {"title": "Audit titulo", "description": "Audit description"},
    }]
    docs = await CWVDocumentadorAgent().documentar(problemas=problemas, plataforma="geral")
    assert len(docs) == 1
    assert docs[0]["kb_codigo"] == "codigo-inventado"
    assert "Audit titulo" in docs[0]["documentacao_md"] or "Audit description" in docs[0]["documentacao_md"]


@pytest.mark.asyncio
async def test_documentador_md_nao_inclui_display_value_redundante():
    """Pos SPEC #18 F4: display_value vai no banner do frontend, nao no markdown."""
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    problemas = [{"kb_codigo": "lcp-imagem-grande", "contexto_especifico": {"display_value": "5.1s", "items": []}}]
    docs = await CWVDocumentadorAgent().documentar(problemas=problemas, plataforma="geral")
    md = docs[0]["documentacao_md"]
    assert "Valor medido" not in md
    assert "Elementos afetados" not in md


@pytest.mark.asyncio
async def test_documentador_inclui_links_referencia():
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    problemas = [{"kb_codigo": "lcp-imagem-grande", "contexto_especifico": {"items": []}}]
    docs = await CWVDocumentadorAgent().documentar(problemas=problemas, plataforma="geral")
    md = docs[0]["documentacao_md"]
    assert "## Referencias" in md
    assert "web.dev" in md


@pytest.mark.asyncio
async def test_documentador_items_ficam_no_contexto_especifico():
    """Pos SPEC #18 F4: items vao para tabela do frontend via contexto_especifico, nao no md."""
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    problemas = [{"kb_codigo": "lcp-imagem-grande", "contexto_especifico": {
        "display_value": "4.2s",
        "items": [{"url": "https://example.com/hero.jpg", "node": {"selector": "#hero > img"}}],
    }}]
    docs = await CWVDocumentadorAgent().documentar(problemas=problemas, plataforma="geral")
    assert docs[0]["contexto_especifico"]["items"][0]["url"] == "https://example.com/hero.jpg"


@pytest.mark.asyncio
async def test_documentador_plataforma_sem_solucao_especifica():
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    problemas = [{"kb_codigo": "lcp-imagem-grande", "contexto_especifico": {"items": []}}]
    docs = await CWVDocumentadorAgent().documentar(problemas=problemas, plataforma="geral")
    md = docs[0]["documentacao_md"]
    assert "Solucao geral" in md
