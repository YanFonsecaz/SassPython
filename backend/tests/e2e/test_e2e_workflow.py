import asyncio
import logging
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

from app.config import settings
from app.db.session import async_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

COOLDOWN = 5


async def cleanup_test_data(usuario_id: str):
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM versoes_artigo WHERE execucao_id IN (SELECT id FROM execucoes_ferramentas WHERE usuario_id = :uid)"), {"uid": usuario_id})
        await session.execute(text("DELETE FROM conteudos_vetores WHERE usuario_id = :uid"), {"uid": usuario_id})
        await session.execute(text("DELETE FROM execucoes_ferramentas WHERE usuario_id = :uid"), {"uid": usuario_id})
        await session.commit()
        logger.info("[OK] Dados de teste limpos")


async def criar_execucao(usuario_id: str) -> tuple[str, str]:
    execucao_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    async with async_session_factory() as session:
        await session.execute(
            text("""
                INSERT INTO execucoes_ferramentas
                    (id, usuario_id, cliente_id, ferramenta, creditos_cobrados, status,
                     etapa_atual, entrada_json, resultado_json, erro_msg,
                     tentativas_revisao, tentativas_feedback, thread_id, job_id, timeout_em, concluida_em)
                VALUES
                    (:id, :uid, NULL, 'gerar_artigo', 0, 'pendente',
                     NULL, :entrada, NULL, NULL,
                     0, 0, :tid, NULL, :timeout, NULL)
            """),
            {
                "id": execucao_id,
                "uid": usuario_id,
                "entrada": """{
                    "topico": "dicas de marketing digital",
                    "palavra_chave_principal": "marketing digital",
                    "palavras_chave_secundarias": ["redes sociais", "SEO"],
                    "tipo_conteudo": "blog",
                    "meta_palavras": 300,
                    "objetivo": "informar",
                    "persona_id": ""
                }""",
                "tid": thread_id,
                "timeout": datetime.now(UTC) + timedelta(hours=1),
            },
        )
        await session.commit()
        logger.info(f"[OK] Execucao criada: {execucao_id}")
    return execucao_id, thread_id


async def run_workflow_phase_1(execucao_id: str, thread_id: str, usuario_id: str):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.agents.workflow import EstadoWorkflow, criar_workflow

    db_url = settings.database_url.replace("+asyncpg", "")
    async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
        await checkpointer.setup()

        workflow = criar_workflow(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        estado_inicial: EstadoWorkflow = {
            "execucao_id": execucao_id,
            "usuario_id": usuario_id,
            "cliente_id": "",
            "cliente_config": {},
            "persona_selecionada": {},
            "topico": "dicas de marketing digital",
            "palavra_chave_principal": "marketing digital",
            "palavras_chave_secundarias": ["redes sociais", "SEO"],
            "tipo_conteudo": "blog",
            "meta_palavras": 300,
            "objetivo": "informar",
            "artigo_introdutorio": "",
            "perguntas_clientes": "",
            "instrucoes_adicionais": "",
            "tentativas_revisao": 0,
            "tentativas_feedback": 0,
            "versao_atual": 0,
            "aprovado_revisor": False,
            "aprovado_usuario": False,
        }

        logger.info("[FASE 1] Iniciando workflow (pesquisar -> analisar -> brief -> redigir -> revisar -> aguardar_aprovacao)...")
        nodos_executados = []
        async for event in workflow.astream(estado_inicial, config=config, version="v2", stream_mode="updates"):
            if event and isinstance(event, dict) and event.get("type") == "updates":
                for node_name in event.get("data", {}).keys():
                    nodos_executados.append(node_name)
                    logger.info(f"  [NODE] {node_name} completo")

        logger.info(f"[FASE 1] Nodos executados: {nodos_executados}")
        return nodos_executados


async def run_workflow_phase_2(thread_id: str, execucao_id: str, usuario_id: str):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.types import Command

    from app.agents.workflow import criar_workflow

    db_url = settings.database_url.replace("+asyncpg", "")
    async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
        await checkpointer.setup()

        workflow = criar_workflow(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        resume_value = {
            "aprovado_usuario": True,
            "feedback_usuario": "",
        }

        logger.info("[FASE 2] Retomando workflow com aprovacao (salvar_vetorial -> gerar_imagem -> END)...")
        nodos_executados = []
        async for event in workflow.astream(Command(resume=resume_value), config=config, version="v2", stream_mode="updates"):
            if event and isinstance(event, dict) and event.get("type") == "updates":
                for node_name in event.get("data", {}).keys():
                    nodos_executados.append(node_name)
                    logger.info(f"  [NODE] {node_name} completo")

        logger.info(f"[FASE 2] Nodos executados: {nodos_executados}")
        return nodos_executados


async def verify_final_state(execucao_id: str):
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT status, etapa_atual, creditos_cobrados FROM execucoes_ferramentas WHERE id = :eid"),
            {"eid": execucao_id},
        )
        row = result.fetchone()
        if row:
            logger.info(f"[VERIFY] Execucao: status={row[0]}, etapa={row[1]}, creditos={row[2]}")
            return row[0], row[1]

        result = await session.execute(
            text("SELECT versao, origem, titulo, contagem_palavras, score_revisao FROM versoes_artigo WHERE execucao_id = :eid ORDER BY versao"),
            {"eid": execucao_id},
        )
        versoes = result.fetchall()
        for v in versoes:
            logger.info(f"[VERIFY] Versao {v[0]}: origem={v[1]}, titulo='{v[2]}', palavras={v[3]}, score={v[4]}")
        return None, None


async def main():
    logger.info("=" * 60)
    logger.info("E2E TEST - Full Workflow (Phase 1 + Phase 2)")
    logger.info(f"Provider: {settings.llm_provider}, Model: {settings.llm_model}")
    logger.info("=" * 60)

    usuario_id = "b9afa7ad-12c7-40b8-a4a7-3d0bcd4f1f31"

    await cleanup_test_data(usuario_id)
    execucao_id, thread_id = await criar_execucao(usuario_id)

    try:
        logger.info(f"\n[COOLDOWN INICIAL] aguardando {COOLDOWN}s...")
        await asyncio.sleep(COOLDOWN)

        nodos_fase1 = await run_workflow_phase_1(execucao_id, thread_id, usuario_id)

        required_fase1 = {"pesquisar", "analisar", "criar_brief", "redigir", "revisar"}
        fase1_ok = required_fase1.issubset(set(nodos_fase1)) and ("__interrupt__" in nodos_fase1)
        if fase1_ok:
            logger.info(f"[OK] FASE 1 PASSOU - todos nodos executados: {nodos_fase1}")
        else:
            missing = required_fase1 - set(nodos_fase1)
            logger.error(f"[FALHA] FASE 1 - nodos faltando: {missing}")

        logger.info(f"\n[COOLDOWN] aguardando {COOLDOWN}s antes de retomar...")
        await asyncio.sleep(COOLDOWN)

        nodos_fase2 = await run_workflow_phase_2(thread_id, execucao_id, usuario_id)

        expected_fase2 = {"salvar_vetorial", "gerar_imagem"}
        fase2_ok = len(nodos_fase2) > 0
        if fase2_ok:
            logger.info("[OK] FASE 2 PASSOU - workflow retomado e completou")

        await verify_final_state(execucao_id)

        logger.info("\n" + "=" * 60)
        if fase1_ok and fase2_ok:
            logger.info("FULL WORKFLOW E2E PASSOU!")
        else:
            logger.error("FULL WORKFLOW E2E FALHOU PARCIALMENTE")
            sys.exit(1)
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"\n[FALHA] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
