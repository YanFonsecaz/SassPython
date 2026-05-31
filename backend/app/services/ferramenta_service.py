import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update

from app.config import settings
from app.models.execucao_ferramenta import ExecucaoFerramenta
from app.models.versao_artigo import VersaoArtigo

logger = logging.getLogger(__name__)

CUSTO_BASE = 15
CUSTO_REVISAO = 3
CUSTO_IMAGEM = 5
CUSTO_MINIMO = CUSTO_BASE + CUSTO_IMAGEM

CUSTO_BASE_INLINKS = 15
CUSTO_POR_URL_INLINKS = 1
CUSTO_MAX_INLINKS = 60

CUSTO_BASE_DISTRIBUIR_INLINKS = 15
CUSTO_POR_CANDIDATA_DISTRIBUIR = 1
CUSTO_MAX_DISTRIBUIR_INLINKS = 115

CUSTO_BASE_CWV = 15
CUSTO_POR_URL_CWV = 1
CUSTO_MAX_CWV = 100

CUSTO_BASE_PARECER = 10
CUSTO_POR_IMAGEM_PARECER = 3
CUSTO_MAX_PARECER = 90


CUSTOS_TABELA = [
    {"acao": "gerar_artigo_base", "custo_creditos": CUSTO_BASE, "chamadas_llm_estimadas": 5},
    {"acao": "revisao_automatica", "custo_creditos": CUSTO_REVISAO, "chamadas_llm_estimadas": 2},
    {"acao": "feedback_humano", "custo_creditos": CUSTO_REVISAO, "chamadas_llm_estimadas": 2},
    {"acao": "gerar_imagem", "custo_creditos": CUSTO_IMAGEM, "chamadas_llm_estimadas": 2},
    {"acao": "salvar_vetorial", "custo_creditos": 0, "chamadas_llm_estimadas": 0},
    {"acao": "inlinks_base", "custo_creditos": CUSTO_BASE_INLINKS, "chamadas_llm_estimadas": 3},
    {"acao": "inlinks_por_url", "custo_creditos": CUSTO_POR_URL_INLINKS, "chamadas_llm_estimadas": 0},
    {"acao": "distribuir_inlinks_base", "custo_creditos": CUSTO_BASE_DISTRIBUIR_INLINKS, "chamadas_llm_estimadas": 3},
    {"acao": "distribuir_inlinks_por_candidata", "custo_creditos": CUSTO_POR_CANDIDATA_DISTRIBUIR, "chamadas_llm_estimadas": 0},
    {"acao": "cwv_base", "custo_creditos": CUSTO_BASE_CWV, "chamadas_llm_estimadas": 0},
    {"acao": "cwv_por_url", "custo_creditos": CUSTO_POR_URL_CWV, "chamadas_llm_estimadas": 0},
    {"acao": "parecer_base", "custo_creditos": CUSTO_BASE_PARECER, "chamadas_llm_estimadas": 1},
    {"acao": "parecer_por_imagem", "custo_creditos": CUSTO_POR_IMAGEM_PARECER, "chamadas_llm_estimadas": 1},
]


def calcular_custo_inlinks(n_processadas: int) -> int:
    return min(CUSTO_BASE_INLINKS + n_processadas * CUSTO_POR_URL_INLINKS, CUSTO_MAX_INLINKS)


def calcular_custo_distribuir_inlinks(n_candidatas: int) -> int:
    return min(CUSTO_BASE_DISTRIBUIR_INLINKS + n_candidatas * CUSTO_POR_CANDIDATA_DISTRIBUIR, CUSTO_MAX_DISTRIBUIR_INLINKS)


def calcular_custo_cwv(n_urls: int) -> int:
    return min(CUSTO_BASE_CWV + n_urls * CUSTO_POR_URL_CWV, CUSTO_MAX_CWV)


def calcular_custo_parecer(n_imagens: int) -> int:
    return min(CUSTO_BASE_PARECER + n_imagens * CUSTO_POR_IMAGEM_PARECER, CUSTO_MAX_PARECER)


async def criar_execucao(
    db,
    usuario_id: str,
    cliente_id: str | None,
    entrada: dict[str, Any],
    ferramenta: str = "gerar_artigo",
    timeout_seconds: int | None = None,
    creditos_reservados: int = 0,
) -> ExecucaoFerramenta:
    timeout_seconds = timeout_seconds or settings.workflow_timeout_segundos
    entrada_json = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in entrada.items()}
    execucao = ExecucaoFerramenta(
        usuario_id=usuario_id,
        cliente_id=cliente_id,
        ferramenta=ferramenta,
        status="pendente",
        entrada_json=entrada_json,
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=timeout_seconds),
    )
    _ = creditos_reservados
    db.add(execucao)
    await db.flush()
    return execucao


async def buscar_execucao(db, execucao_id: str) -> ExecucaoFerramenta | None:
    resultado = await db.execute(select(ExecucaoFerramenta).where(ExecucaoFerramenta.id == execucao_id))
    return resultado.scalar_one_or_none()


