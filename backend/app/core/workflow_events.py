import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _channel(execucao_id: str) -> str:
    return f"workflow:{execucao_id}"


async def publish_event(
    execucao_id: str,
    event_type: str,
    node: str,
    detail: str,
    data: dict[str, Any] | None = None,
) -> None:
    try:
        from app.core.redis_pool import get_redis_commands

        redis = await get_redis_commands()
        payload = {
            "type": event_type,
            "node": node,
            "detail": detail,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if data:
            payload["data"] = data
        await redis.publish(_channel(execucao_id), json.dumps(payload))
    except Exception:
        logger.warning("Falha ao publicar evento workflow para %s", execucao_id, exc_info=True)
