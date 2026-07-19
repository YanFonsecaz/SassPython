from types import SimpleNamespace

from app.services.ferramenta_service import _obter_reserva_estimada, calcular_custo_seo_tecnico


def test_custo_por_fase():
    assert calcular_custo_seo_tecnico("before") == 30
    assert calcular_custo_seo_tecnico("after") == 15


# --- Cancelamento genérico não deve vazar créditos reservados (SPEC_Ferramenta_Auditoria_SEO_Tecnico) ---

def _exec_seotec(fase_destino):
    return SimpleNamespace(entrada_json={"fase_destino": fase_destino})


def test_reserva_estimada_seotec_before():
    assert _obter_reserva_estimada("auditoria_seo_tecnico", _exec_seotec("before")) == 30


def test_reserva_estimada_seotec_after():
    assert _obter_reserva_estimada("auditoria_seo_tecnico", _exec_seotec("after")) == 15
