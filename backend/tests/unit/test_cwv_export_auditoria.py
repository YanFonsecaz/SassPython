"""Testes do export DOCX da auditoria (SPEC_CWV_Relatorio_Executivo).

HTML puro com fixtures dict (padrão do test_cwv_export.py).
"""
from app.services.cwv_export import relatorio_auditoria_para_html


def _auditoria(relatorio_json=None, health_before=75.0, health_after=None):
    return {
        "criado_em": "2026-07-14T00:00:00",
        "fase": "after",
        "health_score_before": health_before,
        "health_score_after": health_after,
        "relatorio_json": relatorio_json or {},
    }


def _checklist_item(codigo, titulo, status_before="fail", esforco="medio"):
    return {"item_codigo": codigo, "titulo": titulo, "status_before": status_before,
            "status_after": "pass", "status_implementacao": "implementado",
            "prioridade": 1, "esforco": esforco}


def _consolidado(titulo="Render blocking", causa_raiz="Bundle", esforco="medio"):
    return {
        "titulo": titulo, "causa_raiz": causa_raiz, "esforco": esforco,
        "escopo_json": {"urls": ["https://a.com/", "https://b.com/"], "estrategias": ["mobile", "desktop"], "descricao": "Produto e home"},
        "recomendacao_md": "Otimize o bundle.",
    }


def test_export_com_relatorio_narrativo_tem_todas_secoes():
    rel = {
        "sumario_executivo_md": "Site com LCP alto.",
        "diagnostico_tecnico_md": "Bundle de 900KB bloqueia render.",
        "plano_fases": [
            {"titulo": "Fase 1", "justificativa": "Quick wins", "itens_codigos": ["kb-1"]},
        ],
    }
    html = relatorio_auditoria_para_html(
        auditoria=_auditoria(relatorio_json=rel, health_after=85.0),
        checklist=[_checklist_item("kb-1", "Render blocking")],
        consolidados=[_consolidado()],
        page_experience=[{"origem": "https://a.com", "https": "pass", "ssl": "pass", "redirect_301": "pass",
                          "security_headers": "fail", "mixed_content": "pass", "mobile_friendly": "pass"}],
        analises=[{"url_canonica": "https://a.com/", "estrategia": "mobile",
                   "crux_lcp_p75_ms": 2200, "crux_cls_p75": 0.04, "crux_inp_p75_ms": 150,
                   "crux_overall_categoria": "AVERAGE", "field_data_disponivel": True}],
        cliente_nome="Cliente X",
    )
    # 8 seções presentes (capa + sumário + checklist + CrUX + PE + consolidado + faseado + diagnóstico).
    assert "Auditoria Core Web Vitals — Cliente X" in html
    assert "Sumário executivo" in html
    assert "Checklist" in html
    assert "Dados de campo (CrUX)" in html
    assert "Page Experience" in html
    assert "Plano de ação consolidado" in html
    assert "Plano faseado" in html
    assert "Diagnóstico técnico" in html
    # Delta de health.
    assert "75.0%" in html
    assert "85.0%" in html


def test_export_sem_relatorio_omite_secoes_narrativas():
    html = relatorio_auditoria_para_html(
        auditoria=_auditoria(),
        checklist=[_checklist_item("kb-1", "Render blocking")],
        consolidados=[_consolidado()],
        page_experience=[],
        analises=[],
    )
    # Dados estruturais presentes.
    assert "Checklist" in html
    assert "Plano de ação consolidado" in html
    # Seções narrativas (LLM) ausentes.
    assert "Sumário executivo" not in html
    assert "Diagnóstico técnico" not in html
    assert "Plano faseado" not in html


def test_export_tabelas_via_data_causas():
    html = relatorio_auditoria_para_html(
        auditoria=_auditoria(),
        checklist=[_checklist_item("kb-1", "X")],
        consolidados=[],
        page_experience=[],
        analises=[],
    )
    assert "<table data-causas" in html
    assert "| Item" not in html  # sem markdown


def test_export_consolidado_com_documentacao_rende_como_corrigir():
    consolidado = {**_consolidado(), "documentacao_md": "## Passo a passo\nUse `defer`."}
    html = relatorio_auditoria_para_html(
        auditoria=_auditoria(),
        checklist=[],
        consolidados=[consolidado],
        page_experience=[],
        analises=[],
    )
    assert "Como corrigir" in html
    assert "defer" in html


def test_export_apendice_por_url_com_problemas():
    analise = {
        "url_canonica": "https://a.com/produto",
        "estrategia": "mobile",
        "status": "sucesso",
        "problemas": [{
            "titulo": "JS não usado",
            "severidade": 4,
            "metricas_afetadas": ["LCP"],
            "contexto_especifico": {"display_value": "300 KB"},
        }],
    }
    html = relatorio_auditoria_para_html(
        auditoria=_auditoria(),
        checklist=[],
        consolidados=[],
        page_experience=[],
        analises=[analise],
    )
    assert "Apêndice — problemas por URL" in html
    assert "https://a.com/produto" in html
    assert "JS não usado" in html


def test_export_apendice_ausente_sem_problemas():
    html = relatorio_auditoria_para_html(
        auditoria=_auditoria(),
        checklist=[_checklist_item("kb-1", "X")],
        consolidados=[],
        page_experience=[],
        analises=[{"url_canonica": "https://a.com/", "estrategia": "mobile", "status": "falhou"}],
    )
    assert "Apêndice — problemas por URL" not in html


def test_export_sem_checklist_sem_consolidados_minimo():
    html = relatorio_auditoria_para_html(
        auditoria=_auditoria(),
        checklist=[],
        consolidados=[],
        page_experience=[],
        analises=[],
    )
    # Só a capa.
    assert "Auditoria Core Web Vitals" in html
    assert "<table" not in html
