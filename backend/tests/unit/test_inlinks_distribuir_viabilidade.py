"""SPEC_Distribuir_Viabilidade_Pelo_Juiz — testes do node_filtrar_similaridade.

Cobre os 4 contratos da spec:
1. caminho novo: piso de ruído 0.25 substitui o threshold;
2. keyword override vira sinal (não promove sozinho);
3. teto de julgamentos (distribuir_max_julgamentos) corta no top-N;
4. flag legado (inlinks_pisos_legado_distribuir=True) restaura o threshold antigo.
"""

import pytest

import app.agents.workflow_inlinks_reversos as wf
from app.core import embeddings as emb_mod


def _cand(url: str, score: float, conteudo: str = "texto", kw: bool = False) -> dict:
    return {
        "url": url,
        "url_canonica": url,
        "titulo": url,
        "resumo": "",
        "palavras_chave": [],
        "score_semantico": score,
        "conteudo_md": conteudo,
        "sinal_keyword_alvo": kw,
    }


def _estado_base(candidatas_scores: list[tuple[str, float]], *, alvo_modo: str = "pleno"):
    """Monta um estado mínimo para chamar node_filtrar_similaridade.

    candidatas_embeddings já traz o embedding por URL; o cosine_seguro é
    substituído por uma função que devolve o score declarado, isolando a lógica
    de corte do cálculo vetorial real.
    """
    return {
        "execucao_id": "e1",
        "alvo_embedding": [1.0, 0.0],
        "candidatas_embeddings": [
            {"url": url, "url_canonica": url, "embedding": [score, 0.0], "titulo": url}
            for url, score in candidatas_scores
        ],
        "candidatas_resultados": [
            {"url": url, "conteudo_md": "texto"} for url, _ in candidatas_scores
        ],
        "threshold_score": 0.6,
        "alvo_modo": alvo_modo,
        "funil": {},
    }


@pytest.mark.asyncio
async def test_piso_substitui_threshold_no_modo_novo(monkeypatch):
    """Candidata com cosine 0.30 (abaixo do threshold 0.6 mas acima do piso 0.25)
    passa a ser viável — o juiz vai decidir."""
    async def fake_publish(*a, **kw):
        return None
    async def fake_etapa(*a, **kw):
        return None
    monkeypatch.setattr(wf, "_gravar_etapa", fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_pisos_legado_distribuir", False)
    monkeypatch.setattr(wf.settings, "distribuir_max_julgamentos", 30)
    # cosine_seguro é importado DENTRO do node; patcheamos no módulo de origem.
    monkeypatch.setattr(emb_mod, "cosine_seguro", lambda a, b: float(b[0]))

    estado = _estado_base([("https://ex.com/a", 0.30)])
    out = await wf.node_filtrar_similaridade(estado)

    assert len(out["candidatas_viaveis"]) == 1
    assert out["candidatas_viaveis"][0]["url"] == "https://ex.com/a"


@pytest.mark.asyncio
async def test_abaixo_do_piso_e_descartada(monkeypatch):
    """Candidata com cosine 0.10 (< piso 0.25) é descartada como ruído."""
    async def fake_publish(*a, **kw):
        return None
    async def fake_etapa(*a, **kw):
        return None
    monkeypatch.setattr(wf, "_gravar_etapa", fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_pisos_legado_distribuir", False)
    monkeypatch.setattr(emb_mod, "cosine_seguro", lambda a, b: float(b[0]))

    estado = _estado_base([("https://ex.com/ruido", 0.10)])
    out = await wf.node_filtrar_similaridade(estado)

    assert len(out["candidatas_viaveis"]) == 0
    assert len(out["candidatas_descartadas"]) == 1
    assert "piso" in out["candidatas_descartadas"][0]["motivo_descarte"]


@pytest.mark.asyncio
async def test_teto_top_n_corta_excedentes(monkeypatch):
    """Com max_julgamentos=2 e 3 candidatas acima do piso, só top-2 vão ao juiz;
    a 3ª vira sem_match 'fora do top-N'."""
    async def fake_publish(*a, **kw):
        return None
    async def fake_etapa(*a, **kw):
        return None
    monkeypatch.setattr(wf, "_gravar_etapa", fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_pisos_legado_distribuir", False)
    monkeypatch.setattr(wf.settings, "distribuir_max_julgamentos", 2)
    monkeypatch.setattr(emb_mod, "cosine_seguro", lambda a, b: float(b[0]))

    estado = _estado_base([
        ("https://ex.com/alta", 0.90),
        ("https://ex.com/media", 0.50),
        ("https://ex.com/baixa", 0.30),
    ])
    out = await wf.node_filtrar_similaridade(estado)

    assert len(out["candidatas_viaveis"]) == 2
    viaveis_urls = {c["url"] for c in out["candidatas_viaveis"]}
    assert viaveis_urls == {"https://ex.com/alta", "https://ex.com/media"}
    # A excedente foi descartada com motivo de top-N.
    assert len(out["candidatas_descartadas"]) == 1
    assert "top-2" in out["candidatas_descartadas"][0]["motivo_descarte"]


@pytest.mark.asyncio
async def test_keyword_vira_sinal_nao_promove(monkeypatch):
    """No slug_only com keyword match, o sinal é registrado na candidata viável
    (não é mais um override que promove sozinho). Acima do piso, ela vai ao juiz
    com sinal_keyword_alvo=True."""
    async def fake_publish(*a, **kw):
        return None
    async def fake_etapa(*a, **kw):
        return None
    monkeypatch.setattr(wf, "_gravar_etapa", fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_pisos_legado_distribuir", False)
    monkeypatch.setattr(wf.settings, "distribuir_max_julgamentos", 30)
    monkeypatch.setattr(emb_mod, "cosine_seguro", lambda a, b: float(b[0]))

    # Força _candidata_tem_keyword_alvo a retornar True.
    monkeypatch.setattr(wf, "_candidata_tem_keyword_alvo", lambda c, p: True)

    estado = _estado_base([("https://ex.com/slug", 0.40)], alvo_modo="slug_only")
    estado["alvo_resultado"] = {"pseudo_palavras_chave": ["slug"]}
    out = await wf.node_filtrar_similaridade(estado)

    assert len(out["candidatas_viaveis"]) == 1
    assert out["candidatas_viaveis"][0]["sinal_keyword_alvo"] is True


@pytest.mark.asyncio
async def test_flag_legado_restaura_threshold(monkeypatch):
    """Com inlinks_pisos_legado_distribuir=True, o threshold 0.6 volta a valer:
    candidata com cosine 0.30 é descartada (comportamento pré-spec)."""
    async def fake_publish(*a, **kw):
        return None
    async def fake_etapa(*a, **kw):
        return None
    monkeypatch.setattr(wf, "_gravar_etapa", fake_etapa)
    import app.core.workflow_events as ev
    monkeypatch.setattr(ev, "publish_event", fake_publish)
    monkeypatch.setattr(wf.settings, "inlinks_pisos_legado_distribuir", True)
    monkeypatch.setattr(emb_mod, "cosine_seguro", lambda a, b: float(b[0]))

    estado = _estado_base([("https://ex.com/a", 0.30)])
    out = await wf.node_filtrar_similaridade(estado)

    assert len(out["candidatas_viaveis"]) == 0
    assert len(out["candidatas_descartadas"]) == 1
    # threshold_informativo reflete o threshold legado (0.6), não o piso.
    assert out["funil"]["threshold_informativo"] == 0.6
