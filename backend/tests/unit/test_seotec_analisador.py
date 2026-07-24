"""Testes do agente analisador SEOTEC (SPEC_SEOTEC_Agentes_IA nó `analisar_ia`).

Mock de invoke_structured (sem rede). Valida:
- montar_contexto_itens filtra só reprovado/atencao com regra.
- diagnosticar preenche dict por slug e marca pendentes em falha de LLM.
- lote respeita settings.seotec_ia_lote (mais de 1 chamada para >lote itens).
"""
import pytest

from app.agents.seotec.analisador import (
    DiagnosticoOut,
    ListaDiagnosticos,
    SeotecAnalisadorAgent,
    montar_contexto_itens,
)
from app.services.seotec_checklist import ItemChecklist
from app.services.seotec_motor import ResultadoItem


def _item(slug: str, nome: str = "x", categoria: str = "Cat") -> ItemChecklist:
    return ItemChecklist(
        slug=slug, nome=nome, peso=1, prioridade="medium",
        implementacao="bom-ter", responsavel=["dev"], impacto={"direto": True},
        fonte="sf", categoria=categoria,
        descricao="desc", importancia="imp",
    )


def test_montar_contexto_filtra_apenas_diagnosticaveis():
    ck = type("CK", (), {"itens_por_slug": lambda self: {
        "item-ok": _item("item-ok"),
        "item-ruim": _item("item-ruim"),
        "item-atencao": _item("item-atencao"),
        "item-semdados": _item("item-semdados"),
    }})()
    resultados = {
        "item-ok": ResultadoItem(status="aprovado"),
        "item-ruim": ResultadoItem(status="reprovado", total_avaliadas=10, total_afetadas=3),
        "item-atencao": ResultadoItem(status="atencao", total_avaliadas=10, total_afetadas=1),
        "item-semdados": ResultadoItem(status="sem_dados"),
    }
    ctx = montar_contexto_itens(ck, resultados)
    slugs = {c["slug"] for c in ctx}
    assert slugs == {"item-ruim", "item-atencao"}


def test_montar_contexto_ignora_slug_sem_item_no_checklist():
    ck = type("CK", (), {"itens_por_slug": lambda self: {"ruim": _item("ruim")}})()
    resultados = {
        "ruim": ResultadoItem(status="reprovado"),
        "sumido": ResultadoItem(status="reprovado"),
    }
    ctx = montar_contexto_itens(ck, resultados)
    assert {c["slug"] for c in ctx} == {"ruim"}


def test_montar_contexto_trunca_amostra_para_5():
    ck = type("CK", (), {"itens_por_slug": lambda self: {"ruim": _item("ruim")}})()
    amostra_grande = [{"address": f"https://x/{i}"} for i in range(50)]
    resultados = {"ruim": ResultadoItem(status="reprovado", amostra=amostra_grande)}
    ctx = montar_contexto_itens(ck, resultados)
    assert len(ctx[0]["amostra"]) == 5


