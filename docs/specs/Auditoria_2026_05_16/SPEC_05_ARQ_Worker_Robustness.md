# SPEC 05 — ARQ Workers: retry, cancel real, timeouts, startup

**Status:** a aplicar · **Escopo:** `worker.py`, `routers/ferramentas*.py` (cancelamento), `config.py` · **Severidade:** Média-Alta
**Cobre issues:** #12 (swallow exceptions sem retry), #13 (cancel não cancela), #16 (job_timeout < workflow_timeout), #31 (on_startup sem warmup)

**Depende de:** SPEC_01.

---

## 5.1 — Worker handler: classificar erros, usar `Retry`

### Problema
`worker.py:18-26` engole tudo via `except Exception: logger.error`. Job marca como ok no ARQ. Sem retry. Se workflow crashou antes de marcar `falhou` no DB, fica `executando` para sempre.

### Fix
```python
# worker.py
from arq import Retry
from app.config import settings
from app.core.excecoes import (
    ErroTransitorio,  # criar: rate limit, http timeout, llm temporario
    ErroPermanente,   # criar: invalid input, syntax, bug
)

async def executar_workflow(ctx, execucao_id: str):
    logger.info("workflow_start", extra={"execucao_id": execucao_id, "try": ctx.get("job_try")})
    try:
        from app.agents.workflow import executar_workflow_completo
        await executar_workflow_completo(execucao_id)
        logger.info("workflow_done", extra={"execucao_id": execucao_id})

    except ErroTransitorio as e:
        # Rate limit, 5xx do LLM, timeouts de rede
        defer = min(60 * ctx.get("job_try", 1), 600)  # 1min, 2min, ..., 10min max
        logger.warning("workflow_transient retry=%s defer=%ds: %s", ctx.get("job_try"), defer, e)
        raise Retry(defer=defer) from e

    except ErroPermanente as e:
        # Bug, input invalido, dados corrompidos — não retry
        logger.error("workflow_permanent_fail", extra={"execucao_id": execucao_id, "err": str(e)})
        await _marcar_falhou(execucao_id, f"Erro: {e}")
        # NÃO faz raise — job marca como sucesso na fila (deu o que dava)

    except Exception as e:
        # Inesperado: log com stack, marca DB como falha, deixa ARQ marcar como falha
        logger.exception("workflow_unexpected", extra={"execucao_id": execucao_id})
        await _marcar_falhou(execucao_id, "Erro interno do workflow")
        raise  # ARQ marca como falha; pode tentar de novo via max_tries

async def _marcar_falhou(execucao_id: str, msg: str):
    """Garante que o DB reflete falha mesmo se workflow não conseguiu."""
    from app.db.session import async_session_factory
    from app.services import ferramenta_service
    async with async_session_factory() as session:
        exec_obj = await ferramenta_service.buscar_execucao(session, execucao_id)
        if exec_obj and exec_obj.status not in ("concluida", "falhou", "cancelada"):
            await ferramenta_service.finalizar_falha(session, execucao_id, msg)
            await session.commit()
```

```python
# core/excecoes.py
class ErroTransitorio(Exception):
    """Falha temporaria: pode ser retentada."""

class ErroPermanente(Exception):
    """Falha permanente: nao retentar."""
```

Atualizar workflows para usar essas exceções (mapear de httpx/openai/etc).

### `WorkerSettings`
```python
class WorkerSettings:
    functions = [...]
    on_startup = ctx_startup
    on_shutdown = ctx_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.arq_max_jobs
    job_timeout = settings.arq_job_timeout
    max_tries = 3                    # ARQ retry padrão
    keep_result = 7200               # 2h: tempo de retenção do resultado
    health_check_interval = 30       # heartbeat
```

---

## 5.2 — Timeouts: alinhar job_timeout com workflow

### Problema (#16)
`arq_job_timeout=900` (15min) mas `workflow_distribuir_inlinks_timeout=1800` (30min). Job morre antes do workflow terminar.

### Fix
Política: `job_timeout > maior workflow_timeout × 1.2` para margem.

```python
# config.py
arq_max_jobs: int = 20
arq_job_timeout: int = 2400  # 40min: cobre distribuir 30min + margem

workflow_gerar_artigo_timeout: int = 600
workflow_inlinks_timeout: int = 900
workflow_distribuir_inlinks_timeout: int = 1800
```

Cada workflow respeita seu timeout interno via `asyncio.wait_for` (já faz). ARQ é o backstop.

---

## 5.3 — Cancelamento REAL via `Job.abort()`

### Problema (#13)
`ferramenta_service.cancelar_execucao` só atualiza DB. Worker continua rodando, gasta LLM e tempo.

### Fix

```python
# routers/ferramentas.py
@router.post("/historico/{execucao_id}/cancelar")
async def cancelar_execucao_endpoint(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao or str(execucao.usuario_id) != str(usuario.id):
        raise HTTPException(404, "Execucao nao encontrada")

    if execucao.status in ("concluida", "falhou", "cancelada"):
        raise HTTPException(400, "Execucao ja finalizada")

    # 1) Abort na fila ARQ (se ainda lá)
    if execucao.job_id:
        try:
            from arq.jobs import Job
            from app.core.redis_pool import get_redis_pool
            redis = await get_redis_pool()
            job = Job(execucao.job_id, redis=redis)
            aborted = await job.abort(timeout=5)  # mata se em execução
            logger.info("job_abort", extra={"job_id": execucao.job_id, "aborted": aborted})
        except Exception:
            logger.warning("Falha ao abortar job", exc_info=True)

    # 2) Liberar reserva de créditos (SPEC 03)
    if execucao.creditos_reservados:
        await credito_service.liberar_reserva(db, str(usuario.id), execucao.creditos_reservados)

    # 3) Marcar DB como cancelada
    execucao.status = "cancelada"
    execucao.creditos_cobrados = 0
    execucao.concluida_em = datetime.now(UTC)
    await db.commit()

    return {"status": "cancelada", "creditos_cobrados": 0}
```

