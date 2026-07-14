"""Testes do export consolidado da execução (SPEC_CWV_Export_Consolidado_Execucao).

HTML puro, sem DB — fixtures dict (padrão do test_cwv_export.py).
"""
from app.services.cwv_export import chave_problema, relatorio_execucao_para_html


def _analise(url, estrategia, problemas=None, status="sucesso", score=80, erro_msg=""):
    return {
        "url_canonica": url,
        "url": url,
        "estrategia": estrategia,
        "status": status,
        "score_performance": score,
        "lcp_ms": 2500,
        "cls": 0.05,
        "inp_ms": 200,
        "template_tipo": "home",
        "plataforma_detectada": "wordpress",
        "erro_msg": erro_msg,
        "problemas": problemas or [],
    }


def _problema(titulo, kb_codigo=None, audit_id=None, severidade=3):
    return {
        "titulo": titulo,
        "kb_codigo": kb_codigo,
        "audit_id": audit_id,
        "severidade": severidade,
        "metricas_afetadas": ["LCP"],
        "contexto_especifico": {},
        "documentacao_md": "",
    }


def _execucao(health_score=None):
    resultado_json = {}
    if health_score is not None:
        resultado_json["health_score"] = {"health_score": health_score, "n_pass": 170, "n_total": 200}
    return {"id": "exec-1", "criado_em": "2026-07-14T00:00:00", "resultado_json": resultado_json}


def test_capa_e_sumario_com_3_urls_6_linhas():
    analises = [
        _analise("https://a.com/", "mobile"),
        _analise("https://a.com/", "desktop"),
        _analise("https://b.com/", "mobile"),
        _analise("https://b.com/", "desktop"),
        _analise("https://c.com/", "mobile"),
        _analise("https://c.com/", "desktop"),
    ]
    html = relatorio_execucao_para_html(_execucao(), analises, cliente_nome="Cliente X")
    assert "Auditoria Core Web Vitals — Cliente X" in html
    assert "Sumario comparativo" in html
    # 6 linhas de sumário (uma por análise de sucesso).
    assert html.count("<tr>") >= 7  # 1 header + 6 dados
    # 3 capítulos (3 URLs distintas).
    assert html.count("<h2>https://a.com/") + html.count("<h2>https://b.com/") + html.count("<h2>https://c.com/") == 3


def test_dedup_mobile_desktop_mesmos_problemas_nota_identidade():
    probs = [_problema("Imagem grande", kb_codigo="lcp-imagem-grande")]
    analises = [
        _analise("https://a.com/", "mobile", probs),
        _analise("https://a.com/", "desktop", probs),
    ]
    html = relatorio_execucao_para_html(_execucao(), analises)
    assert "ocorrem de forma idêntica em Desktop e Mobile" in html
    # O problema é renderizado 1x (não 2x).
    assert html.count("Imagem grande") == 1


def test_mobile_desktop_problemas_diferentes_subsecoes_separadas():
    probs_mobile = [_problema("Prob mobile", kb_codigo="lcp-imagem-grande")]
    probs_desktop = [_problema("Prob desktop", kb_codigo="js-bundle-grande")]
    analises = [
        _analise("https://a.com/", "mobile", probs_mobile),
        _analise("https://a.com/", "desktop", probs_desktop),
    ]
    html = relatorio_execucao_para_html(_execucao(), analises)
    # Não tem nota de identidade (conjuntos diferentes).
    assert "idêntica" not in html
    assert "Prob mobile" in html
    assert "Prob desktop" in html


def test_mais_de_15_problemos_trunca_com_linha_e_mais():
    probs = [_problema(f"Problema {i}", kb_codigo=f"kb-{i}") for i in range(20)]
    analises = [_analise("https://a.com/", "mobile", probs)]
    html = relatorio_execucao_para_html(_execucao(), analises)
    assert "e mais 5 problema(s)" in html
    # 15 problemas documentados.
    count_problemas = sum(1 for i in range(20) if f"Problema {i}" in html)
    assert count_problemas == 15


def test_analise_falhada_aparece_no_apendice():
    analises = [
        _analise("https://a.com/", "mobile", status="sucesso"),
        _analise("https://b.com/", "mobile", status="falhou_psi", erro_msg="PSI indisponivel"),
    ]
    html = relatorio_execucao_para_html(_execucao(), analises)
    assert "Apêndice" in html or "Apéndice" in html or "nao analisadas" in html.lower()
    assert "PSI indisponivel" in html


def test_health_score_na_capa_quando_presente():
    analises = [_analise("https://a.com/", "mobile")]
    html = relatorio_execucao_para_html(_execucao(health_score=85.0), analises)
    assert "Health Score" in html
    assert "85.0%" in html


def test_health_score_omitido_quando_ausente():
    analises = [_analise("https://a.com/", "mobile")]
    html = relatorio_execucao_para_html(_execucao(), analises)
    assert "Health Score" not in html


def test_tabelas_via_data_causas_nunca_markdown():
    probs = [_problema("X", kb_codigo="kb-x", audit_id="long-tasks")]
    probs[0]["contexto_especifico"] = {"items": [{"url": "https://a.com/x.js", "wastedMs": 200}]}
    analises = [_analise("https://a.com/", "mobile", probs)]
    html = relatorio_execucao_para_html(_execucao(), analises)
    assert "<table data-causas" in html
    assert "| Recurso" not in html  # markdown descartado pelo parser


def test_chave_problema_prioridade_kb_codigo():
    assert chave_problema({"kb_codigo": "lcp-imagem-grande", "audit_id": "x", "titulo": "t"}) == "lcp-imagem-grande"
    assert chave_problema({"kb_codigo": None, "audit_id": "unused-javascript", "titulo": "t"}) == "audit:unused-javascript"
    assert chave_problema({"kb_codigo": None, "audit_id": None, "titulo": "Sem mapeamento"}) == "titulo:Sem mapeamento"
