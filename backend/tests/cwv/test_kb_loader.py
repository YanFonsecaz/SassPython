from app.services.cwv_kb import (
    BaseKB,
    buscar_entrada,
    carregar_kb,
    listar_kb_codigos,
    mapeamento_audit_kb,
)


def test_kb_carrega_sem_erros():
    kb = carregar_kb()
    assert isinstance(kb, BaseKB)
    assert len(kb.entradas) >= 30


def test_kb_codigos_unicos():
    kb = carregar_kb()
    codigos = [e.codigo for e in kb.entradas]
    assert len(codigos) == len(set(codigos))


def test_kb_solucao_geral_obrigatoria():
    kb = carregar_kb()
    for e in kb.entradas:
        assert "geral" in e.solucoes, f"{e.codigo} sem solucao geral"


def test_kb_mapeamento_audit_kb_cobre_audits_principais():
    mapa = mapeamento_audit_kb()
    obrigatorios = [
        "largest-contentful-paint-element",
        "unsized-images",
        "lcp-lazy-loaded",
        "cumulative-layout-shift",
        "total-blocking-time",
    ]
    for audit in obrigatorios:
        assert audit in mapa, f"Audit {audit} sem mapeamento na KB"


def test_kb_buscar_entrada_inexistente_retorna_none():
    assert buscar_entrada("codigo-que-nao-existe-xyz") is None


def test_kb_buscar_entrada_existente():
    kb = carregar_kb()
    primeiro = kb.entradas[0].codigo
    resultado = buscar_entrada(primeiro)
    assert resultado is not None
    assert resultado["codigo"] == primeiro


def test_kb_listar_codigos():
    codigos = listar_kb_codigos()
    assert isinstance(codigos, list)
    assert len(codigos) >= 30
    assert "codigo" in codigos[0]
    assert "titulo" in codigos[0]
    assert "metricas_afetadas" in codigos[0]


def test_kb_mapeamento_audit_kb_retorna_dict():
    mapa = mapeamento_audit_kb()
    assert isinstance(mapa, dict)
    assert len(mapa) >= 10
