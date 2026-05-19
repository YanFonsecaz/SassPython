"""Rate limit via Redis sliding window (Lua script atomico)."""
import logging
import time

logger = logging.getLogger(__name__)

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local agora = tonumber(ARGV[1])
local janela = tonumber(ARGV[2])
local limite = tonumber(ARGV[3])

redis.call("ZREMRANGEBYSCORE", key, 0, agora - janela)
local count = redis.call("ZCARD", key)
if count >= limite then
    return 0
end
redis.call("ZADD", key, agora, agora)
redis.call("EXPIRE", key, math.ceil(janela / 1000))
return 1
"""


async def check_rate_limit_redis(key: str, max_requests: int, window_seconds: int) -> bool:
    from app.core.redis_pool import get_redis_commands

    redis = await get_redis_commands()
    agora_ms = int(time.time() * 1000)
    janela_ms = window_seconds * 1000
    try:
        resultado = await redis.eval(
            SLIDING_WINDOW_SCRIPT, 1, key, agora_ms, janela_ms, max_requests
        )
        if resultado == 0:
            logger.info(
                "rate_limit_exceeded",
                extra={
                    "event_type": "rate_limit.exceeded",
                    "key": key,
                    "max_requests": max_requests,
                    "window_seconds": window_seconds,
                },
            )
        return resultado == 1
    except Exception as e:
        logger.warning("rate_limit_redis falhou, permitindo (fail-open): %s", e)
        return True
