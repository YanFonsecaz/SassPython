"""Testes de calcular_health_score (função pura, sem DB).

SPEC_CWV_Health_Score.
"""
from app.services.cwv_health import calcular_health_score


def _a(estrategia, status, audits_totais, n_problemas):
    return {
        "estrategia": estrategia,
        "status": status,
        "audits_totais": audits_totais,
        "n_problemas": n_problemas,
    }


def test_lista_vazia_retorna_none():
    assert calcular_health_score([]) is None


def test_somente_falhas_retorna_none():
    analises = [
        _a("mobile", "falhou_psi", 0, 0),
        _a("desktop", "falhou_psi", 0, 0),
    ]
    assert calcular_health_score(analises) is None


def test_sucesso_com_zero_audits_retorna_none():
    # audits_totais == 0 não qualifica (denominador vazio).
    assert calcular_health_score([_a("mobile", "sucesso", 0, 0)]) is None


def test_mix_sucesso_e_falha_exclui_falha_do_denominador():
    analises = [
        _a("mobile", "sucesso", 100, 10),  # 90 pass
        _a("desktop", "falhou_psi", 0, 0),
    ]
    hs = calcular_health_score(analises)
    assert hs is not None
    assert hs["health_score"] == 90.0
    assert hs["n_pass"] == 90
    assert hs["n_total"] == 100
    # falha não qualifica mobile/desktop.
    assert hs["por_estrategia"] == {"mobile": 90.0}


def test_duas_analises_global_e_por_estrategia():
    # 90/100 mobile + 80/100 desktop → 170/200 = 85.0 global.
    analises = [
        _a("mobile", "sucesso", 100, 10),
        _a("desktop", "sucesso", 100, 20),
    ]
    hs = calcular_health_score(analises)
    assert hs is not None
    assert hs["health_score"] == 85.0
    assert hs["n_pass"] == 170
    assert hs["n_total"] == 200
    assert hs["por_estrategia"] == {"mobile": 90.0, "desktop": 80.0}


def test_problemas_maior_que_audits_clampa_em_zero():
    # Edge defensivo: n_problemas > audits_totais não pode gerar negativo.
    analises = [_a("mobile", "sucesso", 30, 50)]
    hs = calcular_health_score(analises)
    assert hs is not None
    assert hs["n_pass"] == 0
    assert hs["health_score"] == 0.0


def test_arredondamento_uma_casa():
    # 1/3 → 33.333... → 33.3
    analises = [_a("mobile", "sucesso", 3, 2)]
    hs = calcular_health_score(analises)
    assert hs is not None
    assert hs["health_score"] == 33.3


def test_por_estrategia_omite_estrategia_sem_sucesso():
    analises = [
        _a("mobile", "sucesso", 100, 0),  # 100%
        _a("desktop", "falhou_psi", 0, 0),
    ]
    hs = calcular_health_score(analises)
    assert hs is not None
    assert hs["por_estrategia"] == {"mobile": 100.0}
    assert "desktop" not in hs["por_estrategia"]
