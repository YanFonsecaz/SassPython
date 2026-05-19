"""User cache via Redis com TTL e invalidacao explicita."""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

USER_CACHE_TTL = 60
USER_CACHE_PREFIX = "user:cache:"


async def get_user(usuario_id: str) -> dict[str, Any] | None:
    from app.core.redis_pool import get_redis_commands

    redis = await get_redis_commands()
    raw = await redis.get(f"{USER_CACHE_PREFIX}{usuario_id}")
    return json.loads(raw) if raw else None


async def set_user(usuario_id: str, usuario_dict: dict[str, Any]) -> None:
    from app.core.redis_pool import get_redis_commands

    redis = await get_redis_commands()
    await redis.set(
        f"{USER_CACHE_PREFIX}{usuario_id}",
        json.dumps(usuario_dict),
        ex=USER_CACHE_TTL,
    )


async def invalidate_user(usuario_id: str) -> None:
    from app.core.redis_pool import get_redis_commands

    redis = await get_redis_commands()
    await redis.delete(f"{USER_CACHE_PREFIX}{usuario_id}")
