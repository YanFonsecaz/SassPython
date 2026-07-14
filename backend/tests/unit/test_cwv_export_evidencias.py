"""Testes de thresholds/evidências destacadas (SPEC_CWV_Evidencias_Destacadas).

Funções puras sobre cwv_export — sem rede/DB.
"""
from app.services.cwv_export import _tabela_recursos, problema_para_html, threshold_do_audit
from app.services.cwv_kb import AUDIT_ALIASES


def test_threshold_direto():
    assert threshold_do_audit("long-tasks") == "< 100 ms por tarefa"
    assert threshold_do_audit("unused-javascript") == "desperdício < 20 KB por arquivo"


def test_threshold_alias_insight_resolvido():
    # render-blocking-insight → render-blocking-resources via AUDIT_ALIASES.
    assert threshold_do_audit("render-blocking-insight") is not None
    assert threshold_do_audit("render-blocking-insight") == "0 recursos bloqueantes"


def test_threshold_audit_desconhecido_retorna_none():
    assert threshold_do_audit("audit-muito-obscuro-xyz") is None
    assert threshold_do_audit(None) is None


def test_tabela_recursos_com_threshold_emite_meta():
    items = [
        {"url": "https://exemplo.com/a.js", "wastedMs": 350},
        {"url": "https://exemplo.com/b.js", "wastedMs": 120},
    ]
    html_saida = _tabela_recursos(items, audit_id="long-tasks")
    assert "Evidências" in html_saida
    assert "meta:" in html_saida
    # O `<` do threshold é escapeado para `&lt;` por _escape (correto em HTML).
    assert "100 ms por tarefa" in html_saida


def test_tabela_recursos_sem_threshold_nao_emite_meta():
    items = [{"url": "https://exemplo.com/a.js", "wastedMs": 350}]
    html_saida = _tabela_recursos(items, audit_id="audit-desconhecido")
    assert "meta:" not in html_saida
    assert "Evidências" not in html_saida
    # Tabela continua presente (fallback).
    assert "<table data-causas" in html_saida


def test_tabela_recursos_ordena_por_desperdicio_decrescente():
    items = [
        {"url": "https://exemplo.com/pequeno.js", "wastedMs": 50},
        {"url": "https://exemplo.com/grande.js", "wastedMs": 900},
        {"url": "https://exemplo.com/medio.js", "wastedMs": 300},
    ]
    html_saida = _tabela_recursos(items, audit_id="long-tasks")
    # grande deve aparecer antes de medio, que aparece antes de pequeno.
    pos_grande = html_saida.find("grande.js")
    pos_medio = html_saida.find("medio.js")
    pos_pequeno = html_saida.find("pequeno.js")
    assert 0 < pos_grande < pos_medio < pos_pequeno


def test_problema_sem_items_nao_tem_secao_evidencias():
    problema = {
        "titulo": "Sem items",
        "severidade": 3,
        "metricas_afetadas": ["LCP"],
        "audit_id": "long-tasks",
        "contexto_especifico": {},
        "documentacao_md": "",
    }
    html_saida = problema_para_html(problema)
    assert "Evidências" not in html_saida
    assert "meta:" not in html_saida


def test_problema_com_items_e_audit_conhecido_tem_meta():
    problema = {
        "titulo": "Long tasks",
        "severidade": 3,
        "metricas_afetadas": ["TBT"],
        "audit_id": "long-tasks",
        "contexto_especifico": {
            "items": [{"url": "https://exemplo.com/a.js", "wastedMs": 400}],
        },
        "documentacao_md": "## Solução\nFaça X",
    }
    html_saida = problema_para_html(problema)
    assert "meta:" in html_saida
    # O `<` é escapeado; validamos pelo texto não-simbólico.
    assert "100 ms por tarefa" in html_saida
    assert "Como corrigir" in html_saida


def test_todos_aliases_resolvem_sem_excecao():
    """Cobertura: nenhum audit_id mapeado em AUDIT_ALIASES quebra o lookup."""
    for alias in AUDIT_ALIASES.values():
        # Não precisa ter threshold, só não pode lançar.
        threshold_do_audit(alias)
