import asyncio
import logging
import time
from datetime import UTC, datetime

from app.core.excecoes import ErroPermanente
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def executar_workflow_parecer(execucao_id: str, ctx=None):
    from app.config import settings
    from app.services import credito_service, ferramenta_service

    t0 = time.monotonic()
    async with async_session_factory() as session:
        ex = await ferramenta_service.buscar_execucao(session, execucao_id)
        if not ex:
            return
        entrada = dict(ex.entrada_json)
        usuario_id = str(ex.usuario_id)
        cliente_id = str(ex.cliente_id)
        custo = ex.creditos_cobrados
        await ferramenta_service.atualizar_execucao(session, execucao_id, status="processando", etapa_atual="analisando_imagens")
        await session.commit()

    logger.info("parecer.workflow.start", extra={
        "event_type": "parecer.workflow.start",
        "execucao_id": execucao_id,
        "n_imagens": sum(len(b.get("imagens", [])) for b in entrada.get("blocos", [])),
        "modelo": settings.parecer_analisador_model,
    })

    if not settings.openai_api_key:
        await _falhar(execucao_id, usuario_id, custo, "OPENAI_API_KEY ausente — visao indisponivel")
        raise ErroPermanente("OPENAI_API_KEY ausente")

    achados = []
    pares_img = []
    indice = 0
    for bloco in entrada.get("blocos", []):
        for data_uri in bloco.get("imagens", []):
            pares_img.append((indice, data_uri))
            indice += 1

    if pares_img:
        from app.agents.parecer.analisador import analisar_imagem
        nota_map = _construir_nota_map(entrada)
        tasks = [
            analisar_imagem(usuario_id, i, uri, nota_map.get(i, ""))
            for i, uri in pares_img
        ]
        achados = await asyncio.gather(*tasks)
        achados = list(achados)

    try:
        await _set_etapa(execucao_id, "redigindo_parecer")
        from app.agents.parecer.documentador import gerar_parecer_estruturado
        from app.core.metrics import parecer_imagens_total
        for a in achados:
            parecer_imagens_total.labels(status="degradado" if a.degradado else "ok").inc()
        estrutura = await gerar_parecer_estruturado(
            usuario_id,
            cliente_nome=entrada.get("cliente_nome", "Cliente"),
            blocos=entrada.get("blocos", []),
            achados=achados,
        )

        from app.services.parecer_service import estrutura_para_html
        parecer_html = estrutura_para_html(estrutura.model_dump(), imagens_por_indice=dict(pares_img))

        from app.services import parecer_persistencia
        async with async_session_factory() as session:
            parecer = await parecer_persistencia.criar_parecer(
                session,
                execucao_id=execucao_id,
                cliente_id=cliente_id,
                usuario_id=usuario_id,
                cliente_nome=entrada.get("cliente_nome", "Cliente"),
                estrutura=estrutura.model_dump(),
                parecer_html=parecer_html,
                n_imagens=len(pares_img),
                modelo=settings.parecer_documentador_model,
            )
            await ferramenta_service.atualizar_execucao(
                session,
                execucao_id,
                status="concluida",
                etapa_atual="concluido",
                concluida_em=datetime.now(UTC),
                resultado_json={"parecer_id": str(parecer.id)},
            )
            await credito_service.confirmar_debito(
                session, usuario_id, custo, custo,
                descricao=f"Parecer tecnico: {custo} creditos",
                ferramenta="parecer_tecnico",
                execucao_id=execucao_id,
            )
            await session.commit()

        dur_ms = (time.monotonic() - t0) * 1000
        from app.core.metrics import parecer_geracoes_total, parecer_workflow_duration
        parecer_workflow_duration.observe(time.monotonic() - t0)
        parecer_geracoes_total.labels(status="concluida").inc()
        logger.info("parecer.workflow.done", extra={
            "event_type": "parecer.workflow.done",
            "execucao_id": execucao_id,
            "n_imagens": len(pares_img),
            "dur_ms": round(dur_ms),
        })
    except ErroPermanente:
        from app.core.metrics import parecer_geracoes_total, parecer_workflow_duration
        parecer_workflow_duration.observe(time.monotonic() - t0)
        parecer_geracoes_total.labels(status="erro_permanente").inc()
        raise
    except Exception as e:
        from app.core.metrics import parecer_geracoes_total, parecer_workflow_duration
        parecer_workflow_duration.observe(time.monotonic() - t0)
        parecer_geracoes_total.labels(status="falha").inc()
        import sentry_sdk
        sentry_sdk.set_tag("ferramenta", "parecer_tecnico")
        sentry_sdk.set_tag("execucao_id", execucao_id)
        sentry_sdk.capture_exception(e)
        dur_ms = (time.monotonic() - t0) * 1000
        logger.error("parecer.workflow.failed", extra={
            "event_type": "parecer.workflow.failed",
            "execucao_id": execucao_id,
            "dur_ms": round(dur_ms),
            "erro": str(e),
        })
        await _falhar(execucao_id, usuario_id, custo, f"Erro ao gerar parecer: {e}")
        raise


def _construir_nota_map(entrada: dict) -> dict[int, str]:
    nota_map = {}
    indice = 0
    for bloco in entrada.get("blocos", []):
        nota = bloco.get("texto", "")
        for _ in bloco.get("imagens", []):
            nota_map[indice] = nota
            indice += 1
    return nota_map


async def _set_etapa(execucao_id: str, etapa: str) -> None:
    from app.services import ferramenta_service
    async with async_session_factory() as session:
        await ferramenta_service.atualizar_execucao(session, execucao_id, etapa_atual=etapa)
        await session.commit()


async def _falhar(execucao_id: str, usuario_id: str, custo: int, msg: str) -> None:
    from app.services import credito_service, ferramenta_service
    async with async_session_factory() as session:
        await ferramenta_service.finalizar_falha(session, execucao_id, msg, ferramenta="parecer_tecnico")
        if custo > 0:
            await credito_service.liberar_reserva(session, usuario_id, custo)
        await session.commit()


def _data_ptbr() -> str:
    return datetime.now(UTC).astimezone().strftime("%d/%m/%Y")
