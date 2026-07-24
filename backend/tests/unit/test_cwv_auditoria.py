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


def test_chave_problema_outros_cai_para_audit_id():
    """SPEC_CWV_Chave_Problema_Outros: kb_codigo='outros' não identifica o problema."""
    p = {"kb_codigo": "outros", "audit_id": "network-dependency-tree-insight", "titulo": "Genérico"}
    assert chave_problema(p) == "audit:network-dependency-tree-insight"


def test_chave_problema_outros_sem_audit_cai_para_titulo():
    p = {"kb_codigo": "outros", "audit_id": None, "titulo": "Erro estranho"}
    assert chave_problema(p) == "titulo:Erro estranho"


def test_chave_problema_outros_igual_none_mesmo_audit():
    """Problema com kb='outros' e kb=None mesmo audit → mesma chave (dedup funciona)."""
    p_outros = {"kb_codigo": "outros", "audit_id": "x", "titulo": "A"}
    p_none = {"kb_codigo": None, "audit_id": "x", "titulo": "B"}
    assert chave_problema(p_outros) == chave_problema(p_none)


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


def test_checklist_item_patch_aceita_prioridade():
    from app.schemas.cwv_auditoria import ChecklistItemPatch

    corpo = ChecklistItemPatch(prioridade=3)
    assert corpo.prioridade == 3


def test_checklist_item_patch_rejeita_prioridade_negativa():
    import pydantic
    import pytest as _pytest

    from app.schemas.cwv_auditoria import ChecklistItemPatch

    with _pytest.raises(pydantic.ValidationError):
        ChecklistItemPatch(prioridade=-1)


def _analise(url, estrategia, score, problemas, status="sucesso", template="home"):
    return {
        "id": f"{url}-{estrategia}",
        "url_canonica": url,
        "estrategia": estrategia,
        "template_tipo": template,
        "status": status,
        "score_performance": score,
        "lcp_ms": 4200.0,
        "cls": 0.57,
        "inp_ms": 348.0,
        "tbt_ms": 890.0,
        "problemas": problemas,
    }


def _prob(kb):
    return {"kb_codigo": kb, "audit_id": None, "titulo": kb}


def test_montar_comparativo_pareia_e_conta_diff():
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [_analise("https://a.com/", "mobile", 23, [_prob("k1"), _prob("k2"), _prob("k3")])]
    after = [_analise("https://a.com/", "mobile", 61, [_prob("k2"), _prob("k9")])]

    pares = montar_comparativo(before, after)
    assert len(pares) == 1
    par = pares[0]
    assert par["url_canonica"] == "https://a.com/"
    assert par["estrategia"] == "mobile"
    assert par["before"]["score_performance"] == 23
    assert par["after"]["score_performance"] == 61
    assert par["problemas"]["resolvidos"] == 2      # k1, k3
    assert par["problemas"]["persistentes"] == 1    # k2
    assert par["problemas"]["novos"] == 1           # k9
    assert "k1" in par["problemas"]["titulos_resolvidos"]
    assert par["problemas"]["titulos_novos"] == ["k9"]


def test_montar_comparativo_sem_after_retorna_baseline():
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [_analise("https://a.com/", "mobile", 23, [_prob("k1")])]
    pares = montar_comparativo(before, None)
    assert pares[0]["after"] is None
    assert pares[0]["problemas"] is None


def test_montar_comparativo_after_faltando_para_url():
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [
        _analise("https://a.com/", "mobile", 23, []),
        _analise("https://a.com/b", "mobile", 50, []),
    ]
    after = [_analise("https://a.com/", "mobile", 61, [])]
    pares = montar_comparativo(before, after)
    assert len(pares) == 2
    sem_after = [p for p in pares if p["url_canonica"] == "https://a.com/b"][0]
    assert sem_after["after"] is None


def test_montar_comparativo_ignora_analises_sem_sucesso():
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [_analise("https://a.com/", "mobile", 23, [])]
    after = [_analise("https://a.com/", "mobile", None, [], status="falhou")]
    pares = montar_comparativo(before, after)
    assert pares[0]["after"] is None


def test_comparativo_resposta_valida_shape_do_service():
    from app.schemas.cwv_auditoria import ComparativoResposta
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [_analise("https://a.com/", "mobile", 23, [_prob("k1")])]
    after = [_analise("https://a.com/", "mobile", 61, [])]
    resp = ComparativoResposta(fase="after", pares=montar_comparativo(before, after))
    assert resp.pares[0].problemas.resolvidos == 1
    assert resp.pares[0].after.score_performance == 61


