"""Helpers de cache via Redis para resultados de scrape, embeddings e robots.txt."""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def _client():
    from app.core.redis_pool import get_redis_commands

    return await get_redis_commands()


async def cache_get_json(key: str) -> Any | None:
    try:
        client = await _client()
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.debug("cache_get_json falhou key=%s: %s", key, e)
        return None


async def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        client = await _client()
        await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
    except Exception as e:
        logger.debug("cache_set_json falhou key=%s: %s", key, e)


async def cache_get_str(key: str) -> str | None:
    try:
        client = await _client()
        return await client.get(key)
    except Exception as e:
        logger.debug("cache_get_str falhou key=%s: %s", key, e)
        return None


async def cache_set_str(key: str, value: str, ttl_seconds: int) -> None:
    try:
        client = await _client()
        await client.set(key, value, ex=ttl_seconds)
    except Exception as e:
        logger.debug("cache_set_str falhou key=%s: %s", key, e)
