"""SPEC_CWV_Cache_Classificacao_Audit_KB: cache determinístico.

Cobre:
- Helpers do cache (buscar/salvar/invalidar/invalidar_cobertos_por_direto/listar).
- Integração no analisador: cache hit → 0 chamadas LLM; miss → classifica +
  grava no cache; próxima análise com mesmo audit_id → 0 chamadas.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- Service: helpers ---------------------------------------------------------


def _make_cache_row(audit_id: str, kb_codigo: str | None, origem: str = "llm"):
    row = MagicMock()
    row.audit_id = audit_id
    row.kb_codigo = kb_codigo
    row.origem = origem
    row.modelo = "gpt-test"
    row.criado_em = None
    row.atualizado_em = None
    return row


@pytest.mark.asyncio
async def test_buscar_classificacoes_vazio_retorna_dict_vazio():
    from app.services.cwv_audit_kb_cache import buscar_classificacoes

    db = MagicMock()
    db.execute = AsyncMock()
    assert await buscar_classificacoes(db, []) == {}
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_buscar_classificacoes_retorna_mapa_audiid_kb():
    from app.services.cwv_audit_kb_cache import buscar_classificacoes

    resultado = MagicMock()
    resultado.all.return_value = [("audit-a", "kb-1"), ("audit-b", None)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=resultado)

    mapa = await buscar_classificacoes(db, ["audit-a", "audit-b", "audit-c"])
    assert mapa == {"audit-a": "kb-1", "audit-b": None}
    # audit-c não veio da resposta → não está no cache (LLM deve classificar).
    assert "audit-c" not in mapa


@pytest.mark.asyncio
async def test_salvar_classificacao_executa_upsert():
    from app.services.cwv_audit_kb_cache import salvar_classificacao

    db = MagicMock()
    db.execute = AsyncMock()
    await salvar_classificacao(
        db, audit_id="audit-x", kb_codigo="kb-y", origem="llm", modelo="gpt-test"
    )
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalidar_retorna_true_se_removeu():
    from app.services.cwv_audit_kb_cache import invalidar

    res = MagicMock()
    res.rowcount = 1
    db = MagicMock()
    db.execute = AsyncMock(return_value=res)
    assert await invalidar(db, "audit-x") is True


@pytest.mark.asyncio
async def test_invalidar_retorna_false_se_nada_removido():
    from app.services.cwv_audit_kb_cache import invalidar

    res = MagicMock()
    res.rowcount = 0
    db = MagicMock()
    db.execute = AsyncMock(return_value=res)
    assert await invalidar(db, "audit-x") is False


@pytest.mark.asyncio
async def test_invalidar_cobertos_por_direto_deleta_somente_os_passados():
    from app.services.cwv_audit_kb_cache import invalidar_cobertos_por_direto

    res = MagicMock()
    res.rowcount = 3
    db = MagicMock()
    db.execute = AsyncMock(return_value=res)
    n = await invalidar_cobertos_por_direto(db, {"a1": "kb1", "a2": "kb2", "a3": "kb3"})
    assert n == 3


@pytest.mark.asyncio
async def test_invalidar_cobertos_por_direto_vazio_nao_chama_db():
    from app.services.cwv_audit_kb_cache import invalidar_cobertos_por_direto

    db = MagicMock()
    db.execute = AsyncMock()
    assert await invalidar_cobertos_por_direto(db, {}) == 0
    db.execute.assert_not_awaited()


# --- Analisador: integração com cache ----------------------------------------


class _StubListaProblemas:
    def __init__(self, problemas):
        self.problemas = problemas


@pytest.mark.asyncio
async def test_analisador_cache_hit_nao_chama_llm(monkeypatch):
    """Audits residual no cache: 0 chamadas LLM, kb_codigo do cache."""
    from app.agents.cwv import analisador
    from app.agents.cwv.analisador import ProblemaIdentificado

    agente = analisador.CWVAnalisadorAgent.__new__(analisador.CWVAnalisadorAgent)
    # invoke_structured NUNCA deve ser chamado neste teste.
    agente.invoke_structured = AsyncMock(
        side_effect=AssertionError("LLM chamado em cache hit")
    )
    agente._modelo_nome = lambda: "test-model"

    audits = [
        {"id": "audit-unknown-1", "title": "X", "description": "d", "details": {}},
    ]

    cache_map = {"audit-unknown-1": "kb-cached-1"}

    db = MagicMock()
    with patch(
        "app.services.cwv_audit_kb_cache.buscar_classificacoes",
        new=AsyncMock(return_value=cache_map),
    ):
        problemas, stats = await agente.analisar(
            audits_falhos=audits,
            plataforma="wordpress",
            metricas={"lcp_ms": 1},
            db=db,
        )

    assert stats["llm_usado"] is False
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 0
    assert problemas[0]["kb_codigo"] == "kb-cached-1"


@pytest.mark.asyncio
async def test_analisador_cache_miss_chama_llm_e_grava():
    from app.agents.cwv import analisador
    from app.agents.cwv.analisador import ListaProblemas, ProblemaIdentificado

    agente = analisador.CWVAnalisadorAgent.__new__(analisador.CWVAnalisadorAgent)
    salvar_calls: list[dict] = []

    async def _salvar(db, *, audit_id, kb_codigo, origem="llm", modelo=None):
        salvar_calls.append(
            {"audit_id": audit_id, "kb_codigo": kb_codigo, "origem": origem, "modelo": modelo}
        )

    agente.invoke_structured = AsyncMock(
        return_value=ListaProblemas(
            problemas=[
                ProblemaIdentificado(
                    kb_codigo="lcp-imagem-grande",
                    audit_id="audit-new",
                    contexto_especifico={},
                    audits_origem=["audit-new"],
                )
            ]
        )
    )
    agente._modelo_nome = lambda: "test-model"

    db = MagicMock()
    with (
        patch(
            "app.services.cwv_audit_kb_cache.buscar_classificacoes",
            new=AsyncMock(return_value={}),  # cache vazio → miss total.
        ),
        patch("app.services.cwv_audit_kb_cache.salvar_classificacao", new=_salvar),
    ):
        problemas, stats = await agente.analisar(
            audits_falhos=[{"id": "audit-new", "title": "T", "description": "d", "details": {}}],
            plataforma="wordpress",
            metricas={"lcp_ms": 1},
            db=db,
        )

    assert stats["llm_usado"] is True
    assert stats["cache_misses"] == 1
    assert stats["cache_hits"] == 0
    assert any(c["audit_id"] == "audit-new" and c["kb_codigo"] == "lcp-imagem-grande" for c in salvar_calls)


@pytest.mark.asyncio
async def test_analisador_cache_none_pula_llm():
    """Entrada no cache com kb_codigo=None = catalogada como 'sem KB' — usa direto."""
    from app.agents.cwv import analisador

    agente = analisador.CWVAnalisadorAgent.__new__(analisador.CWVAnalisadorAgent)
    agente.invoke_structured = AsyncMock(
        side_effect=AssertionError("LLM chamado para audit cacheado como null")
    )
    agente._modelo_nome = lambda: "test-model"

    db = MagicMock()
    with patch(
        "app.services.cwv_audit_kb_cache.buscar_classificacoes",
        new=AsyncMock(return_value={"audit-sem-kb": None}),
    ):
        problemas, stats = await agente.analisar(
            audits_falhos=[{"id": "audit-sem-kb", "title": "T", "details": {}}],
            plataforma="geral",
            metricas={},
            db=db,
        )

    assert stats["llm_usado"] is False
    assert problemas[0]["kb_codigo"] is None
    assert problemas[0]["audit_id"] == "audit-sem-kb"


@pytest.mark.asyncio
async def test_analisador_sem_db_mantem_comportamento_legado():
    """db=None (fallback): todos residuals vão pro LLM como antes (sem gravar)."""
    from app.agents.cwv import analisador
    from app.agents.cwv.analisador import ListaProblemas, ProblemaIdentificado

    agente = analisador.CWVAnalisadorAgent.__new__(analisador.CWVAnalisadorAgent)
    agente.invoke_structured = AsyncMock(
        return_value=ListaProblemas(
            problemas=[
                ProblemaIdentificado(
                    kb_codigo="kb-x", audit_id="audit-x", audits_origem=["audit-x"],
                )
            ]
        )
    )
    agente._modelo_nome = lambda: "test-model"

    problemas, stats = await agente.analisar(
        audits_falhos=[{"id": "audit-x", "title": "T", "details": {}}],
        plataforma="geral",
        metricas={},
        db=None,
    )
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 1
    assert stats["llm_usado"] is True
