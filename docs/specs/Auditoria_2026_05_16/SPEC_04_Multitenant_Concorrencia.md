# SPEC 04 — Multi-tenant: rate limit, cache e concorrência LLM

**Status:** a aplicar · **Escopo:** `dependencies`, `core/middleware`, `core/llm_guard`, `core/redis_pool`, `core/cache`, `core/embeddings` · **Severidade:** Alta para escalar além de 5 usuários ativos
**Cobre issues:** #8 (user cache process-local), #9 (rate limit process-local), #10 (LLM rate limit global), #11 (overly broad retry), #15 (pubsub conn única), #17 (embeddings fallback sequencial), #19 (semaphore dict race), #41 (pubsub state colliding cache)

**Depende de:** SPEC_01 e SPEC_03 aplicadas (secrets, créditos).

---

## 4.1 — User cache → Redis com TTL

### Problema (#8)
`dependencies.py:17-35` — dict global, process-local, race em eviction LRU.

### Fix
```python
# core/user_cache.py (novo)
import json
from app.core.redis_pool import get_redis_commands

USER_CACHE_TTL = 60  # segundos
USER_CACHE_PREFIX = "user:cache:"

async def get_user(usuario_id: str) -> dict | None:
    redis = await get_redis_commands()
    raw = await redis.get(f"{USER_CACHE_PREFIX}{usuario_id}")
    return json.loads(raw) if raw else None

async def set_user(usuario_id: str, usuario_dict: dict) -> None:
    redis = await get_redis_commands()
    await redis.set(
        f"{USER_CACHE_PREFIX}{usuario_id}",
        json.dumps(usuario_dict),
        ex=USER_CACHE_TTL,
    )

async def invalidate_user(usuario_id: str) -> None:
    redis = await get_redis_commands()
    await redis.delete(f"{USER_CACHE_PREFIX}{usuario_id}")
```

`dependencies.py:get_current_user` usa o helper. `auth_service.logout`, `alterar_senha`, admin-disable invocam `invalidate_user`.

---

## 4.2 — Rate limit → Redis sliding window

### Problema (#9)
`core/middleware.py:15-17` — `defaultdict(list)` process-local. N workers = N × budget. Sem eviction = leak.

### Fix
Algoritmo: Lua script atomicamente decrementa um sorted set (timestamps), conta itens na janela, retorna count.

```python
# core/rate_limit.py
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
redis.call("EXPIRE", key, janela)
return 1
"""

async def check_rate_limit_redis(key: str, max_requests: int, window_seconds: int) -> bool:
    redis = await get_redis_commands()
    agora_ms = int(time.time() * 1000)
    janela_ms = window_seconds * 1000
    resultado = await redis.eval(
        SLIDING_WINDOW_SCRIPT, 1, key, agora_ms, janela_ms, max_requests
    )
    return resultado == 1
```

Substituir `check_rate_limit` em middleware.py. Eliminar `_rate_limit_store` global.

**Chave inclui user_id quando autenticado:**
```python
def rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    async def _check(request: Request, usuario: Usuario | None = Depends(get_optional_user)):
        ip = get_client_ip(request)
        user_id = str(usuario.id) if usuario else None
        # chave preferencialmente por user; fallback IP para login pre-auth
        bucket = user_id or f"ip:{ip}"
        key = f"rl:{key_prefix}:{bucket}"
        if not await check_rate_limit_redis(key, max_requests, window_seconds):
            raise RateLimitExcedido()
    return _check
```

---

## 4.3 — LLM rate limit por tenant

### Problema (#10, #19)
`llm_guard.py:13` — `_last_llm_call_time` global compartilhado. `_llm_per_user_semaphores` dict sem lock.

### Fix
Token bucket por tenant no Redis:

```python
# core/llm_guard.py

LLM_BUCKET_SCRIPT = """
local key = KEYS[1]
local agora = tonumber(ARGV[1])
local capacidade = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])  -- tokens/segundo

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1]) or capacidade
local last_refill = tonumber(bucket[2]) or agora

local elapsed = math.max(0, agora - last_refill)
tokens = math.min(capacidade, tokens + elapsed * refill_rate)

if tokens < 1 then
    redis.call("HSET", key, "tokens", tokens, "last_refill", agora)
    return -1  -- sem tokens; cliente faz backoff
end

redis.call("HSET", key, "tokens", tokens - 1, "last_refill", agora)
redis.call("EXPIRE", key, 300)
return 1
"""

async def adquirir_token_llm(usuario_id: str) -> bool:
    redis = await get_redis_commands()
    capacidade = 5  # 5 requests
    refill = 0.5   # 0.5 token/s = 30/min
    r = await redis.eval(
        LLM_BUCKET_SCRIPT, 1,
        f"llm:bucket:{usuario_id}",
        time.time(), capacidade, refill,
    )
    return r == 1

async def chamada_llm_segura(chain, input_data, usuario_id: str):
    # Wait until token available
    for _ in range(60):  # max 60s wait
        if await adquirir_token_llm(usuario_id):
            break
        await asyncio.sleep(1)
    else:
        raise RateLimitExcedido("LLM bucket vazio")
    async with _llm_global_semaphore:
        return await chain.ainvoke(input_data)
```

Eliminar `_llm_per_user_semaphores` dict e `_last_llm_call_time` global.

