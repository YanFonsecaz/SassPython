"""SPEC_Inlinks_Remover_Reranker_Redundante — testes dos kill-switches.

Os kill-switches `inlinks_reranker_ativo` e `inlinks_revisor_ativo` (default True)
permitem desligar o reranker LLM e o revisor-lint sem deletar o código. Quando
desligados: o cosine ordena sozinho (score_total = score_semantico) e o revisor
curto-circuita sem chamada LLM. Defaults preservam o comportamento atual — o gate
de 2 semanas de produção fica documentado na spec, não no código.
"""

from unittest.mock import AsyncMock

import pytest

import app.agents.workflow_inlinks as wf


async def _fake_publish(*a, **kw):
    return None


async def _fake_etapa(*a, **kw):
    return None


@pytest.mark.asyncio
async def test_reranker_off_usa_cosine_puro_sem_chamar_llm(monkeypatch):
    """Com inlinks_reranker_ativo=False, score_total = score_semantico e o
    reranker LLM NÃO é chamado."""
    monkeypatch.setattr(wf, "_gravar_etapa", _fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", _fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_reranker_ativo", False)

    # Garante que o reranker NUNCA é importado/chamado.
    import sys
    reranker_spy = AsyncMock()
    monkeypatch.setitem(sys.modules, "app.agents.inlinks.reranker", reranker_spy)

    estado = {
        "execucao_id": "e1",
        "usuario_id": "u1",
        "pilar_embedding": [1.0, 0.0],
        "candidatas_embeddings": [
            {"url": "https://ex.com/a", "embedding": [0.9, 0.0], "titulo": "A"},
        ],
        "pilar_resultado": {"titulo": "P", "conteudo_md": "x"},
        "pilar_metadados": {},
        "funil": {},
        "threshold_score": 0.6,
    }
    out = await wf.node_match_rerank(estado)

    cand = out["candidatos_reranked"]
    assert len(cand) == 1
    # score_total == score_semantico (cosine puro, sem reranker).
    assert cand[0]["score_total"] == cand[0]["score_semantico"]
    assert cand[0]["score_contexto"] == cand[0]["score_semantico"]
    reranker_spy.rerank_candidatos.assert_not_called()


@pytest.mark.asyncio
async def test_reranker_on_chama_llm(monkeypatch):
    """Com inlinks_reranker_ativo=True (default), o reranker é chamado normalmente."""
    monkeypatch.setattr(wf, "_gravar_etapa", _fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", _fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_reranker_ativo", True)

    async def fake_rerank(titulo, conteudo, meta, scored, uid):
        # devolve com score_contexto distinto para provar que o reranker rodou
        return [{**c, "score_contexto": 0.5, "score_total": 0.5} for c in scored]

    import app.agents.inlinks.reranker as reranker_mod
    monkeypatch.setattr(reranker_mod, "rerank_candidatos", fake_rerank)

    estado = {
        "execucao_id": "e1",
        "usuario_id": "u1",
        "pilar_embedding": [1.0, 0.0],
        "candidatas_embeddings": [
            {"url": "https://ex.com/a", "embedding": [0.9, 0.0], "titulo": "A"},
        ],
        "pilar_resultado": {"titulo": "P", "conteudo_md": "x"},
        "pilar_metadados": {},
        "funil": {},
        "threshold_score": 0.6,
    }
    out = await wf.node_match_rerank(estado)

    cand = out["candidatos_reranked"]
    assert cand[0]["score_contexto"] == 0.5  # veio do reranker, não do cosine


@pytest.mark.asyncio
async def test_revisor_off_curto_circuita_sem_llm(monkeypatch):
    """Com inlinks_revisor_ativo=False, node_revisar retorna os inlinks sem
    chamar o revisor e registra 0 rejeições."""
    monkeypatch.setattr(wf, "_gravar_etapa", _fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", _fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_revisor_ativo", False)

    # Garante que o revisor NÃO é importado.
    import sys
    revisor_spy = AsyncMock()
    monkeypatch.setitem(sys.modules, "app.agents.inlinks.revisor", revisor_spy)

    inlinks = [
        {"url_destino": "https://ex.com/a", "status": "aplicado", "anchor_text": "a"},
    ]
    estado = {
        "execucao_id": "e1",
        "usuario_id": "u1",
        "inlinks_aplicados": inlinks,
        "pilar_modificado": "texto",
        "pilar_resultado": {"conteudo_md": "texto"},
        "funil": {},
    }
    out = await wf.node_revisar(estado)

    # Retorna os inlinks inalterados.
    assert out["inlinks_revisados"] == inlinks
    assert out["funil"]["n_rejeitados_revisor"] == 0
    revisor_spy.revisar_inlinks.assert_not_called()


@pytest.mark.asyncio
async def test_revisor_on_chama_llm(monkeypatch):
    """Com inlinks_revisor_ativo=True (default), o revisor é chamado."""
    monkeypatch.setattr(wf, "_gravar_etapa", _fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", _fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_revisor_ativo", True)

    async def fake_revisar(original, modificado, inlinks, uid):
        return [{**i, "status": "aplicado"} for i in inlinks]

    import app.agents.inlinks.revisor as revisor_mod
    monkeypatch.setattr(revisor_mod, "revisar_inlinks", fake_revisar)
    import app.agents.inlinks.injector as injector_mod
    monkeypatch.setattr(
        injector_mod, "remover_links_rejeitados",
        lambda mod, revs: mod,
    )

    estado = {
        "execucao_id": "e1",
        "usuario_id": "u1",
        "inlinks_aplicados": [{"url_destino": "https://ex.com/a", "status": "aplicado"}],
        "pilar_modificado": "texto",
        "pilar_resultado": {"conteudo_md": "texto"},
        "funil": {},
    }
    out = await wf.node_revisar(estado)
    assert out["funil"]["n_rejeitados_revisor"] == 0
