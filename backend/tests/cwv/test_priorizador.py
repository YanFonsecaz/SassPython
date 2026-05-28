from app.agents.cwv.priorizador import PESO_METRICA, priorizar_problemas


def test_prioriza_por_severidade_e_metrica():
    problemas = [
        {"kb_codigo": "a", "severidade": 4, "metricas_afetadas": ["CLS"]},
        {"kb_codigo": "b", "severidade": 5, "metricas_afetadas": ["LCP"]},
        {"kb_codigo": "c", "severidade": 3, "metricas_afetadas": ["FCP"]},
    ]
    ordenados = priorizar_problemas(problemas)
    assert ordenados[0]["kb_codigo"] == "b"
    assert ordenados[1]["kb_codigo"] == "a"
    assert ordenados[2]["kb_codigo"] == "c"
    assert ordenados[0]["prioridade_ordem"] == 1
    assert ordenados[1]["prioridade_ordem"] == 2
    assert ordenados[2]["prioridade_ordem"] == 3


def test_priorizar_adiciona_ordem():
    problemas = [
        {"titulo": "X", "severidade": 1, "metricas_afetadas": ["TTFB"]},
        {"titulo": "Y", "severidade": 3, "metricas_afetadas": ["INP"]},
    ]
    resultado = priorizar_problemas(problemas)
    assert resultado[0]["prioridade_ordem"] == 1
    assert resultado[1]["prioridade_ordem"] == 2


def test_priorizar_lista_vazia():
    assert priorizar_problemas([]) == []


def test_priorizar_metricas_afetadas_vazio():
    problemas = [
        {"titulo": "Sem metricas", "severidade": 5, "metricas_afetadas": []},
        {"titulo": "Com metricas", "severidade": 3, "metricas_afetadas": ["LCP"]},
    ]
    resultado = priorizar_problemas(problemas)
    assert resultado[0]["titulo"] == "Com metricas"


def test_priorizar_mesma_severidade_desempate_por_peso():
    problemas = [
        {"titulo": "FCP", "severidade": 3, "metricas_afetadas": ["FCP"]},
        {"titulo": "LCP", "severidade": 3, "metricas_afetadas": ["LCP"]},
        {"titulo": "LCP+CLS", "severidade": 3, "metricas_afetadas": ["LCP", "CLS"]},
    ]
    resultado = priorizar_problemas(problemas)
    assert resultado[0]["titulo"] == "LCP+CLS"
    assert resultado[-1]["titulo"] == "FCP"


def test_pesos_metrica():
    assert PESO_METRICA["LCP"] == 5
    assert PESO_METRICA["CLS"] == 4
    assert PESO_METRICA["INP"] == 4
    assert PESO_METRICA["TBT"] == 3
    assert PESO_METRICA["FCP"] == 2
    assert PESO_METRICA["TTFB"] == 2
