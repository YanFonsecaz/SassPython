import asyncio
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from app.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

from app.agents.workflow_helpers import workflow_node  # noqa: E402


class EstadoWorkflow(TypedDict):
    execucao_id: str
    usuario_id: str
    cliente_id: str
    cliente_config: dict[str, Any]
    persona_selecionada: dict[str, Any]

    topico: str
    palavra_chave_principal: str
    palavras_chave_secundarias: list[str]
    tipo_conteudo: str
    meta_palavras: int
    objetivo: str
    artigo_introdutorio: str
    perguntas_clientes: str
    instrucoes_adicionais: str

    pesquisa_resultados: dict[str, Any]
    conteudos_selecionados: list[dict[str, Any]]
    resumo_analise: str
    brief: dict[str, Any]
    artigo: dict[str, Any]
    artigo_titulo: str
    revisao: dict[str, Any]
    feedback_usuario: str

    tentativas_revisao: int
    tentativas_feedback: int
    versao_atual: int
    aprovado_revisor: bool
    aprovado_usuario: bool

    imagem_url: str | None
    imagem_prompt: str | None
    imagem_alt_text: str | None
    conteudo_final: dict[str, Any]


@workflow_node("pesquisar", "Pesquisando tendencias e conteudos...")
async def node_pesquisar(estado: EstadoWorkflow, session) -> dict[str, Any]:
    from app.agents.pesquisador import PesquisadorAgent

    agente = PesquisadorAgent(estado["usuario_id"])
    return await agente.executar(estado, session)


@workflow_node("analisar", "Analisando conteudos selecionados...")
async def node_analisar(estado: EstadoWorkflow, session) -> dict[str, Any]:
    from app.agents.analisador import AnalisadorAgent

    agente = AnalisadorAgent(estado["usuario_id"])
    return await agente.executar(estado, session)


@workflow_node("criar_brief", "Criando brief de redacao...")
async def node_criar_brief(estado: EstadoWorkflow, session) -> dict[str, Any]:
    from app.agents.criador_brief import CriadorBriefAgent

    agente = CriadorBriefAgent(estado["usuario_id"])
    return await agente.executar(estado, session)


@workflow_node("redigir", "Redigindo artigo...")
async def node_redigir(estado: EstadoWorkflow, session) -> dict[str, Any]:
    from app.agents.redator import RedatorAgent

    agente = RedatorAgent(estado["usuario_id"])
    resultado = await agente.executar(estado, session)
    resultado["versao_atual"] = estado.get("versao_atual", 0) + 1
    return resultado


@workflow_node("revisar", "Revisando qualidade...")
async def node_revisar(estado: EstadoWorkflow, session) -> dict[str, Any]:
    from app.agents.revisor import RevisorAgent

    agente = RevisorAgent(estado["usuario_id"])
    resultado = await agente.executar(estado, session)
    resultado["tentativas_revisao"] = estado.get("tentativas_revisao", 0) + 1
    return resultado


@workflow_node("salvar_vetorial", "Salvando no banco vetorial...")
async def node_salvar_vetorial(estado: EstadoWorkflow, session) -> dict[str, Any]:
    try:
        from app.core.graceful_degradation import gerar_embedding_com_fallback
        from app.models.conteudo_vetor import ConteudoVetor

        artigo = estado.get("artigo", {})
        texto = artigo.get("conteudo_markdown", "")
        titulo = artigo.get("titulo", estado.get("artigo_titulo", ""))

        embedding, _fallback = await gerar_embedding_com_fallback(texto[:8000], estado["usuario_id"])
        if embedding is not None:
            conteudo = ConteudoVetor(
                usuario_id=estado["usuario_id"],
                cliente_id=estado.get("cliente_id") or None,
                execucao_id=estado["execucao_id"],
                titulo=titulo,
                conteudo=texto,
                tipo=estado.get("tipo_conteudo", "blog"),
                intencao="informacional",
                palavras_chave=estado.get("palavras_chave_secundarias", []),
                atividades=[],
                embedding=embedding,
                score_base=estado.get("revisao", {}).get("score_qualidade", 0),
            )
            session.add(conteudo)
    except Exception as e:
        logger.warning("Falha ao salvar conteudo vetorial: %s", e)

    return {}


