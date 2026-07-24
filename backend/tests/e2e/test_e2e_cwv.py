import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

from app.db.session import async_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

TEST_URL = "https://www.google.com/"
TEST_TEMPLATE = "home"


async def criar_cliente_e2e(usuario_id: str) -> str:
    cliente_id = str(uuid.uuid4())
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO clientes (id, usuario_id, nome, site_url, config_json, ativo) "
                "VALUES (:id, :uid, :nome, NULL, '{}', true)"
            ),
            {"id": cliente_id, "uid": usuario_id, "nome": "Cliente E2E CWV"},
        )
        await session.commit()
    logger.info("[OK] Cliente criado: %s", cliente_id)
    return cliente_id


async def cleanup(usuario_id: str, cliente_id: str):
    async with async_session_factory() as session:
        await session.execute(
            text("DELETE FROM cwv_problema WHERE analise_id IN (SELECT id FROM cwv_analise WHERE usuario_id = :uid)"),
            {"uid": usuario_id},
        )
        await session.execute(
            text("DELETE FROM cwv_analise WHERE usuario_id = :uid"),
            {"uid": usuario_id},
        )
        await session.execute(
            text("DELETE FROM execucoes_ferramentas WHERE usuario_id = :uid AND ferramenta = 'core_web_vitals'"),
            {"uid": usuario_id},
        )
        if cliente_id:
            await session.execute(
                text("DELETE FROM clientes WHERE id = :cid"),
                {"cid": cliente_id},
            )
        await session.commit()
        logger.info("[OK] Dados de teste limpos")


async def criar_execucao(usuario_id: str, cliente_id: str) -> str:
    execucao_id = str(uuid.uuid4())
    entrada = {
        "cliente_id": cliente_id,
        "urls_por_template": {TEST_TEMPLATE: [TEST_URL]},
        "estrategia": "mobile",
    }
    async with async_session_factory() as session:
        await session.execute(
            text("""
                INSERT INTO execucoes_ferramentas
                    (id, usuario_id, cliente_id, ferramenta, creditos_cobrados, status,
                     etapa_atual, entrada_json, resultado_json, erro_msg,
                     tentativas_revisao, tentativas_feedback, thread_id, job_id, timeout_em, concluida_em)
                VALUES
                    (:id, :uid, :cid, 'core_web_vitals', 0, 'pendente',
                     NULL, :entrada, NULL, NULL,
                     0, 0, :tid, NULL, :timeout, NULL)
            """),
            {
                "id": execucao_id,
                "uid": usuario_id,
                "cid": cliente_id,
                "entrada": json.dumps(entrada),
                "tid": str(uuid.uuid4()),
                "timeout": datetime.now(UTC) + timedelta(hours=1),
            },
        )
        await session.commit()
    logger.info("[OK] Execucao criada: %s", execucao_id)
    return execucao_id


async def run_workflow(execucao_id: str):
    from app.agents.cwv.workflow import executar_workflow_cwv

    logger.info("[WFL] Executando workflow CWV...")
    await executar_workflow_cwv(execucao_id)
    logger.info("[WFL] Workflow concluido")


async def verify(execucao_id: str) -> bool:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                text("SELECT status, creditos_cobrados, erro_msg, resultado_json FROM execucoes_ferramentas WHERE id = :eid"),
                {"eid": execucao_id},
            )
        ).fetchone()

        if not row:
            logger.error("[FAIL] Execucao nao encontrada")
            return False

        status, creditos, erro, _resultado = row
        logger.info("[VERIFY] execucao: status=%s, creditos=%s, erro=%s", status, creditos, erro)

        if status != "concluida":
            logger.error("[FAIL] Status esperado=concluida, obtido=%s, erro=%s", status, erro)
            return False

        row_analise = (
            await session.execute(
                text("SELECT id, url_canonica, score_performance, lcp_ms, cls, inp_ms, status FROM cwv_analise WHERE execucao_id = :eid"),
                {"eid": execucao_id},
            )
        ).fetchall()

        if not row_analise:
            logger.error("[FAIL] Nenhuma analise persistida")
            return False

        for a in row_analise:
            logger.info(
                "[VERIFY] analise: id=%s, url=%s, score=%s, lcp=%s, cls=%s, inp=%s, status=%s",
                a[0][:8], a[1], a[2], a[3], a[4], a[5], a[6],
            )

        row_probs = (
            await session.execute(
                text("SELECT COUNT(*) FROM cwv_problema WHERE analise_id IN (SELECT id FROM cwv_analise WHERE execucao_id = :eid)"),
                {"eid": execucao_id},
            )
        ).fetchone()

        n_problemas = row_probs[0] if row_probs else 0
        logger.info("[VERIFY] problemas persistidos: %d", n_problemas)

        logger.info("[OK] Verificacao passou")
        return True


async def verify_api_analise(execucao_id: str, usuario_id: str):
    from app.services.cwv_persistencia import buscar_analise_com_problemas, listar_historico_cliente

    async with async_session_factory() as session:
        row = (
            await session.execute(
                text("SELECT id FROM cwv_analise WHERE execucao_id = :eid LIMIT 1"),
                {"eid": execucao_id},
            )
        ).fetchone()

        if not row:
            logger.warning("[SKIP] verify_api_analise: sem analise")
            return True

        analise_id = str(row[0])

        analise = await buscar_analise_com_problemas(session, analise_id)
        assert analise is not None, "buscar_analise_com_problemas retornou None"
        assert analise["url_canonica"], "url_canonica vazio"
        assert analise["usuario_id"] == usuario_id, "usuario_id mismatch"
        assert "problemas" in analise
        logger.info("[VERIFY API] analise OK: url=%s, score=%s, %d problemas", analise["url_canonica"], analise["score_performance"], len(analise["problemas"]))

        historico, total = await listar_historico_cliente(session, analise["cliente_id"])
        assert len(historico) >= 1, "historico vazio"
        assert historico[0]["analises"], "historico sem analises"
        assert total >= 1, "total vazio"
        logger.info("[VERIFY API] historico OK: %d URLs (total=%d)", len(historico), total)

    return True


async def main():
    logger.info("=" * 60)
    logger.info("E2E TEST - Core Web Vitals Workflow")
    logger.info("URL: %s", TEST_URL)
    logger.info("=" * 60)

    usuario_id = "b9afa7ad-12c7-40b8-a4a7-3d0bcd4f1f31"
    cliente_id = None

    try:
        await cleanup(usuario_id, "")
        cliente_id = await criar_cliente_e2e(usuario_id)

        execucao_id = await criar_execucao(usuario_id, cliente_id)

        logger.info("[RUN] Iniciando workflow...")
        await run_workflow(execucao_id)

        ok = await verify(execucao_id)
        if ok:
            await verify_api_analise(execucao_id, usuario_id)

        logger.info("\n" + "=" * 60)
        if ok:
            logger.info("CWV E2E PASSOU!")
        else:
            logger.error("CWV E2E FALHOU")
            sys.exit(1)
        logger.info("=" * 60)
    except Exception as e:
        logger.error("[FALHA] %s: %s", type(e).__name__, e)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await cleanup(usuario_id, cliente_id)


if __name__ == "__main__":
    asyncio.run(main())
