import asyncio
import sys
import os
import uuid
from datetime import date, timedelta, datetime, timezone
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argon2
import jwt
from sqlalchemy import text

from app.config import settings
from app.db.session import async_session_factory
from app.core.seguranca import gerar_jwt_access_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_EMAIL = "teste_e2e@seo-saas.local"
TEST_PASSWORD = "SenhaTesteE2E!2024#Segura"
COOLDOWN = 45


async def criar_test_usuario_e_creditos():
    ph = argon2.PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, salt_len=16, hash_len=32, type=argon2.Type.ID)
    senha_hash = ph.hash(TEST_PASSWORD)
    usuario_id = str(uuid.uuid4())

    async with async_session_factory() as session:
        result = await session.execute(text("SELECT id FROM usuarios WHERE email = :email"), {"email": TEST_EMAIL})
        existing = result.scalar_one_or_none()

        if existing:
            usuario_id = str(existing)
            logger.info(f"[OK] Usuario ja existe: {usuario_id}")
        else:
            await session.execute(
                text("""
                    INSERT INTO usuarios (id, email, nome, senha_hash, email_verificado, ativo)
                    VALUES (:id, :email, :nome, :senha_hash, true, true)
                """),
                {"id": usuario_id, "email": TEST_EMAIL, "nome": "Usuario Teste E2E", "senha_hash": senha_hash},
            )
            await session.commit()
            logger.info(f"[OK] Usuario criado: {usuario_id}")

        result = await session.execute(text("SELECT id FROM contas_creditos WHERE usuario_id = :uid"), {"uid": usuario_id})
        if not result.scalar_one_or_none():
            hoje = date.today()
            await session.execute(
                text("""
                    INSERT INTO contas_creditos (id, usuario_id, saldo_plano, saldo_extras, ciclo_inicio, ciclo_fim)
                    VALUES (:id, :uid, 100, 50, :inicio, :fim)
                """),
                {"id": str(uuid.uuid4()), "uid": usuario_id, "inicio": hoje, "fim": hoje + timedelta(days=30)},
            )
            await session.commit()
            logger.info(f"[OK] Conta credito criada: 100 plano + 50 extras")

    return usuario_id


def gerar_jwt(usuario_id: str):
    token = gerar_jwt_access_token(usuario_id, TEST_EMAIL, False)
    logger.info(f"[OK] JWT gerado (tipo=access, exp=900s)")
    return token


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
                "entrada": '{"topico": "marketing digital para pequenas empresas"}',
                "tid": thread_id,
                "timeout": datetime.now(timezone.utc) + timedelta(hours=1),
            },
        )
        await session.commit()
        logger.info(f"[OK] Execucao teste criada: {execucao_id}")
    return execucao_id


async def test_base_agent_llm(usuario_id: str):
    logger.info("\n=== TEST 1: BaseAgent LLM Call ===")
    from app.agents.base import BaseAgent

    agent = BaseAgent(usuario_id=usuario_id)
    logger.info(f"[OK] BaseAgent criado (model={settings.llm_model})")

    from langchain_core.prompts import ChatPromptTemplate
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Responda em portugues com no maximo 2 frases."),
        ("human", "O que e SEO?"),
    ])
    chain = prompt | agent.llm
    for attempt in range(5):
        try:
            resultado = await agent.invoke(chain, {"input": "O que e SEO?"})
            logger.info(f"[OK] LLM respondeu: {resultado}")
            return True
        except Exception as e:
            if "429" in str(e) and attempt < 4:
                wait = 15 * (attempt + 1)
                logger.warning(f"Rate limit (429), aguardando {wait}s... tentativa {attempt+1}/5")
                await asyncio.sleep(wait)
            else:
                raise


async def test_pesquisador_agent(usuario_id: str):
    logger.info("\n=== TEST 2: PesquisadorAgent ===")
    from app.agents.pesquisador import PesquisadorAgent

    agente = PesquisadorAgent(usuario_id=usuario_id)
    logger.info(f"[OK] PesquisadorAgent criado")

    estado = {
        "topico": "marketing digital para pequenas empresas",
        "palavra_chave_principal": "marketing digital",
        "palavras_chave_secundarias": ["redes sociais", "conteudo digital"],
        "usuario_id": usuario_id,
    }

    async with async_session_factory() as session:
        resultado = await agente.executar(estado, session)

    insights = resultado.get("pesquisa_resultados", {}).get("insights", "")
    web_results = resultado.get("pesquisa_resultados", {}).get("resultados_web", [])
    logger.info(f"[OK] Pesquisador executado. {len(web_results)} resultados web, insights: {len(insights)} chars")
    return True


async def test_analisador_agent(usuario_id: str):
    logger.info("\n=== TEST 3: AnalisadorAgent ===")
    from app.agents.analisador import AnalisadorAgent

    agente = AnalisadorAgent(usuario_id=usuario_id)

    estado = {
        "topico": "marketing digital para pequenas empresas",
        "palavra_chave_principal": "marketing digital",
        "palavras_chave_secundarias": ["redes sociais", "conteudo digital"],
        "pesquisa_resultados": {
            "resultados_web": [
                {"titulo": "Guia de Marketing Digital", "url": "https://exemplo.com/guia", "snippet": "O marketing digital e essencial..."}
            ],
            "tendencias": [
                {"termo": "marketing automatizado", "valor": 85}
            ],
            "conteudos_vetoriais": [],
            "web_fallback": False,
            "trends_fallback": False,
            "insights": "Marketing digital e essencial para pequenas empresas.",
        },
        "usuario_id": usuario_id,
    }

    async with async_session_factory() as session:
        resultado = await agente.executar(estado, session)

    logger.info(f"[OK] Analisador executou. Chaves: {list(resultado.keys())}")
    return True