@workflow_node("gerar_imagem", "Gerando imagem com IA...")
async def node_gerar_imagem(estado: EstadoWorkflow, session) -> dict[str, Any]:
    from app.agents.gerador_imagem import GeradorImagemAgent

    agente = GeradorImagemAgent(estado["usuario_id"])
    return await agente.executar(estado, session)


@workflow_node("marcar_aguardando", "Aguardando revisao do usuario...")
async def node_marcar_aguardando(estado: EstadoWorkflow, session) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    from app.services import ferramenta_service

    eid = estado["execucao_id"]
    versao_atual = estado.get("versao_atual", 1)
    aprovado = estado.get("aprovado_revisor", False)
    score = estado.get("revisao", {}).get("score_qualidade", 0)

    status = "aguardando_aprovacao" if aprovado else "aguardando_revisao"
    if aprovado:
        msg = f"Artigo versao {versao_atual} aprovado pela IA (score {score}/100). Aguardando sua revisao..."
    else:
        msg = f"Artigo versao {versao_atual} precisa de ajustes (score {score}/100). Aguardando seu feedback..."
    await ferramenta_service.atualizar_execucao(session, eid, status=status)
    await publish_event(eid, "aguardando", "aguardar_aprovacao", msg)
    return {}


async def node_aguardar_aprovacao(estado: EstadoWorkflow) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    from app.services import ferramenta_service

    eid = estado["execucao_id"]
    resume_value = interrupt({
        "tipo": "aprovacao_usuario",
        "versao": estado.get("versao_atual", 1),
        "score": estado.get("revisao", {}).get("score_qualidade", 0),
    })

    aprovado_usuario = False
    feedback_usuario = ""
    if isinstance(resume_value, dict):
        aprovado_usuario = resume_value.get("aprovado_usuario", False)
        feedback_usuario = resume_value.get("feedback_usuario", "")

    async with async_session_factory() as session:
        await ferramenta_service.atualizar_execucao(session, eid, status="executando")
        await session.commit()

    await publish_event(
        eid, "node_complete", "aguardar_aprovacao",
        "Aprovado" if aprovado_usuario else "Feedback recebido, reiniciando revisao",
    )

    return {
        "aprovado_usuario": aprovado_usuario,
        "feedback_usuario": feedback_usuario,
        "tentativas_feedback": estado.get("tentativas_feedback", 0) + (0 if aprovado_usuario else 1),
    }


def roteamento_revisor(estado: EstadoWorkflow) -> str:
    if estado.get("aprovado_revisor", False):
        return "aguardar_aprovacao"
    if estado.get("tentativas_revisao", 0) < settings.workflow_max_revisoes:
        return "redigir"
    return "aguardar_aprovacao"


def roteamento_usuario(estado: EstadoWorkflow) -> str:
    if estado.get("aprovado_usuario", False):
        return "salvar_vetorial"
    if estado.get("tentativas_feedback", 0) < settings.workflow_max_feedback:
        return "redigir"
    return "salvar_vetorial"


def criar_workflow(checkpointer=None):
    workflow = StateGraph(EstadoWorkflow)

    workflow.add_node("pesquisar", node_pesquisar)
    workflow.add_node("analisar", node_analisar)
    workflow.add_node("criar_brief", node_criar_brief)
    workflow.add_node("redigir", node_redigir)
    workflow.add_node("revisar", node_revisar)
    workflow.add_node("marcar_aguardando", node_marcar_aguardando)
    workflow.add_node("aguardar_aprovacao", node_aguardar_aprovacao)
    workflow.add_node("salvar_vetorial", node_salvar_vetorial)
    workflow.add_node("gerar_imagem", node_gerar_imagem)

    workflow.set_entry_point("pesquisar")
    workflow.add_edge("pesquisar", "analisar")
    workflow.add_edge("analisar", "criar_brief")
    workflow.add_edge("criar_brief", "redigir")
    workflow.add_edge("redigir", "revisar")

    workflow.add_conditional_edges(
        "revisar",
        roteamento_revisor,
        {"redigir": "redigir", "aguardar_aprovacao": "marcar_aguardando"},
    )

    workflow.add_edge("marcar_aguardando", "aguardar_aprovacao")

    workflow.add_conditional_edges(
        "aguardar_aprovacao",
        roteamento_usuario,
        {"redigir": "redigir", "salvar_vetorial": "salvar_vetorial"},
    )

    workflow.add_edge("salvar_vetorial", "gerar_imagem")
    workflow.add_edge("gerar_imagem", END)

    return workflow.compile(checkpointer=checkpointer)