@pytest.mark.asyncio
async def test_diagnosticar_preenche_dict_por_slug(monkeypatch):
    async def fake_invoke_structured(prompt, schema):
        assert schema is ListaDiagnosticos
        return ListaDiagnosticos(itens=[
            DiagnosticoOut(slug="title-tag-ausente-ou-vazia", diagnostico="3 de 10 páginas sem title."),
            DiagnosticoOut(slug="tag-h1-ausente-ou-vazia", diagnostico="H1 ausente em 5 páginas."),
        ])

    agente = SeotecAnalisadorAgent.__new__(SeotecAnalisadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens_ctx = [
        {"slug": "title-tag-ausente-ou-vazia", "nome": "Title", "categoria": "Title",
         "prioridade": "high", "descricao": "d", "importancia": "i", "status": "reprovado",
         "total_avaliadas": 10, "total_afetadas": 3, "amostra": []},
        {"slug": "tag-h1-ausente-ou-vazia", "nome": "H1", "categoria": "Headings",
         "prioridade": "high", "descricao": "d", "importancia": "i", "status": "reprovado",
         "total_avaliadas": 10, "total_afetadas": 5, "amostra": []},
    ]

    diagnosticos, pendentes = await agente.diagnosticar(itens_ctx, {"dominio": "x", "plataforma": "geral"})
    assert diagnosticos == {
        "title-tag-ausente-ou-vazia": "3 de 10 páginas sem title.",
        "tag-h1-ausente-ou-vazia": "H1 ausente em 5 páginas.",
    }
    assert pendentes == []


@pytest.mark.asyncio
async def test_diagnosticar_marca_pendentes_quando_llm_falha(monkeypatch):
    call_count = {"n": 0}

    async def fake_invoke_structured(prompt, schema):
        call_count["n"] += 1
        raise RuntimeError("LLM offline")

    agente = SeotecAnalisadorAgent.__new__(SeotecAnalisadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens_ctx = [
        {"slug": "item-a", "nome": "A", "categoria": "C", "prioridade": "high",
         "descricao": "d", "importancia": "i", "status": "reprovado",
         "total_avaliadas": 1, "total_afetadas": 1, "amostra": []},
    ]

    diagnosticos, pendentes = await agente.diagnosticar(itens_ctx, {"dominio": "x", "plataforma": "geral"})
    assert diagnosticos == {}
    assert pendentes == ["item-a"]
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_diagnosticar_respeita_lote(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "seotec_ia_lote", 2)

    chamadas = {"n": 0}

    async def fake_invoke_structured(prompt, schema):
        chamadas["n"] += 1
        return ListaDiagnosticos(itens=[])

    agente = SeotecAnalisadorAgent.__new__(SeotecAnalisadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens_ctx = [
        {"slug": f"slug-{i}", "nome": "n", "categoria": "c", "prioridade": "high",
         "descricao": "d", "importancia": "i", "status": "reprovado",
         "total_avaliadas": 1, "total_afetadas": 1, "amostra": []}
        for i in range(5)
    ]

    _, pendentes = await agente.diagnosticar(itens_ctx, {"dominio": "x", "plataforma": "geral"})
    # 5 itens / lote 2 => 3 chamadas; nenhum diagnóstico voltou => todos pendentes.
    assert chamadas["n"] == 3
    assert sorted(pendentes) == ["slug-0", "slug-1", "slug-2", "slug-3", "slug-4"]


@pytest.mark.asyncio
async def test_diagnosticar_ignora_slugs_fora_do_bloco():
    async def fake_invoke_structured(prompt, schema):
        return ListaDiagnosticos(itens=[
            DiagnosticoOut(slug="slug-inventado", diagnostico="x"),
        ])

    agente = SeotecAnalisadorAgent.__new__(SeotecAnalisadorAgent)
    agente.invoke_structured = fake_invoke_structured
    itens_ctx = [
        {"slug": "slug-real", "nome": "n", "categoria": "c", "prioridade": "high",
         "descricao": "d", "importancia": "i", "status": "reprovado",
         "total_avaliadas": 1, "total_afetadas": 1, "amostra": []},
    ]

    diagnosticos, pendentes = await agente.diagnosticar(itens_ctx, {"dominio": "x", "plataforma": "geral"})
    # slug inventado pelo LLM é descartado; slug real fica pendente.
    assert diagnosticos == {}
    assert pendentes == ["slug-real"]


def test_usa_modelo_dedicado_quando_openai(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "seotec_analisador_llm_model", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "seotec_analisador_llm_temperature", 0.1)
    monkeypatch.setattr(settings, "openai_api_key", "fake-key")

    agente = SeotecAnalisadorAgent(usuario_id="u")
    assert agente.llm.model_name == "gpt-4.1-mini"
    assert agente.llm.temperature == 0.1
