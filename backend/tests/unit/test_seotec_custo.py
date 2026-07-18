from app.services.ferramenta_service import calcular_custo_seo_tecnico


def test_custo_por_fase():
    assert calcular_custo_seo_tecnico("before") == 30
    assert calcular_custo_seo_tecnico("after") == 15