async def buscar_execucao_por_thread(db, thread_id: str) -> ExecucaoFerramenta | None:
    resultado = await db.execute(
        select(ExecucaoFerramenta).where(ExecucaoFerramenta.thread_id == thread_id)
    )
    return resultado.scalar_one_or_none()


async def atualizar_execucao(db, execucao_id: str, **kwargs) -> ExecucaoFerramenta | None:
    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        return None
    for key, value in kwargs.items():
        if hasattr(execucao, key):
            setattr(execucao, key, value)
    await db.flush()
    return execucao


async def atualizar_etapa(db, execucao_id: str, etapa: str) -> None:
    await db.execute(
        update(ExecucaoFerramenta).where(ExecucaoFerramenta.id == execucao_id).values(etapa_atual=etapa)
    )
    await db.flush()


async def listar_execucoes(
    db, usuario_id: str, limite: int = 20, offset: int = 0
) -> tuple[list[ExecucaoFerramenta], int]:
    base = select(ExecucaoFerramenta).where(ExecucaoFerramenta.usuario_id == usuario_id)
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    stmt = base.order_by(ExecucaoFerramenta.criado_em.desc()).offset(offset).limit(limite)
    resultado = await db.execute(stmt)
    return list(resultado.scalars().all()), total


async def salvar_versao(
    db,
    execucao_id: str,
    versao: int,
    origem: str,
    titulo: str,
    conteudo_markdown: str,
    contagem_palavras: int,
    score_revisao: float | None = None,
    feedback_recebido: str | None = None,
) -> VersaoArtigo:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(VersaoArtigo).values(
        execucao_id=execucao_id,
        versao=versao,
        origem=origem,
        titulo=titulo,
        conteudo_markdown=conteudo_markdown,
        contagem_palavras=contagem_palavras,
        score_revisao=score_revisao,
        feedback_recebido=feedback_recebido,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["execucao_id", "versao"],
        set_={
            "titulo": stmt.excluded.titulo,
            "conteudo_markdown": stmt.excluded.conteudo_markdown,
            "contagem_palavras": stmt.excluded.contagem_palavras,
            "score_revisao": stmt.excluded.score_revisao,
            "feedback_recebido": stmt.excluded.feedback_recebido,
            "origem": stmt.excluded.origem,
        },
    )
    await db.execute(stmt)
    await db.flush()
    resultado = await db.execute(
        select(VersaoArtigo).where(
            VersaoArtigo.execucao_id == execucao_id,
            VersaoArtigo.versao == versao,
        )
    )
    return resultado.scalar_one()


async def listar_versoes(db, execucao_id: str) -> list[VersaoArtigo]:
    resultado = await db.execute(
        select(VersaoArtigo)
        .where(VersaoArtigo.execucao_id == execucao_id)
        .order_by(VersaoArtigo.versao.desc())
    )
    return list(resultado.scalars().all())


async def atualizar_versao_revisao(
    db,
    execucao_id: str,
    versao: int,
    score_revisao: float | None = None,
    feedback_recebido: str | None = None,
) -> VersaoArtigo | None:
    resultado = await db.execute(
        select(VersaoArtigo).where(
            VersaoArtigo.execucao_id == execucao_id,
            VersaoArtigo.versao == versao,
        )
    )
    versao_artigo = resultado.scalar_one_or_none()
    if not versao_artigo:
        return None
    if score_revisao is not None:
        versao_artigo.score_revisao = score_revisao
    if feedback_recebido is not None:
        versao_artigo.feedback_recebido = feedback_recebido
    await db.flush()
    return versao_artigo


async def calcular_custo_final(execucao: ExecucaoFerramenta) -> int:
    custo = CUSTO_BASE
    custo += execucao.tentativas_revisao * CUSTO_REVISAO
    custo += execucao.tentativas_feedback * CUSTO_REVISAO
    custo += CUSTO_IMAGEM
    return custo


def _obter_reserva_estimada(ferramenta: str, execucao: ExecucaoFerramenta) -> int:
    if ferramenta == "gerar_artigo":
        return CUSTO_MINIMO
    if ferramenta in ("inlinks", "inlinks_automaticos"):
        return CUSTO_BASE_INLINKS
    if ferramenta == "distribuir_inlinks":
        return CUSTO_BASE_DISTRIBUIR_INLINKS
    if ferramenta == "core_web_vitals":
        return CUSTO_BASE_CWV
    if ferramenta == "parecer_tecnico":
        return CUSTO_BASE_PARECER
    return 0