Manter `_llm_global_semaphore` (process-local) como segunda barreira contra spike por worker.

---

## 4.4 — Retry: catch específico (não `Exception`)

### Problema (#11)
`llm_guard.py:56-62` — `except Exception` engole bugs (KeyError, TypeError) e faz retry com sleep de até 3min, mascarando código quebrado.

### Fix
```python
import httpx
from openai import RateLimitError, APITimeoutError, APIConnectionError

LLM_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
)

async def chamada_llm_com_retry(chain, input_data, usuario_id):
    for tentativa in range(MAX_RETRIES + 1):
        try:
            return await chamada_llm_segura(chain, input_data, usuario_id)
        except LLM_RETRYABLE as e:
            if tentativa == MAX_RETRIES:
                raise WorkflowError(...) from e
            delay = min(2 ** tentativa, 60)
            logger.warning("LLM retry %d/%d em %ds: %s", tentativa+1, MAX_RETRIES, delay, e)
            await asyncio.sleep(delay)
        # NÃO captura Exception genérica — bugs propagam imediatamente
```

---

## 4.5 — Redis: separar pool de comandos vs pubsub

### Problema (#15, #41)
`redis_pool.py:get_redis_pubsub()` retorna a MESMA conexão para `pubsub.subscribe()` (em SSE) e `cache_get/set_json` (em scraper). Pubsub muda estado da conexão.

### Fix
```python
# core/redis_pool.py
import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

_commands_pool: ConnectionPool | None = None
_commands_lock = asyncio.Lock()

async def get_redis_commands() -> aioredis.Redis:
    """Cliente para get/set/eval. Multi-conexão via pool."""
    global _commands_pool
    if _commands_pool is None:
        async with _commands_lock:
            if _commands_pool is None:
                _commands_pool = ConnectionPool.from_url(
                    settings.redis_url, decode_responses=True, max_connections=50,
                )
    return aioredis.Redis(connection_pool=_commands_pool)

async def get_pubsub_client() -> aioredis.Redis:
    """Cliente NOVO por subscriber. Caller deve fechar."""
    return aioredis.from_url(settings.redis_url, decode_responses=True)
```

`core/cache.py` usa `get_redis_commands`. `routers/ferramentas.py:stream_progresso` usa `get_pubsub_client()` por SSE (e fecha ao terminar).

---

## 4.6 — Embeddings fallback: split batch, não sequencial

### Problema (#17)
`embeddings.py:80-89` — batch falhou, faz N chamadas individuais sequenciais. Para batch de 100, isso vira 100 round-trips lentos.

### Fix recursivo
```python
async def _gerar_batch_com_split(textos: list[str], usuario_id: str, depth: int = 0) -> list[list[float] | None]:
    if not textos:
        return []
    if depth > 5:
        # Fallback final: ainda assim 1-a-1, mas alertando
        logger.error("Embedding split atingiu profundidade max; %d textos serao 1-a-1", len(textos))
        ...

    try:
        return await embeddings_model.aembed_documents(textos)
    except Exception as e:
        if len(textos) == 1:
            logger.warning("Embedding single falhou: %s", e)
            return [None]
        meio = len(textos) // 2
        a, b = await asyncio.gather(
            _gerar_batch_com_split(textos[:meio], usuario_id, depth+1),
            _gerar_batch_com_split(textos[meio:], usuario_id, depth+1),
        )
        return a + b
```

Substituir o bloco de fallback em `gerar_embeddings_batch`.

---

## 4.7 — Workflow checkpointer pool (sneak peek; detalhado em SPEC 06)

Trocar `_get_checkpointer()` (cria conexão fresca por execution) por pool compartilhado — detalhado em **SPEC 06 §6.1**.

---

## 4.8 — Worker scaling docs

Adicionar `docs/deploy.md`:
```markdown
## Workers em produção
Roda N workers para escalar concorrência:
- arq.WorkerSettings.max_jobs = 20 (cada worker)
- Suporte total = N × 20 workflows simultâneos
- Recomendado: 1 worker por 2 CPUs disponíveis
- systemd unit ou Kubernetes Deployment com replicas=4 → 80 workflows

NOTA: rate limit/credits são globais (Redis), então scaling é seguro.
```

---

## Critério de pronto

- [ ] User cache em Redis com TTL e invalidação explícita em logout
- [ ] Rate limit em Redis (Lua sliding window); chave por user_id quando auth
- [ ] LLM token bucket por tenant; sem global timer
- [ ] Retry LLM captura apenas erros transitórios documentados
- [ ] Pool de comandos separado de pubsub; SSE usa cliente próprio
- [ ] Embeddings fallback usa split recursivo
- [ ] `docs/deploy.md` cobre scaling

## Testes
- 50 usuários concorrentes em rate limit endpoint: ~50 × max_requests respostas 200, demais 429.
- 5 workers paralelos × 10 LLM calls cada: budget respeitado globalmente via Redis.
- SSE de 20 usuários simultâneos: cada um vê apenas seus eventos.

## Riscos
- Redis vira ponto único de falha — documentar HA (sentinel ou cluster).
- Lua scripts: testar em Redis 7+ (sintaxe compatível).
- Cache TTL 60s em user info: admin precisa invalidar explicitamente ao desabilitar conta.
