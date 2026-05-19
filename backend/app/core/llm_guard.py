import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.excecoes import ErroPermanente, RateLimitExcedido

logger = logging.getLogger(__name__)

RETRYABLE_ERRORS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
)

MAX_RETRIES = 5
BACKOFF_BASE = 2

LLM_BUCKET_SCRIPT = """
local key = KEYS[1]
local agora = tonumber(ARGV[1])
local capacidade = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1]) or capacidade
local last_refill = tonumber(bucket[2]) or agora

local elapsed = math.max(0, agora - last_refill)
tokens = math.min(capacidade, tokens + elapsed * refill_rate)

if tokens < 1 then
    redis.call("HSET", key, "tokens", tokens, "last_refill", agora)
    return -1
end

redis.call("HSET", key, "tokens", tokens - 1, "last_refill", agora)
redis.call("EXPIRE", key, 300)
return 1
"""


async def _adquirir_token_llm(usuario_id: str, model: str = "default") -> bool:
    from app.core.redis_pool import get_redis_commands

    redis = await get_redis_commands()
    capacidade = 5
    refill = 0.5
    try:
        r = await redis.eval(
            LLM_BUCKET_SCRIPT, 1,
            f"llm:bucket:{usuario_id}:{model}",
            time.time(), capacidade, refill,
        )
        return r == 1
    except Exception as e:
        logger.warning("LLM bucket redis falhou, permitindo (fail-open): %s", e)
        return True


class WorkflowError(ErroPermanente):
    pass


async def _aguardar_token_llm(usuario_id: str, model: str = "default", max_wait_seconds: int = 30) -> None:
    inicio = time.monotonic()
    for _ in range(max_wait_seconds):
        if await _adquirir_token_llm(usuario_id, model):
            duracao = time.monotonic() - inicio
            if duracao > 5:
                logger.info(
                    "llm_bucket_wait",
                    extra={"event_type": "llm.bucket.wait", "usuario_id": usuario_id, "duracao_s": duracao},
                )
            return
        await asyncio.sleep(1)
    raise RateLimitExcedido("LLM bucket vazio apos 30s, tente novamente")


def _e_status_retryable(exc: Exception) -> bool:
    try:
        import openai
    except ImportError:
        return False
    if isinstance(exc, openai.APIStatusError):
        return 500 <= exc.status_code < 600
    return False


def _get_retryable_openai():
    try:
        import openai
        return openai
    except ImportError:
        return None


async def chamada_llm_com_retry(chain, input_data, usuario_id: str):
    openai = _get_retryable_openai()
    model = getattr(chain, "model_name", None) or getattr(chain, "model", None) or "default"
    for tentativa in range(MAX_RETRIES + 1):
        try:
            await _aguardar_token_llm(usuario_id, model)
            return await chain.ainvoke(input_data)
        except RETRYABLE_ERRORS as e:
            if tentativa == MAX_RETRIES:
                raise WorkflowError(f"LLM falhou apos {MAX_RETRIES + 1} tentativas: {e}") from e
            delay = min(BACKOFF_BASE ** tentativa, 60)
            logger.warning("LLM retry %d/%d em %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
            await asyncio.sleep(delay)
        except Exception as e:
            if openai and isinstance(e, openai.RateLimitError):
                if tentativa == MAX_RETRIES:
                    raise WorkflowError(f"LLM 429 apos {MAX_RETRIES + 1} tentativas: {e}") from e
                delay = min(BACKOFF_BASE ** tentativa, 60)
                logger.warning("LLM 429 retry %d/%d em %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
                await asyncio.sleep(delay)
                continue
            if openai and isinstance(e, openai.APIStatusError):
                if _e_status_retryable(e) and tentativa < MAX_RETRIES:
                    delay = min(BACKOFF_BASE ** tentativa, 60)
                    logger.warning("LLM 5xx retry %d/%d em %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
                    await asyncio.sleep(delay)
                    continue
                raise WorkflowError(f"LLM erro nao-retryable: {e}") from e
            raise


async def chamada_llm_mensagem_com_retry(llm, mensagens: list[Any], usuario_id: str):
    openai = _get_retryable_openai()
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None) or "default"
    for tentativa in range(MAX_RETRIES + 1):
        try:
            await _aguardar_token_llm(usuario_id, model)
            return await llm.ainvoke(mensagens)
        except RETRYABLE_ERRORS as e:
            if tentativa == MAX_RETRIES:
                raise WorkflowError(f"LLM falhou apos {MAX_RETRIES + 1} tentativas: {e}") from e
            delay = min(BACKOFF_BASE ** tentativa, 60)
            logger.warning("LLM retry %d/%d em %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
            await asyncio.sleep(delay)
        except Exception as e:
            if openai and isinstance(e, openai.RateLimitError):
                if tentativa == MAX_RETRIES:
                    raise WorkflowError(f"LLM 429 apos {MAX_RETRIES + 1} tentativas: {e}") from e
                delay = min(BACKOFF_BASE ** tentativa, 60)
                logger.warning("LLM 429 retry %d/%d em %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
                await asyncio.sleep(delay)
                continue
            if openai and isinstance(e, openai.APIStatusError):
                if _e_status_retryable(e) and tentativa < MAX_RETRIES:
                    delay = min(BACKOFF_BASE ** tentativa, 60)
                    logger.warning("LLM 5xx retry %d/%d em %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
                    await asyncio.sleep(delay)
                    continue
                raise WorkflowError(f"LLM erro nao-retryable: {e}") from e
            raise