async def finalizar_sucesso(db, execucao_id: str, resultado_json: dict[str, Any]) -> ExecucaoFerramenta:
    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(f"Execucao {execucao_id} nao encontrada")

    custo = await calcular_custo_final(execucao)
    from app.services import credito_service

    try:
        await credito_service.confirmar_debito(
            db,
            str(execucao.usuario_id),
            reservado=CUSTO_MINIMO,
            quantidade=custo,
            descricao=f"Gerar artigo: {custo} creditos (base={CUSTO_BASE}, revisoes={execucao.tentativas_revisao}, feedbacks={execucao.tentativas_feedback}, imagem={CUSTO_IMAGEM})",
            ferramenta="gerar_artigo",
            execucao_id=str(execucao.id),
        )
    except ValueError:
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), CUSTO_MINIMO)
        execucao.status = "falhou"
        execucao.erro_msg = "Saldo insuficiente no momento do debito"
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        return execucao

    execucao.status = "concluida"
    execucao.creditos_cobrados = custo
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    logger.info("execucao_id=%s status=concluida creditos=%d", execucao_id, custo)
    return execucao


async def finalizar_falha(db, execucao_id: str, erro_msg: str, ferramenta: str | None = None) -> ExecucaoFerramenta:
    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(f"Execucao {execucao_id} nao encontrada")

    from app.services import credito_service

    ferramenta_efetiva = ferramenta or execucao.ferramenta or "gerar_artigo"
    reserva = _obter_reserva_estimada(ferramenta_efetiva, execucao)
    if reserva > 0:
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)

    execucao.status = "falhou"
    execucao.erro_msg = erro_msg[:1000]
    execucao.creditos_cobrados = 0
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    logger.info(
        "execucao_falhou",
        extra={
            "event_type": "workflow.failed",
            "execucao_id": execucao_id,
            "ferramenta": ferramenta_efetiva,
            "erro_resumo": erro_msg[:100],
        },
    )
    return execucao


async def cancelar_execucao(db, execucao_id: str, usuario_id: str) -> ExecucaoFerramenta | None:
    execucao = await buscar_execucao(db, execucao_id)
    if not execucao or str(execucao.usuario_id) != usuario_id:
        return None
    if execucao.status not in ("pendente", "enfileirado", "executando", "aguardando_aprovacao", "aguardando_revisao"):
        return None

    from app.services import credito_service

    ferramenta = execucao.ferramenta or "gerar_artigo"
    reserva = _obter_reserva_estimada(ferramenta, execucao)
    if reserva > 0:
        await credito_service.liberar_reserva(db, usuario_id, reserva)

    execucao.status = "cancelada"
    execucao.creditos_cobrados = 0
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    return execucao


def obter_custos() -> list[dict[str, Any]]:
    return CUSTOS_TABELA


async def finalizar_sucesso_distribuir_inlinks(db, execucao_id: str, resultado_json: dict[str, Any]) -> ExecucaoFerramenta:
    from app.services import credito_service

    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(f"Execucao {execucao_id} nao encontrada")

    if resultado_json.get("alvo_invalido"):
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), CUSTO_BASE_DISTRIBUIR_INLINKS)
        execucao.status = "concluida"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = resultado_json.get("motivo_alvo") or (
            "URL alvo nao tem conteudo redacional suficiente. "
            "Use URL de artigo ou landing page, nao pagina de categoria/listagem."
        )
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        logger.info("%s distribuir_inlinks status=concluida sem creditos (alvo invalido)", execucao_id[:8])
        return execucao

    n_processadas = resultado_json.get("n_candidatas_validas", 0)

    if n_processadas == 0:
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), CUSTO_BASE_DISTRIBUIR_INLINKS)
        execucao.status = "concluida"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = (
            "Nenhuma candidata pode ser processada. "
            "Verifique se as URLs estao acessiveis."
        )
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        logger.info("%s distribuir_inlinks status=concluida sem creditos (0 candidatas validas)", execucao_id[:8])
        return execucao

    n_aplicadas = resultado_json.get("n_aplicadas", 0)
    n_sugestoes = resultado_json.get("n_sugestoes", 0)

    if n_aplicadas + n_sugestoes == 0:
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), CUSTO_BASE_DISTRIBUIR_INLINKS)
        execucao.status = "concluida"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = (
            f"Avaliamos {n_processadas} candidata(s), mas nenhuma tem similaridade "
            f"suficiente com a URL alvo para inserir um link. "
            f"Tente URLs candidatas mais relacionadas ao tema."
        )
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        logger.info(
            "%s distribuir_inlinks status=concluida sem creditos (0 aplicadas+sugestoes de %d)",
            execucao_id[:8], n_processadas,
        )
        return execucao

    custo = calcular_custo_distribuir_inlinks(n_processadas)

    try:
        await credito_service.confirmar_debito(
            db,
            str(execucao.usuario_id),
            reservado=CUSTO_BASE_DISTRIBUIR_INLINKS,
            quantidade=custo,
            descricao=f"Distribuir inlinks: {custo} creditos (candidatas={n_processadas})",
            ferramenta="distribuir_inlinks",
            execucao_id=execucao_id,
        )
    except ValueError:
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), CUSTO_BASE_DISTRIBUIR_INLINKS)
        execucao.status = "falhou"
        execucao.erro_msg = "Saldo insuficiente"
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        return execucao

    execucao.status = "concluida"
    execucao.creditos_cobrados = custo
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    logger.info("%s distribuir_inlinks status=concluida creditos=%d", execucao_id[:8], custo)
    return execucao