Worker deve respeitar abort:
- `arq.Job.abort` envia signal de cancelamento.
- Workflows com `asyncio.wait_for` levantam `CancelledError`.
- Em `except asyncio.CancelledError`: marcar DB como `cancelada`, liberar reserva, re-raise.

```python
# agents/workflow.py
async def executar_workflow_completo(execucao_id: str):
    try:
        async with _get_checkpointer() as cp:
            workflow = criar_workflow(checkpointer=cp)
            await asyncio.wait_for(_run_workflow(workflow, ...), timeout=...)
    except asyncio.CancelledError:
        await _marcar_cancelado(execucao_id)
        raise
    except TimeoutError:
        ...
```

---

## 5.4 — `on_startup` real (warmup de pools)

### Problema (#31)
`worker.py:10-11` — `on_startup` só faz log. Sem prewarming. Cada job recria conexões.

### Fix
```python
# worker.py
async def ctx_startup(ctx):
    """Inicializa pools que serão reutilizados em todos os jobs."""
    logger.info("worker_startup_begin")

    # 1) Redis commands pool
    from app.core.redis_pool import get_redis_commands
    ctx["redis"] = await get_redis_commands()
    await ctx["redis"].ping()

    # 2) Checkpointer pool (LangGraph)
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool
    from app.config import settings

    db_url = settings.database_url.replace("+asyncpg", "")
    ctx["checkpointer_pool"] = AsyncConnectionPool(
        conninfo=db_url, max_size=10, open=False,
    )
    await ctx["checkpointer_pool"].open()
    ctx["checkpointer"] = AsyncPostgresSaver(ctx["checkpointer_pool"])
    await ctx["checkpointer"].setup()

    # 3) HTTP client compartilhado (scraping, HIBP, etc.)
    import httpx
    ctx["http"] = httpx.AsyncClient(timeout=30, follow_redirects=True)

    logger.info("worker_startup_done", extra={"max_jobs": settings.arq_max_jobs})

async def ctx_shutdown(ctx):
    logger.info("worker_shutdown_begin")
    if "http" in ctx:
        await ctx["http"].aclose()
    if "checkpointer_pool" in ctx:
        await ctx["checkpointer_pool"].close()
    if "redis" in ctx:
        await ctx["redis"].close()
    logger.info("worker_shutdown_done")
```

Workflows recebem `ctx` e usam `ctx["checkpointer"]`, `ctx["http"]`, etc. — eliminam o `async with from_conn_string` em cada execução.

```python
# worker.py
async def executar_workflow(ctx, execucao_id: str):
    from app.agents.workflow import executar_workflow_completo
    await executar_workflow_completo(execucao_id, ctx=ctx)
```

```python
# agents/workflow.py
async def executar_workflow_completo(execucao_id: str, ctx: dict | None = None):
    if ctx and "checkpointer" in ctx:
        checkpointer = ctx["checkpointer"]
        workflow = criar_workflow(checkpointer=checkpointer)
        # ... resto do código ...
    else:
        # fallback legacy: comportamento antigo
        async with _get_checkpointer() as cp:
            ...
```

---

## 5.5 — Health check e métricas

ARQ tem `health_check_interval` — habilitar. Plus, expor endpoint `/health/worker` (no API) que consulta Redis para saber se há heartbeat recente:

```python
# routers/health.py
@router.get("/health/worker")
async def health_worker():
    redis = await get_redis_commands()
    health_key = "arq:health-check"  # arq escreve aqui
    raw = await redis.get(health_key)
    if not raw:
        raise HTTPException(503, "Worker sem heartbeat")
    return {"status": "ok", "last_heartbeat": raw}
```

Plus: counter de jobs/min, fila length, jobs in_progress — métricas para alerting.

---

## Verificação

### Teste 1: retry transitório
- Mock httpx para retornar 503 nas primeiras 2 tentativas, 200 na terceira.
- Submeter job → status `executando` → após ~60s → `executando` → após ~120s → `concluida`.
- Logs mostram 2 `workflow_transient retry`.

### Teste 2: erro permanente sem retry
- Submeter job com input inválido (`url_alvo="not-a-url"`).
- Workflow levanta `ErroPermanente`.
- DB marca `falhou` imediatamente; sem retry.

### Teste 3: cancelamento real
- Submeter job longo (10min).
- Após 30s, chamar `/cancelar`.
- Worker log: `job_abort aborted=true`. Workflow para. LLM não é mais chamado.
- DB `cancelada`, créditos liberados.

### Teste 4: warmup
- Restart worker.
- Primeiro job termina em tempo similar ao décimo (sem overhead de conexão).

---

## Critério de pronto

- [ ] `ErroTransitorio` / `ErroPermanente` definidos
- [ ] Worker classifica e usa `Retry(defer=...)`
- [ ] `job_timeout = 2400`s (40min)
- [ ] `cancelar_execucao` chama `Job.abort()`
- [ ] Workflows respeitam `CancelledError`
- [ ] `on_startup` cria pools de Redis, checkpointer, http
- [ ] Pools usados via `ctx` nos handlers
- [ ] `/health/worker` retorna 200 se worker está vivo

## Riscos
- `Job.abort()` requer ARQ >= 0.25; nosso pyproject já tem 0.26. OK.
- Workflows com side effects parciais precisam revisar idempotência ao cancelar (ex.: já gravou InlinkSugerido) — documentar.
- Warmup adiciona ~2-3s ao startup. Aceitável.