async def test_criador_brief_agent(usuario_id: str):
    logger.info("\n=== TEST 4: CriadorBriefAgent ===")
    from app.agents.criador_brief import CriadorBriefAgent

    agente = CriadorBriefAgent(usuario_id=usuario_id)

    estado = {
        "topico": "marketing digital para pequenas empresas",
        "palavra_chave_principal": "marketing digital",
        "palavras_chave_secundarias": ["redes sociais", "conteudo digital"],
        "pesquisa_resultados": {
            "resultados_web": [
                {"titulo": "Guia de Marketing Digital", "url": "https://exemplo.com/guia", "snippet": "O marketing digital e essencial..."}
            ],
            "tendencias": [{"termo": "marketing automatizado", "valor": 85}],
            "insights": "Marketing digital e essencial para pequenas empresas alcancarem novos clientes.",
        },
        "usuario_id": usuario_id,
    }

    async with async_session_factory() as session:
        resultado = await agente.executar(estado, session)

    logger.info(f"[OK] CriadorBrief executou. Chaves: {list(resultado.keys())}")
    return True


async def test_redator_agent(usuario_id: str, execucao_id: str):
    logger.info("\n=== TEST 5: RedatorAgent ===")
    from app.agents.redator import RedatorAgent

    agente = RedatorAgent(usuario_id=usuario_id)

    estado = {
        "execucao_id": execucao_id,
        "topico": "marketing digital para pequenas empresas",
        "palavra_chave_principal": "marketing digital",
        "palavras_chave_secundarias": ["redes sociais", "conteudo digital"],
        "brief": "Crie um guia completo sobre marketing digital para pequenas empresas, incluindo redes sociais, SEO e conteudo digital. Meta: 1500 palavras.",
        "conteudos_selecionados": [],
        "meta_palavras": 1500,
        "tipo_conteudo": "blog",
        "versao_atual": 0,
        "usuario_id": usuario_id,
    }

    async with async_session_factory() as session:
        resultado = await agente.executar(estado, session)
        await session.commit()

    logger.info(f"[OK] Redator executou. Chaves: {list(resultado.keys())}")
    artigo = resultado.get("artigo", {})
    if artigo.get("conteudo_markdown"):
        n_chars = len(artigo["conteudo_markdown"])
        n_words = artigo.get("contagem_palavras", 0) or len(artigo["conteudo_markdown"].split())
        logger.info(f"[OK] Conteudo criado: {n_chars} chars, ~{n_words} palavras")
        logger.info(f"[OK] Titulo: {artigo.get('titulo', 'N/A')}")
    return resultado


async def test_revisor_agent(usuario_id: str, execucao_id: str, artigo: dict, brief: dict):
    logger.info("\n=== TEST 6: RevisorAgent ===")
    from app.agents.revisor import RevisorAgent

    agente = RevisorAgent(usuario_id=usuario_id)

    estado = {
        "execucao_id": execucao_id,
        "artigo": artigo,
        "artigo_titulo": artigo.get("titulo", ""),
        "brief": brief,
        "meta_palavras": 1500,
        "versao_atual": 1,
        "tentativas_revisao": 0,
        "usuario_id": usuario_id,
    }

    async with async_session_factory() as session:
        resultado = await agente.executar(estado, session)
        await session.commit()

    logger.info(f"[OK] Revisor executou. Chaves: {list(resultado.keys())}")
    revisao = resultado.get("revisao", {})
    aprovado = resultado.get("aprovado_revisor", False)
    score = revisao.get("score_qualidade", 0)
    logger.info(f"[OK] Score: {score}, Aprovado: {aprovado}")
    problemas = revisao.get("problemas", [])
    if problemas:
        logger.info(f"[OK] Problemas: {problemas[:3]}")
    return resultado


async def main():
    logger.info("=" * 60)
    logger.info("E2E TEST - ZhipuAI Agents (all 6)")
    logger.info(f"Model: {settings.llm_model}")
    logger.info(f"SERPAPI: {'CONFIGURADA' if settings.serpapi_key else 'NAO CONFIGURADA'}")
    logger.info(f"Zhipuai Key: {settings.zhipuai_api_key[:10]}...")
    logger.info(f"Cooldown entre testes: {COOLDOWN}s")
    logger.info("=" * 60)

    usuario_id = await criar_test_usuario_e_creditos()
    gerar_jwt(usuario_id)

    execucao_id = await criar_execucao_teste(usuario_id)

    try:
        await test_base_agent_llm(usuario_id)
        logger.info(f"[COOLDOWN] aguardando {COOLDOWN}s...")
        await asyncio.sleep(COOLDOWN)

        await test_pesquisador_agent(usuario_id)
        logger.info(f"[COOLDOWN] aguardando {COOLDOWN}s...")
        await asyncio.sleep(COOLDOWN)

        await test_analisador_agent(usuario_id)
        logger.info(f"[COOLDOWN] aguardando {COOLDOWN}s...")
        await asyncio.sleep(COOLDOWN)

        await test_criador_brief_agent(usuario_id)
        logger.info(f"[COOLDOWN] aguardando {COOLDOWN}s...")
        await asyncio.sleep(COOLDOWN)

        artigo_resultado = await test_redator_agent(usuario_id, execucao_id)
        artigo = artigo_resultado.get("artigo", {})
        brief_data = "Guia sobre marketing digital para pequenas empresas"
        logger.info(f"[COOLDOWN] aguardando {COOLDOWN}s...")
        await asyncio.sleep(COOLDOWN)

        await test_revisor_agent(usuario_id, execucao_id, artigo, brief_data)

        logger.info("\n" + "=" * 60)
        logger.info("TODOS OS 6 TESTES PASSARAM!")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"\n[FALHA] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
