from app.services.cwv_kb import (
    AUDIT_ALIASES,
    AUDITS_IGNORADOS,
    BaseKB,
    EntradaKB,
    buscar_entrada,
    carregar_kb,
    listar_kb_codigos,
    listar_kb_codigos_descritos,
    mapeamento_audit_kb,
    mapeamento_audit_kb_com_aliases,
    recarregar_kb,
)


def test_carregar_kb_arquivo_real():
    kb = carregar_kb()
    assert isinstance(kb, BaseKB)
    assert len(kb.entradas) >= 20


def test_entradas_têm_codigo_titulo():
    kb = carregar_kb()
    for e in kb.entradas:
        assert e.codigo
        assert len(e.titulo) >= 5
        assert 1 <= e.severidade <= 5
        assert len(e.metricas_afetadas) >= 1
        assert "geral" in e.solucoes


def test_codigos_unicos():
    kb = carregar_kb()
    codigos = [e.codigo for e in kb.entradas]
    assert len(codigos) == len(set(codigos))


def test_buscar_entrada_existente():
    kb = carregar_kb()
    primeiro = kb.entradas[0].codigo
    resultado = buscar_entrada(primeiro)
    assert resultado is not None
    assert resultado["codigo"] == primeiro


def test_buscar_entrada_inexistente():
    assert buscar_entrada("codigo-inexistente-xyz") is None


def test_listar_kb_codigos_retorna_lista():
    codigos = listar_kb_codigos()
    assert isinstance(codigos, list)
    assert len(codigos) >= 20
    assert "codigo" in codigos[0]
    assert "titulo" in codigos[0]
    assert "metricas_afetadas" in codigos[0]


def test_mapeamento_audit_kb_retorna_dict():
    mapa = mapeamento_audit_kb()
    assert isinstance(mapa, dict)
    assert len(mapa) >= 10
    for audit_id, codigo in mapa.items():
        assert isinstance(audit_id, str)
        assert isinstance(codigo, str)


def test_mapeamento_audit_kb_audit_conhecido():
    mapa = mapeamento_audit_kb()
    assert "largest-contentful-paint-element" in mapa
    assert mapa["largest-contentful-paint-element"] == "lcp-imagem-grande"


def test_recarregar_kb():
    kb1 = carregar_kb()
    recarregar_kb()
    kb2 = carregar_kb()
    assert len(kb1.entradas) == len(kb2.entradas)


def test_entrada_kb_sem_geral_falha_validacao():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EntradaKB(
            codigo="teste-sem-geral",
            titulo="Teste sem solução geral",
            severidade=3,
            metricas_afetadas=["LCP"],
            descricao="Descrição de teste com tamanho mínimo válido",
            solucoes={"vtex": "Use o componente X"},
        )


def test_total_entradas_minimo_40():
    kb = carregar_kb()
    assert len(kb.entradas) >= 40


def test_audits_ignorados_is_set():
    assert isinstance(AUDITS_IGNORADOS, set)
    assert len(AUDITS_IGNORADOS) >= 10


def test_audits_ignorados_contem_aggregates():
    assert "metrics" in AUDITS_IGNORADOS
    assert "diagnostics" in AUDITS_IGNORADOS
    assert "main-thread-tasks" in AUDITS_IGNORADOS
    assert "network-requests" in AUDITS_IGNORADOS
    assert "final-screenshot" in AUDITS_IGNORADOS


def test_listar_kb_codigos_descritos_retorna_descricao():
    descritos = listar_kb_codigos_descritos()
    assert len(descritos) >= 40
    for d in descritos:
        assert "codigo" in d
        assert "titulo" in d
        assert "descricao_curta" in d
        assert "metricas_afetadas" in d
        assert len(d["descricao_curta"]) <= 80


def test_new_kb_entries_existem():
    kb = carregar_kb()
    codes = {e.codigo for e in kb.entradas}
    esperados = [
        "js-duplicado",
        "bf-cache-nao-elegivel",
        "imagens-formato-moderno",
        "imagens-tamanho-correto",
        "imagens-offscreen",
        "prioridade-recursos",
        "animacoes-nao-compositadas",
        "dom-profundidade-alta",
        "servidor-tempo-resposta-lento",
        "recurso-render-blocking-extra",
        "eficiente-conteudo-animado",
        "https-redirecionamento",
        "performance-budget",
        "service-worker-sem-estrategia-cache",
    ]
    for c in esperados:
        assert c in codes, f"Missing KB entry: {c}"


def test_new_entries_have_audits_lighthouse():
    kb = carregar_kb()
    new_codes = {
        "js-duplicado",
        "bf-cache-nao-elegivel",
        "imagens-formato-moderno",
        "imagens-tamanho-correto",
        "imagens-offscreen",
        "prioridade-recursos",
        "servidor-tempo-resposta-lento",
    }
    for e in kb.entradas:
        if e.codigo in new_codes:
            assert len(e.audits_lighthouse) >= 1, f"{e.codigo} has no audits_lighthouse"


def test_audit_aliases_is_dict():
    assert isinstance(AUDIT_ALIASES, dict)
    assert len(AUDIT_ALIASES) >= 5
    for alias, clasico in AUDIT_ALIASES.items():
        assert isinstance(alias, str) and len(alias) >= 3
        assert isinstance(clasico, str) and len(clasico) >= 3
        assert alias != clasico


def test_audit_aliases_known_mappings():
    assert "cache-insight" in AUDIT_ALIASES
    assert AUDIT_ALIASES["cache-insight"] == "uses-long-cache-ttl"
    assert "render-blocking-insight" in AUDIT_ALIASES
    assert AUDIT_ALIASES["render-blocking-insight"] == "render-blocking-resources"


def test_mapeamento_audit_kb_com_aliases_includes_base():
    base = mapeamento_audit_kb()
    com_alias = mapeamento_audit_kb_com_aliases()
    for audit, codigo in base.items():
        assert com_alias[audit] == codigo


def test_mapeamento_audit_kb_com_aliases_resolves_aliases():
    com_alias = mapeamento_audit_kb_com_aliases()
    for alias, clasico in AUDIT_ALIASES.items():
        base = mapeamento_audit_kb()
        if clasico in base:
            assert alias in com_alias
            assert com_alias[alias] == base[clasico]


def test_mapeamento_audit_kb_com_aliases_more_than_base():
    base = mapeamento_audit_kb()
    com_alias = mapeamento_audit_kb_com_aliases()
    assert len(com_alias) >= len(base)


def test_metric_info_entries_exist():
    kb = carregar_kb()
    codes = {e.codigo for e in kb.entradas}
    metric_info = [
        "metrica-lcp-info",
        "metrica-fcp-info",
        "metrica-tti-info",
        "metrica-si-info",
        "metrica-inp-info",
    ]
    for c in metric_info:
        assert c in codes, f"Missing metric-info KB entry: {c}"


def test_metric_info_entries_have_audits():
    kb = carregar_kb()
    for e in kb.entradas:
        if e.codigo.startswith("metrica-") and e.codigo.endswith("-info"):
            assert len(e.audits_lighthouse) >= 1, f"{e.codigo} has no audits_lighthouse"
            assert 1 <= e.severidade <= 2, f"{e.codigo} should have low severity as result metric"
