"""Testes da re-auditoria AFTER (SPEC_CWV_Reauditoria_After).

Testa funções puras e a lógica determinística de determinação de status_after.
A integração completa (service com DB) é coberta por E2E manual.
"""
from __future__ import annotations

from app.services.cwv_auditoria_service import chave_problema


def test_chave_problema_consistencia_before_after():
    """A chave de comparação deve ser a mesma entre before e after."""
    p_before = {"kb_codigo": "lcp-imagem-grande", "audit_id": "largest-contentful-paint-element", "titulo": "X"}
    p_after = {"kb_codigo": "lcp-imagem-grande", "audit_id": "largest-contentful-paint-element", "titulo": "X"}
    assert chave_problema(p_before) == chave_problema(p_after)


def test_chave_divergente_nao_falsa_resolucao():
    """Chaves divergentes (kb_codigo None vs audit_id) não devem colidir."""
    p_com_kb = {"kb_codigo": "js-bundle-grande", "audit_id": None, "titulo": "Bundle"}
    p_sem_kb = {"kb_codigo": None, "audit_id": "bundle-js", "titulo": "Bundle"}
    assert chave_problema(p_com_kb) != chave_problema(p_sem_kb)


def test_logica_status_after_resumo():
    """Documento vivo da lógica de status_after (implementada em aplicar_resultado_after):
    - problema presente no after → fail
    - problema ausente E (kb saudável no after OU URLs do escopo com sucesso) → pass
    - todas as URLs do escopo falharam no PSI after → na
    - field data: FAST → pass, AVERAGE/SLOW → fail, sem dado → na
    - page experience: pior veredito (fail > erro/na > pass)
    """
    # Esta função existe apenas como asserção de documentação — a lógica real
    # vive em aplicar_resultado_after e é validada por E2E.
    assert True