async def _atualizar_etapa(execucao_id: str, etapa: str, session=None) -> None:
    from app.services import ferramenta_service

    if session is not None:
        await ferramenta_service.atualizar_etapa(session, execucao_id, etapa)
    else:
        async with async_session_factory() as s:
            await ferramenta_service.atualizar_etapa(s, execucao_id, etapa)
            await s.commit()


async def executar_workflow_completo(execucao_id: str, ctx: dict[str, Any] | None = None) -> None:
    from app.services import ferramenta_service

    try:
        async with async_session_factory() as session:
            await ferramenta_service.atualizar_execucao(session, execucao_id, status="executando")
            await session.commit()

            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if not execucao:
                return

            entrada = execucao.entrada_json

            if execucao.cliente_id:
                from app.services import cliente_service

                cliente = await cliente_service.buscar_cliente(session, str(execucao.cliente_id), str(execucao.usuario_id))
                cliente_config = cliente.config_json if cliente else {}
            else:
                cliente_config = {}

            persona_nome = entrada.get("persona_id", "")
            personas = cliente_config.get("personas", [])
            persona = next((p for p in personas if p.get("nome") == persona_nome), {})

        estado_inicial: EstadoWorkflow = {
            "execucao_id": execucao_id,
            "usuario_id": str(execucao.usuario_id),
            "cliente_id": str(execucao.cliente_id) if execucao.cliente_id else "",
            "cliente_config": cliente_config,
            "persona_selecionada": persona,
            "topico": entrada.get("topico", ""),
            "palavra_chave_principal": entrada.get("palavra_chave_principal", ""),
            "palavras_chave_secundarias": entrada.get("palavras_chave_secundarias", []),
            "tipo_conteudo": entrada.get("tipo_conteudo", "blog"),
            "meta_palavras": entrada.get("meta_palavras", 2000),
            "objetivo": entrada.get("objetivo", ""),
            "artigo_introdutorio": entrada.get("artigo_introdutorio", ""),
            "perguntas_clientes": entrada.get("perguntas_clientes", ""),
            "instrucoes_adicionais": entrada.get("instrucoes_adicionais", ""),
            "tentativas_revisao": 0,
            "tentativas_feedback": 0,
            "versao_atual": 0,
            "aprovado_revisor": False,
            "aprovado_usuario": False,
        }

        from app.agents.checkpointer import get_checkpointer_from_ctx

        cp = get_checkpointer_from_ctx(ctx)
        if cp:
            workflow = criar_workflow(checkpointer=cp)
            config = {"configurable": {"thread_id": str(execucao.thread_id)}}
            await asyncio.wait_for(
                _run_workflow(workflow, estado_inicial, config, execucao_id),
                timeout=settings.workflow_timeout_segundos,
            )
        else:
            from app.agents.checkpointer import get_checkpointer

            checkpointer = await get_checkpointer()
            workflow = criar_workflow(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": str(execucao.thread_id)}}
            await asyncio.wait_for(
                _run_workflow(workflow, estado_inicial, config, execucao_id),
                timeout=settings.workflow_timeout_segundos,
            )

    except asyncio.CancelledError:
        logger.info("Workflow cancelado para execucao %s", execucao_id)
        async with async_session_factory() as session:
            from app.services import credito_service

            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if execucao and execucao.status == "executando":
                ferramenta = execucao.ferramenta or "gerar_artigo"
                reserva = ferramenta_service._obter_reserva_estimada(ferramenta, execucao)
                if reserva > 0:
                    await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
                await ferramenta_service.atualizar_execucao(
                    session, execucao_id, status="cancelada", creditos_cobrados=0,
                )
                await session.commit()
        raise

    except TimeoutError:
        minutos = settings.workflow_timeout_segundos // 60
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, f"Workflow excedeu o tempo limite de {minutos} minutos")
            await session.commit()
    except Exception as e:
        logger.error("Workflow falhou para execucao %s: %s", execucao_id, e)
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Erro interno do workflow")
            await session.commit()


