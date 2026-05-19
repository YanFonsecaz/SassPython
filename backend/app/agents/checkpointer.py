"""Pool de conexoes compartilhado para o checkpointer do LangGraph.

Padrao de producao (Context7 / LangGraph docs):
  - usar `AsyncConnectionPool` (psycopg-pool) em vez de `from_conn_string` por execucao
  - inicializar uma unica vez no startup do worker (worker.ctx_startup)
  - reusar a mesma instancia entre todas as execucoes do mesmo worker

A funcao `get_checkpointer()` retorna a instancia singleton (criando preguicosamente
se nao foi inicializada). Workers ARQ podem chamar no on_startup; rotas e testes
podem chamar sob demanda.
"""

import asyncio
import logging
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.config import settings

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_setup_done = False
_lock = asyncio.Lock()


async def get_checkpointer() -> AsyncPostgresSaver:
    """Retorna a instancia singleton do checkpointer.

    Cria pool psycopg e roda `setup()` na primeira invocacao. Subsequentes
    chamadas retornam a mesma instancia.
    """
    global _pool, _checkpointer, _setup_done
    if _checkpointer is not None:
        return _checkpointer

    async with _lock:
        if _checkpointer is not None:
            return _checkpointer

        db_url = settings.database_url.replace("+asyncpg", "")
        _pool = AsyncConnectionPool(conninfo=db_url, max_size=10, open=False)
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)
        if not _setup_done:
            await _checkpointer.setup()
            _setup_done = True
        logger.info("checkpointer.singleton ready (pool max_size=10)")

    return _checkpointer


async def close_checkpointer() -> None:
    """Fecha pool. Chamar em worker on_shutdown / app lifespan stop."""
    global _pool, _checkpointer
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            logger.warning("checkpointer.close falhou", exc_info=True)
    _pool = None
    _checkpointer = None


def get_checkpointer_from_ctx(ctx: dict[str, Any] | None) -> AsyncPostgresSaver | None:
    """Helper para uso dentro dos workflows.

    Prefere o checkpointer ja inicializado no ctx do ARQ (warmup feito).
    Retorna None se nao houver — caller deve usar `get_checkpointer()` como fallback.
    """
    if ctx and "checkpointer" in ctx:
        return ctx["checkpointer"]
    return None
