import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.usuario import Usuario
from app.schemas.inlinks import CustoInlinksResponse, InlinksRequest
from app.services.ferramenta_service import (
    CUSTO_BASE_INLINKS,
    CUSTO_MAX_INLINKS,
    CUSTO_POR_URL_INLINKS,
    calcular_custo_inlinks,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/inlinks-automaticos", status_code=202)
async def criar_inlinks(
    body: InlinksRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("inlinks", max_requests=3, window_seconds=60)),
) -> dict[str, Any]:
    if not body.pilar_url and not body.pilar_markdown:
        raise HTTPException(status_code=422, detail="Forneça pilar_url ou pilar_markdown")

    calcular_custo_inlinks(len(body.candidatas_urls))

    from app.services import credito_service

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), CUSTO_BASE_INLINKS)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc

    entrada = body.model_dump()
    execucao = await _criar_execucao_inlinks(db, str(usuario.id), entrada)

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_inlinks", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        logger.error("Falha ao enfileirar inlinks: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), CUSTO_BASE_INLINKS)
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


@router.get("/inlinks-automaticos/custo", response_model=CustoInlinksResponse)
async def custo_inlinks_endpoint(
    n_urls: int = 5,
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    custo = calcular_custo_inlinks(n_urls)
    return {
        "custo_base": CUSTO_BASE_INLINKS,
        "custo_por_url": CUSTO_POR_URL_INLINKS,
        "custo_maximo": CUSTO_MAX_INLINKS,
        "custo_estimado": custo,
        "n_urls": n_urls,
    }


async def _criar_execucao_inlinks(db, usuario_id: str, entrada: dict[str, Any]):
    from app.config import settings
    from app.models.execucao_ferramenta import ExecucaoFerramenta

    entrada_json = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in entrada.items()}
    execucao = ExecucaoFerramenta(
        usuario_id=usuario_id,
        ferramenta="inlinks_automaticos",
        status="pendente",
        entrada_json=entrada_json,
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=settings.workflow_timeout_segundos),
    )
    db.add(execucao)
    await db.flush()
    return execucao