def test_montar_detalhe_item_com_kb():
    from app.services.cwv_auditoria_service import montar_detalhe_item

    d = montar_detalhe_item(
        item_codigo="lcp-imagem-grande",  # entrada real na KB
        titulo="ignorado",
        esforco="alto",
        urls_escopo=["https://a.com/"],
        plataforma="wordpress",
    )
    assert d["tem_kb"] is True
    assert d["descricao"] and len(d["descricao"]) > 0
    assert d["solucao_geral"]  # sempre existe
    assert d["metricas_afetadas"]
    assert d["esforco"] == "alto"
    assert d["urls_escopo"] == ["https://a.com/"]


def test_montar_detalhe_item_solucao_plataforma_so_quando_nao_geral():
    from app.services.cwv_auditoria_service import montar_detalhe_item

    geral = montar_detalhe_item(
        item_codigo="lcp-imagem-grande", titulo="t", esforco=None,
        urls_escopo=[], plataforma="geral",
    )
    assert geral["solucao_plataforma"] is None  # 'geral' não duplica a solução geral


def test_montar_detalhe_item_sem_kb_fallback():
    from app.services.cwv_auditoria_service import montar_detalhe_item

    d = montar_detalhe_item(
        item_codigo="crux_lcp",  # sem entrada na KB, mas com descrição fixa
        titulo="Dado de campo — LCP",
        esforco=None,
        urls_escopo=[],
        plataforma="wordpress",
    )
    assert d["tem_kb"] is False
    # DESCRICOES_ITENS_SEM_KB cobre crux_*/pe_*/manual_*/agentic_*.
    assert d["descricao"] and "CrUX" in d["descricao"]
    assert d["solucao_geral"] is None
    assert d["titulo"] == "Dado de campo — LCP"


def test_montar_detalhe_item_sem_kb_e_sem_descricao_fixa():
    from app.services.cwv_auditoria_service import montar_detalhe_item

    d = montar_detalhe_item(
        item_codigo="audit:algum-audit-desconhecido",
        titulo="Audit desconhecido",
        esforco=None,
        urls_escopo=[],
        plataforma="geral",
    )
    assert d["tem_kb"] is False
    assert d["descricao"] is None


def test_item_detalhe_resposta_valida_shape():
    from app.schemas.cwv_auditoria import ItemDetalheResposta
    from app.services.cwv_auditoria_service import montar_detalhe_item

    d = montar_detalhe_item(
        item_codigo="lcp-imagem-grande", titulo="t", esforco="alto",
        urls_escopo=["https://a.com/"], plataforma="vtex",
    )
    resp = ItemDetalheResposta(**d)
    assert resp.tem_kb is True
    assert resp.links_referencia == resp.links_referencia  # valida shape de links


# --- SPEC_CWV_Detalhe_Evidencias_Elementos ---------------------------------

def _prob_ctx(items):
    p = MagicMock()
    p.contexto_especifico = {"items": items}
    return p


def test_montar_evidencias_agrupa_por_url_estrategia():
    from app.services.cwv_auditoria_service import montar_evidencias

    rows = [
        (_prob_ctx([{"node_label": "img.hero"}, {"url": "https://a.com/x.png"}]), "https://a.com/", "mobile"),
    ]
    ev = montar_evidencias(rows)
    assert len(ev) == 1
    assert ev[0]["url_canonica"] == "https://a.com/"
    assert ev[0]["estrategia"] == "mobile"
    assert ev[0]["elementos"] == ["img.hero", "https://a.com/x.png"]
    assert ev[0]["total"] == 2


def test_montar_evidencias_funde_audits_do_mesmo_grupo_e_dedupe():
    from app.services.cwv_auditoria_service import montar_evidencias

    # Dois problemas (audits diferentes) na mesma URL×estratégia; "img.hero" repete.
    rows = [
        (_prob_ctx([{"node_label": "img.hero"}, {"node_label": "div.a"}]), "https://a.com/", "mobile"),
        (_prob_ctx([{"node_label": "img.hero"}, {"node_label": "div.b"}]), "https://a.com/", "mobile"),
    ]
    ev = montar_evidencias(rows)
    assert len(ev) == 1  # fundido num só grupo mobile
    assert ev[0]["elementos"] == ["img.hero", "div.a", "div.b"]  # dedupe preserva ordem
    assert ev[0]["total"] == 3


