"""Testes do agente recomendador SEOTEC (SPEC_SEOTEC_Agentes_IA nó `recomendar_ia`).

Cobre: fluxo KB→LLM (hit canônico, variação plataforma, miss→LLM, aprovado sem
KB = texto fixo), lote, fail-open em erro LLM, sugerir_amostra (limita a N URLs
e falha sem quebrar).
"""
import pytest

from app.agents.seotec.recomendador import (
    APROVADO_SEM_KB,
    ListaRecomendacoes,
    ListaSugestoesOut,
    RecomendacaoOut,
    SeotecRecomendadorAgent,
    SugestaoUrlOut,
    montar_contexto_recomendacao,
)
from app.services.seotec_checklist import ItemChecklist
from app.services.seotec_motor import ResultadoItem


def _item(slug: str, status_alvo: str = "reprovado", **kw) -> ItemChecklist:
    base = dict(
        slug=slug, nome=slug, peso=1, prioridade="medium",
        implementacao="bom-ter", responsavel=["dev"], impacto={"direto": True},
        fonte="sf", categoria="Cat", descricao="d", importancia="i",
    )
    base.update(kw)
    return ItemChecklist(**base)


def _ctx(slug: str, status: str = "reprovado", **extra) -> dict:
    base = {
        "slug": slug, "nome": slug, "categoria": "Cat", "prioridade": "high",
        "descricao": "d", "importancia": "i", "status": status,
        "total_avaliadas": 10, "total_afetadas": 3, "amostra": [],
        "avaliacao_ia": False, "recomendada_ia": False,
    }
    base.update(extra)
    return base


def test_montar_contexto_inclui_aprovado_reprovado_atencao():
    ck = type("CK", (), {"itens_por_slug": lambda self: {
        "item-a": _item("item-a"), "item-r": _item("item-r"),
        "item-t": _item("item-t"), "item-s": _item("item-s"),
    }})()
    resultados = {
        "item-a": ResultadoItem(status="aprovado"),
        "item-r": ResultadoItem(status="reprovado"),
        "item-t": ResultadoItem(status="atencao"),
        "item-s": ResultadoItem(status="sem_dados"),
    }
    ctx = montar_contexto_recomendacao(ck, resultados)
    assert {c["slug"] for c in ctx} == {"item-a", "item-r", "item-t"}


def test_montar_contexto_propaga_flags_ia():
    ck = type("CK", (), {"itens_por_slug": lambda self: {
        "item-x": _item("item-x", recomendada_ia=True, avaliacao_ia=True),
    }})()
    resultados = {"item-x": ResultadoItem(status="reprovado")}
    ctx = montar_contexto_recomendacao(ck, resultados)
    assert ctx[0]["recomendada_ia"] is True
    assert ctx[0]["avaliacao_ia"] is True


@pytest.mark.asyncio
async def test_recomendar_kb_hit_nao_chama_llm():
    async def explode(*a, **kw):
        raise AssertionError("LLM não deveria ser chamado para hit na KB")

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = explode
    itens = [_ctx("tag-h1-ausente-ou-vazia")]  # coberto por headings.yaml

    recs, pendentes = await agente.recomendar(itens, "geral")
    assert "tag-h1-ausente-ou-vazia" in recs
    assert "h1" in recs["tag-h1-ausente-ou-vazia"].lower()
    assert pendentes == []


@pytest.mark.asyncio
async def test_recomendar_kb_hit_usa_variacao_plataforma():
    async def explode(*a, **kw):
        raise AssertionError("LLM não deveria ser chamado para hit na KB")

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = explode

    recs_geral, _ = await agente.recomendar([_ctx("tag-h1-ausente-ou-vazia")], "geral")
    recs_wp, _ = await agente.recomendar([_ctx("tag-h1-ausente-ou-vazia")], "wordpress")
    assert recs_geral != recs_wp


@pytest.mark.asyncio
async def test_recomendar_aprovado_sem_kb_recebe_texto_curto_sem_llm():
    async def explode(*a, **kw):
        raise AssertionError("LLM não deveria rodar para aprovado")

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = explode
    itens = [_ctx("slug-nao-existe-na-kb", status="aprovado")]

    recs, pendentes = await agente.recomendar(itens, "geral")
    assert recs["slug-nao-existe-na-kb"] == APROVADO_SEM_KB
    assert pendentes == []


