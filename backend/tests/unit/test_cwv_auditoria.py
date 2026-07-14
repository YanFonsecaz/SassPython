"""Testes da auditoria CWV (SPEC_CWV_Auditoria_Ciclo_De_Vida).

Testa funções puras do service (chave_problema, avancar_fase). A geração do
checklist (gerar_checklist) depende de DB — coberta por teste E2E manual.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.cwv_auditoria_service import ORDEM_FASES, avancar_fase, chave_problema


def test_chave_problema_prioridade_kb_codigo():
    p = {"kb_codigo": "lcp-imagem-grande", "audit_id": "x", "titulo": "t"}
    assert chave_problema(p) == "lcp-imagem-grande"


def test_chave_problema_fallback_audit_id():
    p = {"kb_codigo": None, "audit_id": "unused-javascript", "titulo": "t"}
    assert chave_problema(p) == "audit:unused-javascript"


def test_chave_problema_fallback_titulo():
    p = {"kb_codigo": None, "audit_id": None, "titulo": "Sem mapeamento"}
    assert chave_problema(p) == "titulo:Sem mapeamento"


def test_chave_problema_aceita_objeto_orm():
    p = MagicMock()
    p.kb_codigo = "js-bundle-grande"
    p.audit_id = None
    p.titulo = "Bundle"
    assert chave_problema(p) == "js-bundle-grande"


def _mock_auditoria(fase: str) -> MagicMock:
    a = MagicMock()
    a.fase = fase
    return a


def test_avancar_fase_cadeia_valida():
    a = _mock_auditoria("before")
    avancar_fase(a, "aguardando_implementacao")
    assert a.fase == "aguardando_implementacao"

    a2 = _mock_auditoria("aguardando_implementacao")
    avancar_fase(a2, "after")
    assert a2.fase == "after"

    a3 = _mock_auditoria("after")
    avancar_fase(a3, "concluida")
    assert a3.fase == "concluida"


def test_avancar_fase_pulo_invalido_levanta_value_error():
    a = _mock_auditoria("before")
    with pytest.raises(ValueError, match="Transição inválida"):
        avancar_fase(a, "after")  # before -> after (pula aguardar)


def test_avancar_fase_fase_invalida_levanta_value_error():
    a = _mock_auditoria("before")
    with pytest.raises(ValueError, match="Fase inválida"):
        avancar_fase(a, "inexistente")


def test_avancar_fase_voltar_levanta_value_error():
    a = _mock_auditoria("after")
    with pytest.raises(ValueError, match="Transição inválida"):
        avancar_fase(a, "before")  # não pode voltar


def test_ordem_fases_completa():
    assert ORDEM_FASES == ("before", "aguardando_implementacao", "after", "concluida")
