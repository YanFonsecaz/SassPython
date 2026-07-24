"""SPEC_CWV_Contratos_JSONB_Tipados: valida que o schema pydantic aceita o
conteúdo REAL produzido pelos serviços sem descartar campos essenciais.

Diff verificado antes de ativar response_model: ``campos_retornados ⊖
campos_do_modelo = ∅`` (campos extras preservados por ``extra="allow"``).
"""
from __future__ import annotations

import pytest


def test_relatorio_json_aceita_status_gerando():
    """Estado transitório: só status presente (sem conteúdo do redator)."""
    from app.schemas.cwv_auditoria import RelatorioJsonResposta

    r = RelatorioJsonResposta(**{"status": "gerando"})
    assert r.status == "gerando"
    assert r.sumario_executivo_md is None


def test_relatorio_json_aceita_relatorio_completo_do_redator():
    """Shape exato que sai do ``redator.py::redigir``."""
    from app.schemas.cwv_auditoria import RelatorioJsonResposta

    payload = {
        "sumario_executivo_md": "Sumário...",
        "diagnostico_tecnico_md": "Diagnóstico...",
        "plano_fases": [
            {
                "titulo": "Prioridade 1 — Quick wins",
                "justificativa": "Baixo esforço.",
                "itens_codigos": ["lcp-imagem-grande", "render-blocking-resources"],
            }
        ],
        "gerado_em": "2026-07-17T00:00:00+00:00",
        "modelo": "gpt-test",
    }
    r = RelatorioJsonResposta(**payload)
    assert r.plano_fases[0].itens_codigos == ["lcp-imagem-grande", "render-blocking-resources"]
    assert r.modelo == "gpt-test"


def test_relatorio_json_aceita_falha():
    from app.schemas.cwv_auditoria import RelatorioJsonResposta

    r = RelatorioJsonResposta(**{"status": "falhou"})
    assert r.status == "falhou"
    assert r.plano_fases == []


def test_relatorio_json_preserva_campo_experimental():
    """``extra="allow"`` mantém chaves novas (forward-compat)."""
    from app.schemas.cwv_auditoria import RelatorioJsonResposta

    r = RelatorioJsonResposta(**{"status": "concluido", "versao_formato": 2})
    # Campo experimental preservado — não descartado.
    assert getattr(r, "versao_formato", None) == 2


def test_problema_consolidado_resposta_espelha_shape_do_servico():
    """Mesma estrutura que ``listar_consolidados`` monta no router."""
    from app.schemas.cwv_auditoria import ProblemaConsolidadoResposta

    payload = {
        "id": "00000000-0000-0000-0000-000000000001",
        "titulo": "Imagens LCP grandes",
        "causa_raiz": "Sem otimização",
        "kb_codigo": "lcp-imagem-grande",
        "severidade": 5,
        "prioridade_ordem": 1,
        "esforco": "medio",
        "metricas_afetadas": ["LCP"],
        "escopo_json": {"urls": ["https://a.com/"]},
        "evidencias_json": {},
        "recomendacao_md": "# Reduza o tamanho",
        "problemas_origem_ids": ["00000000-0000-0000-0000-000000000002"],
    }
    c = ProblemaConsolidadoResposta(**payload)
    assert c.kb_codigo == "lcp-imagem-grande"
    assert c.severidade == 5


def test_consolidados_resposta_valida_lista_com_status():
    from app.schemas.cwv_auditoria import ConsolidadosResposta

    payload = {
        "consolidados": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "titulo": "X",
                "causa_raiz": "raiz",
                "kb_codigo": None,
                "severidade": 3,
                "prioridade_ordem": 1,
                "esforco": None,
                "metricas_afetadas": [],
                "escopo_json": {},
                "evidencias_json": {},
                "recomendacao_md": "",
                "problemas_origem_ids": [],
            }
        ],
        "status": "concluida",
    }
    r = ConsolidadosResposta(**payload)
    assert r.status == "concluida"
    assert len(r.consolidados) == 1


def test_resultado_json_aceita_sucesso_cwv():
    """Shape do workflow.py:613 quando todas URLs tiveram sucesso."""
    from app.schemas.cwv import ResultadoJsonResposta

    payload = {
        "n_urls_analisadas": 5,
        "n_urls_falharam": 0,
        "analise_ids": ["a1", "a2"],
        "analises": [{"id": "a1", "score": 80}],
        "health_score": {
            "health_score": 75.0,
            "n_pass": 3,
            "n_total": 4,
            "por_estrategia": {"mobile": 75.0, "desktop": 80.0},
        },
    }
    r = ResultadoJsonResposta(**payload)
    assert r.n_urls_analisadas == 5
    assert r.health_score["health_score"] == 75.0


def test_resultado_json_aceita_motivo_falha_psi_total():
    """Shape do workflow.py:574 quando todas URLs falharam."""
    from app.schemas.cwv import ResultadoJsonResposta

    payload = {
        "n_urls_analisadas": 0,
        "n_urls_falharam": 5,
        "analise_ids": [],
        "analises": [],
        "health_score": None,
        "motivo_falha": "psi_total",
    }
    r = ResultadoJsonResposta(**payload)
    assert r.motivo_falha == "psi_total"
    assert r.health_score is None


def test_resultado_json_aceita_apenas_motivo_falha_saldo():
    """Shape do workflow.py:608 — só motivo_falha."""
    from app.schemas.cwv import ResultadoJsonResposta

    r = ResultadoJsonResposta(**{"motivo_falha": "saldo_insuficiente"})
    assert r.motivo_falha == "saldo_insuficiente"


def test_execucao_resposta_valida_buscar_execucao_cwv():
    """Shape exato que ``buscar_execucao_cwv`` retorna."""
    from app.schemas.cwv import ExecucaoResposta

    payload = {
        "id": "00000000-0000-0000-0000-000000000001",
        "ferramenta": "core_web_vitals",
        "status": "concluida",
        "etapa_atual": "concluida",
        "creditos_cobrados": 17,
        "resultado_json": {"motivo_falha": "saldo_insuficiente"},
        "entrada_json": {"urls_por_template": {"home": ["https://a.com/"]}},
        "erro_msg": None,
        "criado_em": "2026-07-17T00:00:00+00:00",
        "concluida_em": "2026-07-17T00:05:00+00:00",
        "cliente_id": "00000000-0000-0000-0000-000000000002",
    }
    r = ExecucaoResposta(**payload)
    assert r.resultado_json.motivo_falha == "saldo_insuficiente"
    assert r.creditos_cobrados == 17


def test_execucao_resposta_valida_com_auditoria_id_a2():
    """A2 preenche auditoria_id/auditoria_existente_id no resultado_json."""
    from app.schemas.cwv import ResultadoJsonResposta

    r = ResultadoJsonResposta(
        **{
            "n_urls_analisadas": 5,
            "n_urls_falharam": 0,
            "analise_ids": ["a1"],
            "analises": [],
            "health_score": None,
            "auditoria_id": "00000000-0000-0000-0000-0000000000aa",
        }
    )
    assert r.auditoria_id == "00000000-0000-0000-0000-0000000000aa"
    assert r.auditoria_existente_id is None
