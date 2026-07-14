"""Testes do consolidador Cross-URL (SPEC_CWV_Consolidador_Cross_URL).

Testa a fase 1 determinística (agrupar_problemas) e a validação fail-open
da fase 2 (LLM). O LLM é mockado via monkeypatch em invoke_structured.
"""
from __future__ import annotations

import pytest

from app.agents.cwv.consolidador import (
    ConsolidacaoOut,
    GrupoConsolidadoOut,
    _validar_e_aplicar_llm,
    agrupar_problemas,
)


def _prob(titulo, kb_codigo=None, audit_id=None, severidade=3, url="https://a.com/", estrategia="mobile", esforco=None, savings_ms=None, items=None):
    ctx = {}
    if savings_ms:
        ctx["savings_ms"] = savings_ms
    if items:
        ctx["items"] = items
    return {
        "id": f"id-{titulo}-{url}-{estrategia}",
        "kb_codigo": kb_codigo,
        "audit_id": audit_id,
        "titulo": titulo,
        "severidade": severidade,
        "esforco": esforco,
        "metricas_afetadas": ["LCP"],
        "contexto_especifico": ctx,
        "documentacao_md": "",
        "url_canonica": url,
        "estrategia": estrategia,
    }


def test_fase1_agrupa_16_problemas_mesma_chave_em_1_grupo():
    probs = [
        _prob("Render blocking", kb_codigo="fcp-render-blocking", url=f"https://u{i}.com/", estrategia=e)
        for i in range(8) for e in ("mobile", "desktop")
    ]
    grupos = agrupar_problemas(probs)
    assert len(grupos) == 1
    g = grupos[0]
    assert len(g["urls"]) == 8
    assert sorted(g["estrategias"]) == ["desktop", "mobile"]
    assert g["severidade"] == 3
    assert g["grupo_id"] == 1


def test_fase1_chaves_distintas_grupos_distintos():
    probs = [
        _prob("A", kb_codigo="kb-a"),
        _prob("B", kb_codigo="kb-b"),
        _prob("C", audit_id="audit-c"),
    ]
    grupos = agrupar_problemas(probs)
    assert len(grupos) == 3
    chaves = {g["chave"] for g in grupos}
    assert chaves == {"kb-a", "kb-b", "audit:audit-c"}


def test_fase1_severidade_max_e_esforco_max():
    probs = [
        _prob("X", kb_codigo="kb-x", severidade=2, esforco="baixo"),
        _prob("X", kb_codigo="kb-x", severidade=5, esforco="alto"),
    ]
    grupos = agrupar_problemas(probs)
    assert grupos[0]["severidade"] == 5
    assert grupos[0]["esforco"] == "alto"


def test_fase1_top_recursos_3_maiores():
    probs = [
        _prob("Long tasks", kb_codigo="kb-lt", audit_id="long-tasks", items=[
            {"url": "https://a.com/big.js", "wastedMs": 900},
            {"url": "https://a.com/med.js", "wastedMs": 300},
            {"url": "https://a.com/small.js", "wastedMs": 50},
            {"url": "https://a.com/huge.js", "wastedMs": 2000},
        ]),
    ]
    grupos = agrupar_problemas(probs)
    top = grupos[0]["top_recursos"]
    assert len(top) == 3
    assert top[0]["recurso"] == "https://a.com/huge.js"
    assert top[0]["wasted"] == 2000.0


def test_fase1_savings_somados():
    probs = [
        _prob("X", kb_codigo="kb-x", savings_ms=100),
        _prob("X", kb_codigo="kb-x", savings_ms=200),
    ]
    grupos = agrupar_problemas(probs)
    assert grupos[0]["savings_total_ms"] == 300.0


