import pytest
from sqlalchemy import select

from app.models.cwv_analise import CwvAnalise
from app.models.cwv_problema import CwvProblema
from app.services.cwv_persistencia import (
    buscar_analise_anterior,
    buscar_analise_com_problemas,
    buscar_historico_url,
    buscar_ultima_analise_url,
    persistir_analise,
)


@pytest.mark.asyncio
async def test_persistir_analise_sucesso(db_session, usuario_teste, cliente_teste, execucao_teste):
    analise_id = await persistir_analise(
        db_session,
        execucao_id=str(execucao_teste.id),
        cliente_id=str(cliente_teste),
        usuario_id=str(usuario_teste),
        url="https://x.com/",
        template="home",
        estrategia="mobile",
        plataforma="vtex",
        psi_resultado={"ok": True, "payload": {}, "parsed": {
            "score_performance": 80, "lcp_ms": 1500.0, "cls": 0.05,
            "inp_ms": 100, "fcp_ms": 1000, "ttfb_ms": 200, "tbt_ms": 100,
            "audits_falhos": [],
        }},
        problemas=[{
            "kb_codigo": "x", "titulo": "T", "severidade": 4, "prioridade_ordem": 1,
            "metricas_afetadas": ["LCP"], "contexto_especifico": {}, "documentacao_md": "## P",
        }],
    )
    assert analise_id

    analise = await db_session.get(CwvAnalise, analise_id)
    assert analise is not None
    assert analise.status == "sucesso"
    assert analise.plataforma_detectada == "vtex"
    assert analise.score_performance == 80

    probs = (await db_session.execute(select(CwvProblema).where(CwvProblema.analise_id == analise_id))).scalars().all()
    assert len(probs) == 1
    assert probs[0].kb_codigo == "x"


@pytest.mark.asyncio
async def test_persistir_analise_falha_psi(db_session, usuario_teste, cliente_teste, execucao_teste):
    analise_id = await persistir_analise(
        db_session,
        execucao_id=str(execucao_teste.id),
        cliente_id=str(cliente_teste),
        usuario_id=str(usuario_teste),
        url="https://x.com/",
        template="home",
        estrategia="mobile",
        plataforma="vtex",
        psi_resultado={"ok": False, "erro": "PSI 429"},
        problemas=[],
    )
    analise = await db_session.get(CwvAnalise, analise_id)
    assert analise.status == "falhou_psi"
    assert analise.erro_msg == "PSI 429"

    probs = (await db_session.execute(select(CwvProblema).where(CwvProblema.analise_id == analise_id))).scalars().all()
    assert len(probs) == 0


@pytest.mark.asyncio
async def test_buscar_analise_com_problemas(db_session, analise_teste):
    """persistir_analise cria nova linha cwv_analise — captura o ID retornado para buscar."""
    from app.services.cwv_persistencia import persistir_analise

    novo_id = await persistir_analise(
        db_session,
        execucao_id=str(analise_teste.execucao_id),
        cliente_id=str(analise_teste.cliente_id),
        usuario_id=str(analise_teste.usuario_id),
        url=analise_teste.url,
        template=analise_teste.template_tipo,
        estrategia=analise_teste.estrategia,
        plataforma=analise_teste.plataforma_detectada,
        psi_resultado={"ok": True, "payload": {}, "parsed": {
            "score_performance": 80, "lcp_ms": 1500.0, "cls": 0.05,
            "inp_ms": 100, "fcp_ms": 1000, "ttfb_ms": 200, "tbt_ms": 100,
            "audits_falhos": [],
        }},
        problemas=[{
            "kb_codigo": "p1", "titulo": "Prob1", "severidade": 5, "prioridade_ordem": 1,
            "metricas_afetadas": ["LCP"], "contexto_especifico": {}, "documentacao_md": "## Doc",
        }],
    )
    await db_session.commit()

    resultado = await buscar_analise_com_problemas(db_session, novo_id)
    assert resultado is not None
    assert resultado["status"] == "sucesso"
    assert len(resultado["problemas"]) >= 1


