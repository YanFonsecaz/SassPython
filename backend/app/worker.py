import asyncio
import logging

from arq import Retry
from arq.connections import RedisSettings

from app.config import settings

logger = logging.getLogger(__name__)


async def ctx_startup(ctx):
    from app.core.logging import setup_logging

    setup_logging(settings.log_level)

    if settings.langsmith_api_key:
        import os

        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        logger.info("langsmith.enabled", extra={"event_type": "observability.langsmith", "project": settings.langsmith_project})

    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.05,
            environment=settings.ambiente,
        )
        logger.info("sentry.enabled", extra={"event_type": "observability.sentry"})

    logger.info("worker_startup_begin", extra={"event_type": "worker.start", "max_jobs": settings.arq_max_jobs})

    try:
        from app.core.redis_pool import get_redis_commands

        redis = await get_redis_commands()
        await redis.ping()
        ctx["redis"] = redis
    except Exception as e:
        logger.warning("worker_startup redis warmup falhou: %s", e)

    try:
        from app.agents.checkpointer import get_checkpointer

        checkpointer = await get_checkpointer()
        ctx["checkpointer"] = checkpointer
    except Exception as e:
        logger.warning("worker_startup checkpointer warmup falhou: %s", e)

    try:
        import httpx

        ctx["http"] = httpx.AsyncClient(timeout=30, follow_redirects=True)
    except Exception as e:
        logger.warning("worker_startup http warmup falhou: %s", e)

    logger.info("worker_startup_done")


async def ctx_shutdown(ctx):
    logger.info("worker_shutdown_begin")
    if "http" in ctx:
        await ctx["http"].aclose()
    try:
        from app.agents.checkpointer import close_checkpointer

        await close_checkpointer()
    except Exception:
        logger.warning("worker_shutdown close_checkpointer falhou", exc_info=True)
    logger.info("worker_shutdown_done")


async def _marcar_falhou(execucao_id: str, msg: str):
    from app.db.session import async_session_factory

    try:
        from app.services import ferramenta_service

        async with async_session_factory() as session:
            exec_obj = await ferramenta_service.buscar_execucao(session, execucao_id)
            if exec_obj and exec_obj.status not in ("concluida", "falhou", "cancelada"):
                await ferramenta_service.finalizar_falha(session, execucao_id, msg)
                await session.commit()
    except Exception:
        logger.exception("marcar_falhou falhou para execucao_id=%s", execucao_id)


async def _executar_job(ctx, handler_module: str, handler_fn: str, execucao_id: str):
    logger.info("workflow_start", extra={"event_type": "workflow.start", "execucao_id": execucao_id, "handler": f"{handler_module}.{handler_fn}", "try": ctx.get("job_try")})
    try:
        import importlib

        mod = importlib.import_module(handler_module)
        fn = getattr(mod, handler_fn)
        await fn(execucao_id, ctx=ctx)
        logger.info("workflow_completed", extra={"event_type": "workflow.completed", "execucao_id": execucao_id})
    except Exception as e:
        from app.core.excecoes import ErroPermanente, ErroTransitorio

        if isinstance(e, ErroTransitorio):
            defer = min(60 * ctx.get("job_try", 1), 600)
            logger.warning("workflow_transient", extra={"event_type": "workflow.retry", "execucao_id": execucao_id, "try": ctx.get("job_try"), "defer_s": defer, "err": str(e)})
            raise Retry(defer=defer) from e
        elif isinstance(e, ErroPermanente):
            logger.error("workflow_permanent_fail", extra={"event_type": "workflow.failed", "execucao_id": execucao_id, "err": str(e)})
            await _marcar_falhou(execucao_id, f"Erro: {e}")
        elif isinstance(e, asyncio.CancelledError):
            logger.info("workflow_cancelled", extra={"event_type": "workflow.cancelled", "execucao_id": execucao_id})
            await _marcar_falhou(execucao_id, "Execucao cancelada")
            raise
        else:
            logger.exception("workflow_unexpected", extra={"event_type": "workflow.failed", "execucao_id": execucao_id})
            await _marcar_falhou(execucao_id, "Erro interno do workflow")
            raise


async def executar_workflow(ctx, execucao_id: str):
    await _executar_job(ctx, "app.agents.workflow", "executar_workflow_completo", execucao_id)


async def retomar_workflow_job(ctx, execucao_id: str, acao: str, feedback: str | None):
    logger.info("Retomando workflow execucao_id=%s acao=%s", execucao_id, acao, extra={"event_type": "workflow.resumed", "execucao_id": execucao_id, "acao": acao})
    try:
        from app.agents.workflow import retomar_workflow

        await retomar_workflow(execucao_id, acao, feedback, ctx=ctx)
        logger.info("Retomada concluida execucao_id=%s", execucao_id, extra={"event_type": "workflow.completed", "execucao_id": execucao_id})
    except asyncio.CancelledError:
        logger.info("Retomada cancelada execucao_id=%s", execucao_id, extra={"event_type": "workflow.cancelled", "execucao_id": execucao_id})
        await _marcar_falhou(execucao_id, "Execucao cancelada")
        raise
    except Exception as e:
        logger.error("Retomada falhou execucao_id=%s: %s", execucao_id, e, extra={"event_type": "workflow.failed", "execucao_id": execucao_id})


async def executar_inlinks(ctx, execucao_id: str):
    await _executar_job(ctx, "app.agents.workflow_inlinks", "executar_workflow_inlinks", execucao_id)


async def executar_distribuir_inlinks(ctx, execucao_id: str):
    await _executar_job(ctx, "app.agents.workflow_inlinks_reversos", "executar_workflow_distribuir_inlinks", execucao_id)


async def executar_workflow_cwv(ctx, execucao_id: str):
    await _executar_job(ctx, "app.agents.cwv.workflow", "executar_workflow_cwv", execucao_id)


async def executar_workflow_parecer(ctx, execucao_id: str):
    await _executar_job(ctx, "app.agents.parecer.workflow", "executar_workflow_parecer", execucao_id)


async def executar_indexar_site(ctx, execucao_id: str):
    await _executar_job(ctx, "app.agents.workflow_indexar_site", "executar_workflow_indexar_site", execucao_id)


async def executar_consolidador_cwv(ctx, auditoria_id: str):
    """SPEC_CWV_Consolidador_Cross_URL: consolidação de auditoria (job direto)."""
    from app.agents.cwv.consolidador import executar_consolidacao

    await executar_consolidacao(auditoria_id)


class WorkerSettings:
    functions = [executar_workflow, retomar_workflow_job, executar_inlinks, executar_distribuir_inlinks, executar_workflow_cwv, executar_workflow_parecer, executar_indexar_site, executar_consolidador_cwv]  # noqa: RUF012
    on_startup = ctx_startup
    on_shutdown = ctx_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.arq_max_jobs
    job_timeout = settings.arq_job_timeout
    max_tries = 3
    keep_result = 7200
    health_check_interval = 30
    allow_abort_jobs = True
