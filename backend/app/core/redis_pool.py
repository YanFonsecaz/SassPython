from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from redis.asyncio.connection import ConnectionPool

from app.config import settings

if TYPE_CHECKING:
    from arq import ArqRedis

logger = logging.getLogger(__name__)

_arq_pool: ArqRedis | None = None
_arq_lock = asyncio.Lock()

_commands_pool: ConnectionPool | None = None
_commands_lock = asyncio.Lock()


async def get_redis_pool():
    global _arq_pool
    if _arq_pool is not None:
        return _arq_pool
    async with _arq_lock:
        if _arq_pool is None:
            _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def get_redis_commands() -> aioredis.Redis:
    global _commands_pool
    if _commands_pool is not None:
        return aioredis.Redis(connection_pool=_commands_pool)
    async with _commands_lock:
        if _commands_pool is None:
            _commands_pool = ConnectionPool.from_url(
                settings.redis_url, decode_responses=True, max_connections=50,
            )
    return aioredis.Redis(connection_pool=_commands_pool)


async def get_pubsub_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def close_redis_pool():
    global _arq_pool, _commands_pool
    if _arq_pool is not None:
        with contextlib.suppress(Exception):
            await _arq_pool.close()
        _arq_pool = None
    if _commands_pool is not None:
        with contextlib.suppress(Exception):
            _commands_pool.disconnect()
        _commands_pool = None
