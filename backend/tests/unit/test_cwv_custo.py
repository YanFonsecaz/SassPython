from app.services.ferramenta_service import (
    CUSTO_BASE_CWV,
    CUSTO_MAX_CWV,
    CUSTO_POR_URL_CWV,
    calcular_custo_cwv,
)


def test_custo_1_url():
    assert calcular_custo_cwv(1) == CUSTO_BASE_CWV + CUSTO_POR_URL_CWV


def test_custo_5_urls():
    assert calcular_custo_cwv(5) == CUSTO_BASE_CWV + 5 * CUSTO_POR_URL_CWV


def test_custo_0_urls():
    assert calcular_custo_cwv(0) == CUSTO_BASE_CWV


def test_custo_nao_ultrapassa_maximo():
    assert calcular_custo_cwv(1000) == CUSTO_MAX_CWV


def test_custo_no_limite():
    n = CUSTO_MAX_CWV - CUSTO_BASE_CWV
    assert calcular_custo_cwv(n) == CUSTO_MAX_CWV


def test_custo_abaixo_do_limite():
    n = CUSTO_MAX_CWV - CUSTO_BASE_CWV - 1
    assert calcular_custo_cwv(n) == CUSTO_BASE_CWV + n * CUSTO_POR_URL_CWV


def test_custos_tabela_contem_cwv():
    from app.services.ferramenta_service import CUSTOS_TABELA

    acoes = [c["acao"] for c in CUSTOS_TABELA]
    assert "cwv_base" in acoes
    assert "cwv_por_url" in acoes
