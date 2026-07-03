"""Regressões dos 4 bugs encontrados no E2E de 2026-05-28.

Cada teste falha sem o fix correspondente. Adicionar novo teste aqui sempre
que um bug for descoberto em produção/staging para evitar reintroducao.
"""


def test_bug1_node_pesquisar_outros_usa_variavel_correta():
    """Bug: workflow.py:183 referenciava `outros` (nome antigo) em vez de `sem_kb`.
    NameError so disparava em runtime quando havia problemas sem KB.
    """
    import inspect

    from app.agents.cwv import workflow

    src = inspect.getsource(workflow.node_pesquisar_outros)
    assert "len(outros)" not in src, "Workflow ainda usa variavel 'outros' inexistente"
    assert "len(sem_kb)" in src or "sem_kb" in src


def test_bug2_problema_comparado_aceita_kb_codigo_nulo():
    """Bug: ProblemaComparado.kb_codigo: str quebrava com null pos SPEC #17."""
    from app.schemas.cwv import ProblemaComparado

    obj = ProblemaComparado(kb_codigo=None, titulo="Audit pesquisado sem KB")
    assert obj.kb_codigo is None
    assert obj.titulo == "Audit pesquisado sem KB"


def test_bug3_diff_distingue_problemas_pesquisados_diferentes():
    """Bug: diff colapsava todos kb_codigo=None em um unico item.
    Solucao: usar audit_id como chave de fallback.
    """
    from types import SimpleNamespace

    def _chave(p):
        if p.kb_codigo:
            return p.kb_codigo
        if p.audit_id:
            return f"audit:{p.audit_id}"
        return f"titulo:{p.titulo}"

    p1 = SimpleNamespace(kb_codigo=None, audit_id="forced-reflow-insight", titulo="A")
    p2 = SimpleNamespace(kb_codigo=None, audit_id="network-dependency-tree-insight", titulo="B")

    chaves = {_chave(p1), _chave(p2)}
    assert len(chaves) == 2, "Diff colapsando audits diferentes em um unico item"


def test_bug5_resumir_items_ignora_itens_nao_dict():
    """Bug encontrado no E2E Magalu 2026-05-28: alguns audits retornam items que sao
    strings/numeros (ex: network-rtt). _resumir_items quebrava com AttributeError.
    """
    from app.agents.cwv.analisador import _resumir_items

    items_mistos = [
        {"url": "https://x.com/a.js", "totalBytes": 1000},
        "string-solta",
        123,
        None,
        {"url": "https://y.com/b.js", "totalBytes": 2000},
    ]
    resumo = _resumir_items(items_mistos)
    assert len(resumo) == 2
    assert resumo[0]["url"] == "https://x.com/a.js"
    assert resumo[1]["url"] == "https://y.com/b.js"


def test_bug4_psi_client_preserva_metric_savings_e_numeric_value():
    """Bug: cwv_psi_client criava dict reduzido que perdia metricSavings/numericValue/warnings."""
    from app.services.cwv_psi_client import parse_psi

    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.5}},
            "finalUrl": "https://example.com/",
            "audits": {
                "unused-javascript": {
                    "id": "unused-javascript",
                    "title": "Reduce unused JS",
                    "description": "...",
                    "score": 0.3,
                    "scoreDisplayMode": "numeric",
                    "displayValue": "Est savings of 500 KiB",
                    "numericValue": 500000,
                    "numericUnit": "byte",
                    "metricSavings": {"LCP": 1200, "FCP": 800},
                    "warnings": ["aviso 1"],
                    "details": {"type": "opportunity", "items": [], "overallSavingsBytes": 500000},
                },
                "largest-contentful-paint": {"id": "lcp", "score": 0.95, "numericValue": 3500},
            },
        }
    }

    parsed = parse_psi(payload)
    audits_falhos = parsed["audits_falhos"]
    assert len(audits_falhos) == 1
    audit = audits_falhos[0]
    assert audit["metricSavings"] == {"LCP": 1200, "FCP": 800}, "metricSavings foi descartado"
    assert audit["numericValue"] == 500000
    assert audit["numericUnit"] == "byte"
    assert audit["warnings"] == ["aviso 1"]
    assert audit["scoreDisplayMode"] == "numeric"
