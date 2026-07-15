"""Testes do redator de relatório executivo (SPEC_CWV_Relatorio_Executivo).

Testa o fallback determinístico e a validação de item_codigo. O LLM é mockado.
"""
from __future__ import annotations

from app.agents.cwv.redator import _fallback_deterministico


def _checklist_item(codigo, titulo, status_before="fail", esforco="medio"):
    return {"item_codigo": codigo, "titulo": titulo, "status_before": status_before, "esforco": esforco}


def test_fallback_deterministico_por_esforco():
    items = [
        _checklist_item("kb-1", "Quick win", esforco="baixo"),
        _checklist_item("kb-2", "Estrutural", esforco="medio"),
        _checklist_item("kb-3", "Refactor", esforco="alto"),
        _checklist_item("kb-4", "Outro quick", esforco="baixo"),
        _checklist_item("kb-pass", "Pass item", status_before="pass"),
    ]
    rel = _fallback_deterministico(
        codigos_validos={"kb-1", "kb-2", "kb-3", "kb-4"},
        checklist_items=items,
        motivo="teste",
    )
    assert rel["modelo"] == "fallback-deterministico"
    assert "gerado_em" in rel
    fases = rel["plano_fases"]
    assert len(fases) == 3  # baixo, medio, alto
    # Quick wins = baixo.
    quick = next(f for f in fases if "Quick wins" in f["titulo"])
    assert set(quick["itens_codigos"]) == {"kb-1", "kb-4"}
    # Pass item não entra em nenhuma fase.
    todos_codigos = {c for f in fases for c in f["itens_codigos"]}
    assert "kb-pass" not in todos_codigos


def test_fallback_sem_fails_gera_plano_vazio():
    items = [_checklist_item("kb-pass", "Pass", status_before="pass")]
    rel = _fallback_deterministico(set(), items, motivo="teste")
    assert rel["plano_fases"] == []


def test_fallback_apenas_esforco_alto():
    items = [_checklist_item("kb-1", "Refactor", esforco="alto")]
    rel = _fallback_deterministico({"kb-1"}, items, motivo="teste")
    fases = rel["plano_fases"]
    assert len(fases) == 1
    assert "refactor" in fases[0]["titulo"].lower()


def test_fallback_esforco_none_vai_para_medio():
    items = [_checklist_item("kb-1", "Sem esforço", esforco=None)]
    rel = _fallback_deterministico({"kb-1"}, items, motivo="teste")
    fases = rel["plano_fases"]
    # Vai para medio (default) — fase "Ajustes estruturais".
    medio = next(f for f in fases if "estruturais" in f["titulo"].lower())
    assert "kb-1" in medio["itens_codigos"]
