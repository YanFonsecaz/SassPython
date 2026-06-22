"""Guarda dura anti-loop no workflow de gerar_artigo (roteamento por versao).

Garante terminacao mesmo se os contadores de tentativas divergirem
(ex.: retomada sobre checkpoint de topologia antiga / edge case de resume).
"""
from app.agents.workflow import _teto_versoes, roteamento_revisor, roteamento_usuario
from app.config import settings


def test_teto_versoes_formula():
    assert _teto_versoes() == settings.workflow_max_revisoes + settings.workflow_max_feedback + 1


def test_fluxo_normal_preservado():
    # abaixo do teto e com contadores permitindo -> continua gerando
    assert roteamento_usuario({"aprovado_usuario": False, "tentativas_feedback": 1, "versao_atual": 4}) == "redigir"
    assert roteamento_revisor({"aprovado_revisor": False, "tentativas_revisao": 1, "versao_atual": 2}) == "redigir"


def test_guarda_forca_terminacao_no_teto():
    teto = _teto_versoes()
    # no teto (ou acima), NUNCA volta para redigir — mesmo com contadores "zerados"
    assert roteamento_usuario({"aprovado_usuario": False, "tentativas_feedback": 0, "versao_atual": teto}) == "salvar_vetorial"
    assert roteamento_revisor({"aprovado_revisor": False, "tentativas_revisao": 0, "versao_atual": teto}) == "aguardar_aprovacao"
    assert roteamento_usuario({"aprovado_usuario": False, "tentativas_feedback": 0, "versao_atual": teto + 9}) == "salvar_vetorial"


def test_aprovacao_tem_prioridade_sobre_teto():
    teto = _teto_versoes()
    assert roteamento_usuario({"aprovado_usuario": True, "versao_atual": teto}) == "salvar_vetorial"
    assert roteamento_revisor({"aprovado_revisor": True, "versao_atual": 2}) == "aguardar_aprovacao"
