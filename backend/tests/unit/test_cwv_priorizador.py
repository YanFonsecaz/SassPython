from app.agents.cwv.priorizador import PESO_METRICA, estimar_esforco, priorizar_problemas
from app.services.cwv_kb import carregar_kb


def test_priorizar_ordena_por_severidade_x_peso():
    problemas = [
        {"titulo": "B", "severidade": 2, "metricas_afetadas": ["FCP"]},
        {"titulo": "A", "severidade": 5, "metricas_afetadas": ["LCP"]},
        {"titulo": "C", "severidade": 3, "metricas_afetadas": ["CLS", "INP"]},
    ]
    resultado = priorizar_problemas(problemas)
    assert [p["titulo"] for p in resultado] == ["A", "C", "B"]


def test_priorizar_adiciona_ordem():
    problemas = [
        {"titulo": "X", "severidade": 1, "metricas_afetadas": ["TTFB"]},
        {"titulo": "Y", "severidade": 3, "metricas_afetadas": ["INP"]},
    ]
    resultado = priorizar_problemas(problemas)
    assert resultado[0]["prioridade_ordem"] == 1
    assert resultado[1]["prioridade_ordem"] == 2


def test_priorizar_metricas_afetadas_vazio():
    problemas = [
        {"titulo": "Sem metricas", "severidade": 5, "metricas_afetadas": []},
        {"titulo": "Com metricas", "severidade": 3, "metricas_afetadas": ["LCP"]},
    ]
    resultado = priorizar_problemas(problemas)
    assert resultado[0]["titulo"] == "Com metricas"


def test_priorizar_lista_vazia():
    assert priorizar_problemas([]) == []


def test_priorizar_mesma_severidade_desempate_por_peso_metrica():
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


# --- SPEC_CWV_Estimador_Esforco ---------------------------------------------


def test_esforco_cobre_toda_kb():
    """Completude: todo codigo da KB tem esforco definido (guarda de mapa)."""
    kb = carregar_kb()
    faltantes = [e.codigo for e in kb.entradas if estimar_esforco(e.codigo, None) is None]
    assert not faltantes, f"Codigos KB sem esforco: {faltantes}"


def test_esforco_diretos():
    assert estimar_esforco("imagens-formato-moderno", None) == "baixo"
    assert estimar_esforco("lcp-imagem-grande", None) == "baixo"
    assert estimar_esforco("lcp-fonte-bloqueante", None) == "medio"
    assert estimar_esforco("js-bundle-grande", None) == "alto"
    assert estimar_esforco("dom-muito-grande", None) == "alto"


def test_esforco_fallback_por_familia():
    # Sem KB, mas audit_id de familia conhecida.
    assert estimar_esforco(None, "unused-javascript") == "alto"
    assert estimar_esforco(None, "modern-image-formats") == "baixo"
    assert estimar_esforco(None, "uses-long-cache-ttl") == "baixo"
    # Familia desconhecida.
    assert estimar_esforco(None, "audit-muito-obscuro-xyz") is None


def test_esforco_kb_tem_precedencia_sobre_familia():
    # kb_codigo resolve primeiro, mesmo se audit_id casasse outra familia.
    assert estimar_esforco("js-bundle-grande", "modern-image-formats") == "alto"


def test_priorizar_popula_esforco():
    problemas = [
        {"titulo": "Imagem", "severidade": 5, "metricas_afetadas": ["LCP"], "kb_codigo": "imagens-formato-moderno"},
        {"titulo": "Bundle", "severidade": 5, "metricas_afetadas": ["TBT"], "kb_codigo": "js-bundle-grande"},
        {"titulo": "Sem KB", "severidade": 3, "metricas_afetadas": ["CLS"], "kb_codigo": None, "audit_id": "unused-javascript"},
    ]
    resultado = priorizar_problemas(problemas)
    esforcos = {p["titulo"]: p["esforco"] for p in resultado}
    assert esforcos["Imagem"] == "baixo"
    assert esforcos["Bundle"] == "alto"
    assert esforcos["Sem KB"] == "alto"