def test_fase2_llm_valido_mescla_grupos():
    grupos_fase1 = [
        {"grupo_id": 1, "chave": "kb-a", "titulo": "A", "kb_codigo": "kb-a", "audit_ids": [], "severidade": 3,
         "esforco": "baixo", "metricas_afetadas": ["LCP"], "urls": ["https://a.com/"], "estrategias": ["mobile"],
         "savings_total_ms": 0, "top_recursos": [], "problemas_ids": ["p1"]},
        {"grupo_id": 2, "chave": "kb-b", "titulo": "B", "kb_codigo": "kb-b", "audit_ids": [], "severidade": 4,
         "esforco": "medio", "metricas_afetadas": ["LCP"], "urls": ["https://b.com/"], "estrategias": ["desktop"],
         "savings_total_ms": 0, "top_recursos": [], "problemas_ids": ["p2"]},
        {"grupo_id": 3, "chave": "kb-c", "titulo": "C", "kb_codigo": "kb-c", "audit_ids": [], "severidade": 2,
         "esforco": "alto", "metricas_afetadas": ["CLS"], "urls": ["https://c.com/"], "estrategias": ["mobile"],
         "savings_total_ms": 0, "top_recursos": [], "problemas_ids": ["p3"]},
    ]
    resposta = ConsolidacaoOut(grupos=[
        GrupoConsolidadoOut(
            grupos_origem=[1, 2], titulo="A+B mesclados", causa_raiz="Bundle compartilhado",
            escopo_descricao="Produto e home", recomendacao_resumo="Otimizar bundle",
        ),
    ])
    mesclados = _validar_e_aplicar_llm(grupos_fase1, resposta)
    assert mesclados is not None
    # 1 mesclado (grupos 1+2) + 1 determinístico (grupo 3 não citado).
    assert len(mesclados) == 2
    mesclado = next(m for m in mesclados if "mesclados" in m["titulo"])
    assert set(mesclado["problemas_ids"]) == {"p1", "p2"}
    assert sorted(mesclado["urls"]) == ["https://a.com/", "https://b.com/"]


def test_fase2_grupo_id_inexistente_descarta_resposta():
    grupos_fase1 = [{"grupo_id": 1, "chave": "kb-a", "titulo": "A", "problemas_ids": ["p1"]}]
    resposta = ConsolidacaoOut(grupos=[
        GrupoConsolidadoOut(grupos_origem=[99], titulo="X", causa_raiz="Y", escopo_descricao="Z", recomendacao_resumo="W"),
    ])
    result = _validar_e_aplicar_llm(grupos_fase1, resposta)
    assert result is None  # resposta descartada


def test_fase2_grupo_id_repetido_descarta_resposta():
    grupos_fase1 = [
        {"grupo_id": 1, "chave": "kb-a", "titulo": "A", "problemas_ids": ["p1"]},
        {"grupo_id": 2, "chave": "kb-b", "titulo": "B", "problemas_ids": ["p2"]},
    ]
    resposta = ConsolidacaoOut(grupos=[
        GrupoConsolidadoOut(grupos_origem=[1], titulo="X", causa_raiz="Y", escopo_descricao="Z", recomendacao_resumo="W"),
        GrupoConsolidadoOut(grupos_origem=[1], titulo="X2", causa_raiz="Y2", escopo_descricao="Z2", recomendacao_resumo="W2"),
    ])
    result = _validar_e_aplicar_llm(grupos_fase1, resposta)
    assert result is None  # grupo 1 repetido


@pytest.mark.asyncio
async def test_kill_switch_desligado_nao_chama_llm(monkeypatch):
    from app.agents.cwv.consolidador import CWVConsolidadorAgent
    from app.config import settings

    monkeypatch.setattr(settings, "cwv_consolidador_llm_habilitado", False)
    agente = CWVConsolidadorAgent.__new__(CWVConsolidadorAgent)
    # Mock invoke_structured para detectar chamada.
    chamado = []
    agente.invoke_structured = lambda *a, **kw: chamado.append(1) or None
    grupos = [
        {"grupo_id": 1, "chave": "kb-a", "titulo": "A", "severidade": 3, "metricas_afetadas": ["LCP"], "urls": ["x"], "estrategias": ["mobile"], "problemas_ids": ["p1"]},
        {"grupo_id": 2, "chave": "kb-b", "titulo": "B", "severidade": 3, "metricas_afetadas": ["LCP"], "urls": ["y"], "estrategias": ["mobile"], "problemas_ids": ["p2"]},
    ]
    result = await agente.consolidar(grupos)
    assert chamado == []  # LLM nunca chamado
    assert len(result) == 2  # tudo determinístico