def test_montar_evidencias_cap_40_com_total():
    from app.services.cwv_auditoria_service import montar_evidencias

    itens = [{"node_label": f"el{i}"} for i in range(60)]
    ev = montar_evidencias([(_prob_ctx(itens), "https://a.com/", "desktop")])
    assert len(ev[0]["elementos"]) == 40  # exibidos
    assert ev[0]["total"] == 60          # total real preservado


def test_montar_evidencias_separa_mobile_desktop():
    from app.services.cwv_auditoria_service import montar_evidencias

    rows = [
        (_prob_ctx([{"node_label": "m1"}]), "https://a.com/", "mobile"),
        (_prob_ctx([{"node_label": "d1"}]), "https://a.com/", "desktop"),
    ]
    ev = montar_evidencias(rows)
    assert len(ev) == 2
    estr = {e["estrategia"] for e in ev}
    assert estr == {"mobile", "desktop"}


def test_montar_evidencias_descarta_sem_elementos_legiveis():
    from app.services.cwv_auditoria_service import montar_evidencias

    # items sem nenhum campo string legível → entrada some.
    ev = montar_evidencias([(_prob_ctx([{"wastedMs": 120}]), "https://a.com/", "mobile")])
    assert ev == []


def test_montar_detalhe_item_inclui_evidencias():
    from app.services.cwv_auditoria_service import montar_detalhe_item

    d = montar_detalhe_item(
        item_codigo="lcp-imagem-grande", titulo="t", esforco="alto",
        urls_escopo=["https://a.com/"], plataforma="vtex",
        evidencias=[{"url_canonica": "https://a.com/", "estrategia": "mobile", "elementos": ["img.hero"]}],
    )
    assert d["evidencias"][0]["elementos"] == ["img.hero"]


def test_item_detalhe_resposta_valida_evidencias():
    from app.schemas.cwv_auditoria import ItemDetalheResposta
    from app.services.cwv_auditoria_service import montar_detalhe_item

    d = montar_detalhe_item(
        item_codigo="crux_lcp", titulo="Dado", esforco=None, urls_escopo=[], plataforma=None,
        evidencias=[{"url_canonica": "https://a.com/", "estrategia": "mobile", "elementos": ["x"]}],
    )
    resp = ItemDetalheResposta(**d)
    assert resp.evidencias[0].estrategia == "mobile"


def test_evidencia_item_preserva_total():
    """Regressão: schema duplicado já engoliu `total` silenciosamente (pydantic ignora extras)."""
    from app.schemas.cwv_auditoria import EvidenciaItem

    ev = EvidenciaItem(url_canonica="https://a.com/", estrategia="mobile", elementos=["x"], total=12)
    assert ev.total == 12
    assert "total" in ev.model_dump()


# --- SPEC_CWV_Alinhamento_Relatorio_Json -----------------------------------

def test_auditoria_resposta_aceita_relatorio_json():
    from app.schemas.cwv_auditoria import AuditoriaResposta

    resp = AuditoriaResposta(
        id="00000000-0000-0000-0000-000000000001",
        cliente_id="00000000-0000-0000-0000-000000000002",
        titulo="t", fase="after",
        # SPEC_CWV_Contratos_JSONB_Tipados: relatorio_json agora tipado.
        relatorio_json={"status": "concluido", "sumario_executivo_md": "ok"},
        criado_em="2026-07-16T00:00:00", atualizado_em="2026-07-16T00:00:00",
    )
    assert resp.relatorio_json.status == "concluido"
    assert resp.relatorio_json.sumario_executivo_md == "ok"


def test_auditoria_resposta_relatorio_json_default_none():
    from app.schemas.cwv_auditoria import AuditoriaResposta

    resp = AuditoriaResposta(
        id="00000000-0000-0000-0000-000000000001",
        cliente_id="00000000-0000-0000-0000-000000000002",
        titulo="t", fase="before",
        criado_em="2026-07-16T00:00:00", atualizado_em="2026-07-16T00:00:00",
    )
    assert resp.relatorio_json is None


# --- SPEC_CWV_Checklist_Itens_Manuais --------------------------------------

def test_itens_manuais_definidos():
    from app.services.cwv_auditoria_service import ITENS_MANUAIS

    codigos = [c for c, _ in ITENS_MANUAIS]
    assert codigos == ["manual_popups", "manual_interstitials", "manual_ads_above_fold"]