@pytest.mark.asyncio
async def test_recomendar_miss_chama_llm_em_lote():
    async def fake_invoke_structured(prompt, schema):
        assert schema is ListaRecomendacoes
        return ListaRecomendacoes(itens=[
            RecomendacaoOut(slug="slug-orfao-1", recomendacao="Corrija X."),
        ])

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens = [_ctx("slug-orfao-1"), _ctx("slug-orfao-2")]

    recs, pendentes = await agente.recomendar(itens, "geral")
    assert recs["slug-orfao-1"] == "Corrija X."
    # slug-orfao-2 não voltou do LLM → pendente.
    assert pendentes == ["slug-orfao-2"]


@pytest.mark.asyncio
async def test_recomendar_llm_falha_deixa_tudo_pendente():
    async def boom(prompt, schema):
        raise RuntimeError("offline")

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = boom
    itens = [_ctx("slug-orfao-1"), _ctx("slug-orfao-2")]

    recs, pendentes = await agente.recomendar(itens, "geral")
    assert recs == {}
    assert sorted(pendentes) == ["slug-orfao-1", "slug-orfao-2"]


@pytest.mark.asyncio
async def test_recomendar_respeita_lote(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "seotec_ia_lote", 2)
    chamadas = {"n": 0}

    async def fake_invoke_structured(prompt, schema):
        chamadas["n"] += 1
        return ListaRecomendacoes(itens=[])

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens = [_ctx(f"slug-{i}") for i in range(5)]

    _, pendentes = await agente.recomendar(itens, "geral")
    assert chamadas["n"] == 3  # 5 itens / lote 2 = 3 chamadas
    assert len(pendentes) == 5


@pytest.mark.asyncio
async def test_recomendar_descarta_slugs_inventados_pelo_llm():
    async def fake_invoke_structured(prompt, schema):
        return ListaRecomendacoes(itens=[
            RecomendacaoOut(slug="slug-inventado-pelo-llm", recomendacao="x"),
        ])

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens = [_ctx("slug-real-orfao")]

    recs, pendentes = await agente.recomendar(itens, "geral")
    assert recs == {}
    assert pendentes == ["slug-real-orfao"]


@pytest.mark.asyncio
async def test_sugerir_amostra_vazio_quando_sem_itens():
    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    out = await agente.sugerir_amostra([], "geral")
    assert out == {}


@pytest.mark.asyncio
async def test_sugerir_amostra_limita_a_max_amostra(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "seotec_ia_amostra_max", 3)

    capturado = {"prompt": ""}

    async def fake_invoke_structured(prompt, schema):
        capturado["prompt"] = prompt
        return ListaSugestoesOut(slug="x", sugestoes=[
            SugestaoUrlOut(url="https://a/1", sugestao="s1"),
        ])

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens_ri = [{
        "slug": "item-x", "nome": "n",
        "descricao": "desc", "importancia": "imp",
        "amostra": [{"address": f"https://a/{i}"} for i in range(20)],
    }]
    out = await agente.sugerir_amostra(itens_ri, "geral")
    # Prompt só recebeu 3 URLs (limite), não as 20 da amostra.
    assert capturado["prompt"].count("https://a/") == 3
    assert out == {"item-x": [{"url": "https://a/1", "sugestao": "s1"}]}


@pytest.mark.asyncio
async def test_sugerir_amostra_fail_open_em_erro_llm():
    async def boom(prompt, schema):
        raise RuntimeError("offline")

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = boom
    itens_ri = [{
        "slug": "item-x", "nome": "n",
        "descricao": "desc", "importancia": "imp",
        "amostra": [{"address": "https://a/"}],
    }]

    out = await agente.sugerir_amostra(itens_ri, "geral")
    assert out == {}


@pytest.mark.asyncio
async def test_sugerir_amostra_pula_itens_sem_amostra():
    chamadas = {"n": 0}

    async def fake_invoke_structured(prompt, schema):
        chamadas["n"] += 1
        return ListaSugestoesOut(slug="x", sugestoes=[])

    agente = SeotecRecomendadorAgent.__new__(SeotecRecomendadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens_ri = [{"slug": "x", "nome": "n", "amostra": []}]

    out = await agente.sugerir_amostra(itens_ri, "geral")
    assert out == {}
    assert chamadas["n"] == 0
