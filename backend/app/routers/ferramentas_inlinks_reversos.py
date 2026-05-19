import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.usuario import Usuario
from app.schemas.inlinks_reversos import CustoDistribuirInlinksResponse, DistribuirInlinksRequest
from app.services.ferramenta_service import (
    CUSTO_BASE_DISTRIBUIR_INLINKS,
    CUSTO_MAX_DISTRIBUIR_INLINKS,
    CUSTO_POR_CANDIDATA_DISTRIBUIR,
    calcular_custo_distribuir_inlinks,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/distribuir-inlinks", status_code=202)
async def criar_distribuir_inlinks(
    body: DistribuirInlinksRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("distribuir_inlinks", max_requests=3, window_seconds=60)),
) -> dict[str, Any]:
    from app.core.scraper import _normalizar_url

    alvo_norm = _normalizar_url(body.url_alvo)
    for url in body.candidatas_urls:
        if _normalizar_url(url) == alvo_norm:
            raise HTTPException(status_code=422, detail="A URL alvo nao pode estar na lista de candidatas")

    calcular_custo_distribuir_inlinks(len(body.candidatas_urls))

    from app.services import credito_service

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), CUSTO_BASE_DISTRIBUIR_INLINKS)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc

    entrada = body.model_dump()
    execucao = await _criar_execucao_distribuir(db, str(usuario.id), entrada)

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_distribuir_inlinks", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        logger.error("Falha ao enfileirar distribuir inlinks: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), CUSTO_BASE_DISTRIBUIR_INLINKS)
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


@router.get("/distribuir-inlinks/custo", response_model=CustoDistribuirInlinksResponse)
async def custo_distribuir_inlinks_endpoint(
    n_candidatas: int = 5,
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    custo = calcular_custo_distribuir_inlinks(n_candidatas)
    return {
        "custo_base": CUSTO_BASE_DISTRIBUIR_INLINKS,
        "custo_por_candidata": CUSTO_POR_CANDIDATA_DISTRIBUIR,
        "custo_maximo": CUSTO_MAX_DISTRIBUIR_INLINKS,
        "custo_estimado": custo,
        "n_candidatas": n_candidatas,
    }


async def _criar_execucao_distribuir(db, usuario_id: str, entrada: dict[str, Any]):
    from app.config import settings
    from app.models.execucao_ferramenta import ExecucaoFerramenta

    entrada_json = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in entrada.items()}
    timeout = getattr(settings, "workflow_distribuir_inlinks_timeout", 1800)
    execucao = ExecucaoFerramenta(
        usuario_id=usuario_id,
        ferramenta="distribuir_inlinks",
        status="pendente",
        entrada_json=entrada_json,
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=timeout),
    )
    db.add(execucao)
    await db.flush()
    return execucao