async def _run_workflow(workflow, estado_inicial, config, execucao_id: str) -> None:
    async for _event in workflow.astream(estado_inicial, config=config, version="v2"):
        pass

    snapshot = await workflow.aget_state(config)
    estado_final = snapshot.values if snapshot else None

    async with async_session_factory() as session:
        from app.services import ferramenta_service

        execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
        if execucao and execucao.status == "executando":
            resultado = _extrair_resultado(estado_final)
            await ferramenta_service.finalizar_sucesso(
                session, execucao_id, resultado,
                versao_atual=(estado_final or {}).get("versao_atual", 1),
                tentativas_revisao=(estado_final or {}).get("tentativas_revisao", 0),
                tentativas_feedback=(estado_final or {}).get("tentativas_feedback", 0),
            )
            await session.commit()


async def retomar_workflow(execucao_id: str, acao: str, feedback: str | None, ctx: dict[str, Any] | None = None) -> None:
    from app.services import ferramenta_service

    async with async_session_factory() as session:
        execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
        if not execucao:
            return

        await session.commit()

    aprovado = acao == "aprovar"

    resume_value = {
        "aprovado_usuario": aprovado,
        "feedback_usuario": feedback or "",
    }

    if not aprovado:
        resume_value["aprovado_revisor"] = False

    try:
        from app.agents.checkpointer import get_checkpointer_from_ctx

        async with async_session_factory() as session:
            await ferramenta_service.atualizar_execucao(session, execucao_id, status="executando")
            await session.commit()

        cp = get_checkpointer_from_ctx(ctx)
        if cp:
            workflow = criar_workflow(checkpointer=cp)
            config = {"configurable": {"thread_id": str(execucao.thread_id)}}
            await asyncio.wait_for(
                _run_resumed_workflow(workflow, resume_value, config, execucao_id),
                timeout=settings.workflow_timeout_segundos,
            )
        else:
            from app.agents.checkpointer import get_checkpointer

            checkpointer = await get_checkpointer()
            workflow = criar_workflow(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": str(execucao.thread_id)}}
            await asyncio.wait_for(
                _run_resumed_workflow(workflow, resume_value, config, execucao_id),
                timeout=settings.workflow_timeout_segundos,
            )
    except asyncio.CancelledError:
        logger.info("Retomada cancelada para execucao %s", execucao_id)
        raise
    except TimeoutError:
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Workflow excedeu o tempo limite")
            await session.commit()
    except Exception as e:
        logger.error("Retomada falhou para execucao %s: %s", execucao_id, e)
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Erro na retomada do workflow")
            await session.commit()


async def _run_resumed_workflow(workflow, resume_value, config, execucao_id: str) -> None:
    from app.db.session import async_session_factory
    from app.services import ferramenta_service

    async for _event in workflow.astream(Command(resume=resume_value), config=config, version="v2"):
        pass

    snapshot = await workflow.aget_state(config)
    estado_final = snapshot.values if snapshot else None

    async with async_session_factory() as session:
        execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
        if execucao and execucao.status == "executando":
            resultado = _extrair_resultado(estado_final)
            await ferramenta_service.finalizar_sucesso(
                session, execucao_id, resultado,
                versao_atual=(estado_final or {}).get("versao_atual", 1),
                tentativas_revisao=(estado_final or {}).get("tentativas_revisao", 0),
                tentativas_feedback=(estado_final or {}).get("tentativas_feedback", 0),
            )
            await session.commit()


def _extrair_resultado(estado: dict[str, Any] | None) -> dict[str, Any]:
    if not estado:
        return {"artigo_titulo": "", "imagem_url": None, "artigo": ""}
    artigo = estado.get("artigo", {})
    titulo = estado.get("artigo_titulo", "") or artigo.get("titulo", "")
    conteudo = artigo.get("conteudo_markdown", "")
    imagem_url = estado.get("imagem_url")
    return {
        "artigo_titulo": titulo,
        "imagem_url": imagem_url,
        "artigo": conteudo,
        "conteudo_markdown": conteudo,
    }
