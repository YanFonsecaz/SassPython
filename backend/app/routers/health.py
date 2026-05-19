import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.redis_pool import get_redis_commands

logger = logging.getLogger(__name__)
router = APIRouter()

_ARQ_HEALTH_KEY = "arq:queue:health-check"


@router.get("/health/worker")
async def health_worker():
    redis = await get_redis_commands()
    raw = await redis.get(_ARQ_HEALTH_KEY)
    if not raw:
        raise HTTPException(status_code=503, detail="Worker sem heartbeat")
    return {"status": "ok", "last_heartbeat": raw}


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request):
    from app.config import settings

    allowed = settings.metrics_allowlist or []
    if allowed and request.client and request.client.host not in allowed:
        raise HTTPException(status_code=403, detail="Forbidden")

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
