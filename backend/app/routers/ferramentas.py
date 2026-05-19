import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.dependencies import get_current_user, get_db, rate_limit, rate_limit_autenticado
from app.models.usuario import Usuario
from app.schemas.ferramenta import (
    AprovacaoRequest,
    CancelarResponse,
    CustosResponse,
    ExecucaoCriadaResponse,
    ExecucaoDetalheResponse,
    ExecucoesListResponse,
    GerarArtigoRequest,
    MensagemResponse,
    VersoesListResponse,
)
from app.services import ferramenta_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/custos", response_model=CustosResponse)
async def obter_custos(
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    return {"custos": ferramenta_service.obter_custos()}


@router.post("/gerar-artigo", response_model=ExecucaoCriadaResponse, status_code=202)
async def gerar_artigo(
    body: GerarArtigoRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("gerar_artigo", max_requests=3, window_seconds=60)),
) -> dict[str, Any]:
    from fastapi import HTTPException

    from app.services import cliente_service, credito_service

    if body.cliente_id:
        cliente = await cliente_service.buscar_cliente(db, str(body.cliente_id), str(usuario.id))
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")

        config = cliente.config_json or {}
        personas = config.get("personas", [])
        if body.persona_id and not any(p.get("nome") == body.persona_id for p in personas):
            raise HTTPException(status_code=400, detail="Persona nao encontrada no cliente")

    from app.services.ferramenta_service import CUSTO_MINIMO

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), CUSTO_MINIMO)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc

    entrada = body.model_dump()
    execucao = await ferramenta_service.criar_execucao(
        db,
        usuario_id=str(usuario.id),
        cliente_id=str(body.cliente_id) if body.cliente_id else None,
        entrada=entrada,
    )

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        logger.error("Falha ao enfileirar workflow: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), CUSTO_MINIMO)
        execucao.status = "falhou"
        execucao.erro_msg = "Falha ao enfileirar workflow"
        await db.flush()

    return {
        "id": execucao.id,
        "ferramenta": execucao.ferramenta,
        "status": execucao.status,
        "etapa_atual": execucao.etapa_atual,
        "creditos_cobrados": execucao.creditos_cobrados,
        "criado_em": execucao.criado_em,
    }


@router.get("/historico", response_model=ExecucoesListResponse)
async def listar_historico(
    limite: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    execucoes, total = await ferramenta_service.listar_execucoes(db, str(usuario.id), limite=limite, offset=offset)
    return {"execucoes": execucoes, "total": total}


@router.get("/historico/{execucao_id}", response_model=ExecucaoDetalheResponse)
async def detalhe_execucao(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao or str(execucao.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")

    return execucao


@router.get("/historico/{execucao_id}/progresso")
async def stream_progresso(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit("progresso", max_requests=30, window_seconds=60)),
):
    from fastapi import HTTPException

    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao or str(execucao.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")

    channel_name = f"workflow:{execucao_id}"
    redis_queue: asyncio.Queue[Any] = asyncio.Queue()
    redis_sub_task = None

    async def subscribe_redis():
        nonlocal redis_sub_task
        pubsub = None
        try:
            from app.core.redis_pool import get_pubsub_client

            redis = await get_pubsub_client()
            pubsub = redis.pubsub()
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel_name)
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = message["data"]
                        if isinstance(data, str):
                            await redis_queue.put(data)
                        elif isinstance(data, bytes):
                            await redis_queue.put(data.decode("utf-8"))
            except asyncio.CancelledError:
                pass
        except Exception:
            logger.warning("Falha ao inscrever no Redis pub/sub para %s", execucao_id, exc_info=True)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(channel_name)
                    await pubsub.aclose()
                except Exception:
                    pass

    redis_sub_task = asyncio.create_task(subscribe_redis())

    async def evento_stream():
        try:
            while True:
                done = False

                async with async_session_factory() as session:
                    execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
                    if not execucao:
                        yield f"data: {json.dumps({'type': 'falhou', 'erro': 'Execucao nao encontrada'})}\n\n"
                        break

                    data = {
                        "type": "status",
                        "status": execucao.status,
                        "etapa": execucao.etapa_atual,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                    yield f"data: {json.dumps(data)}\n\n"

                    if execucao.status in ("concluida", "falhou", "cancelada"):
                        final = {"type": execucao.status}
                        if execucao.status == "falhou":
                            final["erro"] = execucao.erro_msg
                        elif execucao.status == "concluida":
                            final["creditos_cobrados"] = execucao.creditos_cobrados
                        yield f"data: {json.dumps(final)}\n\n"
                        break

                try:
                    while True:
                        msg = await asyncio.wait_for(redis_queue.get(), timeout=1.0)
                        try:
                            parsed = json.loads(msg) if isinstance(msg, str) else msg
                            event_type = parsed.get("type", "")
                            if event_type in ("node_start", "node_complete"):
                                yield f"data: {json.dumps({'type': 'node_progress', 'node': parsed.get('node'), 'detail': parsed.get('detail'), 'timestamp': parsed.get('timestamp')})}\n\n"
                                if parsed.get("type") == "node_complete" and parsed.get("node") == "aguardar_aprovacao":
                                    done = True
                                    break
                        except (json.JSONDecodeError, TypeError):
                            pass
                except TimeoutError:
                    pass

                if done:
                    break

                await asyncio.sleep(1)
        finally:
            if redis_sub_task:
                redis_sub_task.cancel()

    return StreamingResponse(
        evento_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/historico/{execucao_id}/versoes", response_model=VersoesListResponse)
async def listar_versoes(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao or str(execucao.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")

    versoes = await ferramenta_service.listar_versoes(db, execucao_id)
    return {"execucao_id": execucao.id, "versoes": versoes}


async def _enqueue_retomada(execucao_id: str, acao: str, feedback: str | None) -> str | None:
    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("retomar_workflow_job", execucao_id, acao, feedback)
        return job.job_id
    except Exception as e:
        logger.error("Falha ao enfileirar retomada: %s", e)
        return None


@router.post("/historico/{execucao_id}/aprovacao", response_model=MensagemResponse)
async def aprovar_reprovar(
    execucao_id: str,
    body: AprovacaoRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit("aprovacao", max_requests=10, window_seconds=60)),
) -> dict[str, Any]:
    from fastapi import HTTPException

    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao or str(execucao.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")

    if execucao.status not in ("aguardando_aprovacao", "aguardando_revisao"):
        raise HTTPException(status_code=400, detail="Execucao nao esta aguardando aprovacao")

    job_id = await _enqueue_retomada(execucao_id, body.acao, body.feedback)
    if not job_id:
        raise HTTPException(status_code=500, detail="Falha ao enfileirar retomada")

    await ferramenta_service.atualizar_execucao(db, execucao_id, status="executando", job_id=job_id)
    await db.commit()

    return {"mensagem": "Acao registrada com sucesso"}


@router.post("/historico/{execucao_id}/cancelar", response_model=CancelarResponse)
async def cancelar_execucao(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    execucao = await ferramenta_service.cancelar_execucao(db, execucao_id, str(usuario.id))
    if not execucao:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Execucao nao encontrada ou nao pode ser cancelada")

    aborted = False
    if execucao.job_id:
        try:
            from arq.jobs import Job

            from app.core.redis_pool import get_redis_commands

            redis = await get_redis_commands()
            job = Job(execucao.job_id, _queue_name="arq:queue", redis=redis)
            aborted = await job.abort()
            logger.info("job_abort execucao_id=%s job_id=%s aborted=%s", execucao_id, execucao.job_id, aborted)
        except Exception:
            logger.warning("job_abort falhou execucao_id=%s job_id=%s", execucao_id, execucao.job_id, exc_info=True)

    await db.commit()
    return {
        "id": execucao.id,
        "status": execucao.status,
        "creditos_cobrados": execucao.creditos_cobrados,
        "mensagem": "Execuacao cancelada. Nenhum credito foi debitado.",
        "job_aborted": aborted,
    }
