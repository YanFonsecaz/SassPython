"""SPEC_Inlinks_Badges_Pela_Decisao_Do_Juiz — teste do mapeamento categoria x decisão.

A categoria da badge agora deriva de (status, confiança) — não mais de cortes de
cosine. Cobre os 5 casos da tabela da spec + CTA + caminho legado.
"""

import pytest

from app.agents.inlinks.injector import _categoria_match, _categoria_match_por_decisao


@pytest.mark.parametrize(
    "status, confianca, esperado",
    [
        ("aplicado", 0.95, "alta_similaridade"),
        ("aplicado", 0.85, "alta_similaridade"),  # limiar inclusivo
        ("aplicado", 0.78, "boa_similaridade"),
        ("aplicado", 0.70, "boa_similaridade"),  # limiar inclusivo
        ("aplicado", 0.55, "complemento_contextual"),
        ("aplicado", None, "complemento_contextual"),  # sem confiança → pede revisão
        ("sugestao_manual", 0.99, "similaridade_media"),
        ("rejeitado", 0.99, "similaridade_media"),
    ],
)
def test_categoria_por_decisao(status, confianca, esperado):
    assert _categoria_match_por_decisao(status, confianca) == esperado


def test_categoria_cta_fallback_e_sempre_boa_similaridade():
    """CTA é link deliberado (não inferido) — sempre conexão sólida, independente da confiança."""
    assert _categoria_match_por_decisao("aplicado", 0.30, cta=True) == "boa_similaridade"
    assert _categoria_match_por_decisao("aplicado", 0.99, cta=True) == "boa_similaridade"


def test_categoria_legado_continua_por_cosine():
    """O caminho legado (aplicar_pisos_legado=True) mantém _categoria_match por cosine."""
    assert _categoria_match(0.85, 0.5, 0.7) == "alta_similaridade"
    assert _categoria_match(0.50, 0.65, 0.60) == "complemento_contextual"
    assert _categoria_match(0.40, 0.40, 0.40) == "similaridade_media"


def test_coerencia_badge_confianca_nao_contradiz():
    """Regra de produto: 'IA 90%' nunca ao lado de 'Conexão fraca'."""
    alta = _categoria_match_por_decisao("aplicado", 0.90)
    assert alta != "similaridade_media"
    assert alta == "alta_similaridade"