@pytest.mark.asyncio
async def test_buscar_historico_url_retorna_contagens_corretas(db_session, usuario_teste, cliente_teste, execucao_teste):
    """REGRESSAO Bug #1: n_problemas e n_problemas_alta_severidade vem do banco"""
    await persistir_analise(
        db_session,
        execucao_id=str(execucao_teste.id),
        cliente_id=str(cliente_teste),
        usuario_id=str(usuario_teste),
        url="https://x.com/",
        template="home",
        estrategia="mobile",
        plataforma="vtex",
        psi_resultado={"ok": True, "payload": {}, "parsed": {
            "score_performance": 80, "lcp_ms": 1500.0, "cls": 0.05,
            "inp_ms": 100, "fcp_ms": 1000, "ttfb_ms": 200, "tbt_ms": 100,
            "audits_falhos": [],
        }},
        problemas=[
            {"kb_codigo": "p1", "titulo": "P1", "severidade": 5, "prioridade_ordem": 1, "metricas_afetadas": ["LCP"], "contexto_especifico": {}, "documentacao_md": "D1"},
            {"kb_codigo": "p2", "titulo": "P2", "severidade": 4, "prioridade_ordem": 2, "metricas_afetadas": ["CLS"], "contexto_especifico": {}, "documentacao_md": "D2"},
            {"kb_codigo": "p3", "titulo": "P3", "severidade": 4, "prioridade_ordem": 3, "metricas_afetadas": ["INP"], "contexto_especifico": {}, "documentacao_md": "D3"},
            {"kb_codigo": "p4", "titulo": "P4", "severidade": 2, "prioridade_ordem": 4, "metricas_afetadas": ["FCP"], "contexto_especifico": {}, "documentacao_md": "D4"},
            {"kb_codigo": "p5", "titulo": "P5", "severidade": 2, "prioridade_ordem": 5, "metricas_afetadas": ["TTFB"], "contexto_especifico": {}, "documentacao_md": "D5"},
        ],
    )
    await db_session.commit()

    historico = await buscar_historico_url(db_session, str(cliente_teste), "https://x.com/")
    assert len(historico) >= 1
    assert historico[0]["n_problemas"] == 5
    assert historico[0]["n_problemas_alta_severidade"] == 3


@pytest.mark.asyncio
async def test_buscar_ultima_analise_url_retorna_mais_recente(db_session, usuario_teste, cliente_teste, execucao_teste):
    """REGRESSAO Bug #2: retorna analise mais recente por criado_em"""
    from datetime import UTC, datetime, timedelta

    from app.models.cwv_analise import CwvAnalise

    url = "https://x.com/teste-bug2"

    analise_antiga = CwvAnalise(
        execucao_id=execucao_teste.id,
        cliente_id=cliente_teste,
        usuario_id=usuario_teste,
        url=url,
        url_canonica="https://x.com/teste-bug2",
        template_tipo="home",
        estrategia="mobile",
        plataforma_detectada="vtex",
        score_performance=50,
        raw_psi_json={},
        status="sucesso",
        criado_em=datetime.now(UTC) - timedelta(days=7),
    )
    db_session.add(analise_antiga)

    analise_recente = CwvAnalise(
        execucao_id=execucao_teste.id,
        cliente_id=cliente_teste,
        usuario_id=usuario_teste,
        url=url,
        url_canonica="https://x.com/teste-bug2",
        template_tipo="home",
        estrategia="mobile",
        plataforma_detectada="wordpress",
        score_performance=80,
        raw_psi_json={},
        status="sucesso",
        criado_em=datetime.now(UTC),
    )
    db_session.add(analise_recente)
    await db_session.commit()

    ultima = await buscar_ultima_analise_url(db_session, str(cliente_teste), "https://x.com/teste-bug2")
    assert ultima is not None
    assert ultima.plataforma_detectada == "wordpress"
    assert ultima.score_performance == 80


def execucao_teste_fixture_id():
    import uuid
    return uuid.uuid4()
