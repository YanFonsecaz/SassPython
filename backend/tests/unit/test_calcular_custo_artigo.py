
from app.services.ferramenta_service import CUSTO_BASE, calcular_custo_final, custo_maximo_estimado


def test_custo_primeira_versao_com_imagem():
    assert calcular_custo_final(versao_atual=1, imagem_gerada=True) == 20


def test_custo_primeira_versao_sem_imagem():
    assert calcular_custo_final(versao_atual=1, imagem_gerada=False) == CUSTO_BASE


def test_custo_tres_versoes_sem_imagem():
    assert calcular_custo_final(versao_atual=3, imagem_gerada=False) == CUSTO_BASE + 2 * 3


def test_imagem_falha_nao_cobra():
    assert calcular_custo_final(versao_atual=1, imagem_gerada=False) == CUSTO_BASE


def test_custo_maximo_cobre_pior_caso():
    from app.config import settings

    teto = custo_maximo_estimado()
    pior = calcular_custo_final(
        versao_atual=settings.workflow_max_revisoes + settings.workflow_max_feedback + 1,
        imagem_gerada=True,
    )
    assert pior <= teto


def test_custo_maximo_estimado_valor_esperado():
    from app.config import settings

    teto = custo_maximo_estimado()
    esperado = CUSTO_BASE + (settings.workflow_max_revisoes + settings.workflow_max_feedback) * 3 + 5
    assert teto == esperado
