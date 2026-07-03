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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COOLDOWN = 60


async def criar_execucao_teste(usuario_id: str):
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
                    (:id, :uid, NULL, 'gerar_artigo', 0, 'executando',
                     'redigir', :entrada, NULL, NULL,
                     0, 0, :tid, NULL, :timeout, NULL)
            """),
            {
                "id": execucao_id,
                "uid": usuario_id,
                "entrada": '{"topico": "marketing digital"}',
                "tid": thread_id,
                "timeout": datetime.now(UTC) + timedelta(hours=1),
            },
        )
        await session.commit()
        logger.info(f"[OK] Execucao teste criada: {execucao_id}")
    return execucao_id


async def test_redator_agent(usuario_id: str, execucao_id: str):
    logger.info("\n=== TEST 5: RedatorAgent ===")
    from app.agents.redator import RedatorAgent

    agente = RedatorAgent(usuario_id=usuario_id)

    estado = {
        "execucao_id": execucao_id,
        "topico": "marketing digital para pequenas empresas",
        "palavra_chave_principal": "marketing digital",
        "palavras_chave_secundarias": ["redes sociais", "conteudo digital"],
        "brief": "Escreva um artigo curto sobre marketing digital. Meta: 300 palavras. Foque em 3 dicas simples.",
        "conteudos_selecionados": [],
        "meta_palavras": 300,
        "tipo_conteudo": "blog",
        "versao_atual": 0,
        "usuario_id": usuario_id,
    }

    for attempt in range(5):
        try:
            async with async_session_factory() as session:
                resultado = await agente.executar(estado, session)
                await session.commit()
            break
        except Exception as e:
            if attempt < 4:
                wait = 30 * (attempt + 1)
                logger.warning(f"Falha tentativa {attempt+1}/5, aguardando {wait}s: {str(e)[:200]}")
                await asyncio.sleep(wait)
            else:
                raise

    logger.info(f"[OK] Redator executou. Chaves: {list(resultado.keys())}")
    artigo = resultado.get("artigo", {})
    if artigo.get("conteudo_markdown"):
        n_words = len(artigo["conteudo_markdown"].split())
        logger.info(f"[OK] Conteudo: {n_words} palavras, Titulo: {artigo.get('titulo', 'N/A')}")
    return resultado


async def test_revisor_agent(usuario_id: str, execucao_id: str, artigo: dict):
    logger.info("\n=== TEST 6: RevisorAgent ===")
    from app.agents.revisor import RevisorAgent

    agente = RevisorAgent(usuario_id=usuario_id)

    estado = {
        "execucao_id": execucao_id,
        "artigo": artigo,
        "artigo_titulo": artigo.get("titulo", ""),
        "brief": "Artigo curto sobre marketing digital, 3 dicas simples",
        "meta_palavras": 300,
        "versao_atual": 1,
        "tentativas_revisao": 0,
        "usuario_id": usuario_id,
    }

    for attempt in range(5):
        try:
            async with async_session_factory() as session:
                resultado = await agente.executar(estado, session)
                await session.commit()
            break
        except Exception as e:
            if attempt < 4:
                wait = 30 * (attempt + 1)
                logger.warning(f"Falha tentativa {attempt+1}/5, aguardando {wait}s: {str(e)[:200]}")
                await asyncio.sleep(wait)
            else:
                raise

    logger.info(f"[OK] Revisor executou. Chaves: {list(resultado.keys())}")
    revisao = resultado.get("revisao", {})
    aprovado = resultado.get("aprovado_revisor", False)
    score = revisao.get("score_qualidade", 0)
    logger.info(f"[OK] Score: {score}, Aprovado: {aprovado}")
    if revisao.get("problemas"):
        logger.info(f"[OK] Problemas: {revisao['problemas'][:3]}")
    if revisao.get("checagens"):
        logger.info(f"[OK] Checagens: {revisao['checagens']}")
    return resultado


async def main():
    logger.info("=" * 60)
    logger.info("E2E TEST - RedatorAgent + RevisorAgent")
    logger.info(f"Model: {settings.llm_model}")
    logger.info(f"Cooldown: {COOLDOWN}s")
    logger.info("=" * 60)

    usuario_id = "b9afa7ad-12c7-40b8-a4a7-3d0bcd4f1f31"

    logger.info(f"[COOLDOWN INICIAL] aguardando {COOLDOWN}s para garantir rate limit reset...")
    await asyncio.sleep(COOLDOWN)

    execucao_id = await criar_execucao_teste(usuario_id)

    try:
        artigo_resultado = await test_redator_agent(usuario_id, execucao_id)
        artigo = artigo_resultado.get("artigo", {})

        logger.info(f"[COOLDOWN] aguardando {COOLDOWN}s...")
        await asyncio.sleep(COOLDOWN)

        await test_revisor_agent(usuario_id, execucao_id, artigo)

        logger.info("\n" + "=" * 60)
        logger.info("TODOS OS TESTES PASSARAM!")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"\n[FALHA] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
