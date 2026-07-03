import asyncio
import contextlib
import hashlib
import json
import logging
import math
from collections.abc import Awaitable, Callable

import numpy as np
from numpy.linalg import norm as _np_norm

from app.config import settings
from app.core.cache import cache_get_json, cache_set_json

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100
_EMBED_CACHE_TTL = 30 * 24 * 3600  # 30 dias


class EmbeddingCacheStats:
    """Contadores L1(Redis)/L2(Postgres)/API por chamada de batch — p/ telemetria do funil."""

    def __init__(self) -> None:
        self.l1 = 0
        self.l2 = 0
        self.api = 0

    def as_dict(self) -> dict[str, int]:
        return {"n_emb_cache_l1": self.l1, "n_emb_cache_l2": self.l2, "n_emb_api": self.api}


BatchProgressCallback = Callable[[int, int, int, int], Awaitable[None]]
"""callback(batch_atual, total_batches, n_processados_acumulado, total_textos)"""


def _embed_cache_key(texto: str) -> str:
    provider = (settings.llm_provider or "default").lower()
    model = (
        "text-embedding-3-small"
        if provider == "openai"
        else (settings.embedding_model or "embedding-3")
    )
    digest = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    return f"emb:{provider}:{model}:{settings.embedding_dimensions}:{digest}"


# ──────────────────────────────────────────────────────────────────────────────
# Camada L2 em Postgres (SPEC_Inlinks_Cache_Duravel_Embeddings)
# O Redis (L1) é efêmero em produção (Render KV free = 25MB, evicção contínua).
# Esta camada persiste o embedding na tabela embeddings_cache (chave = PK igual
# à do Redis) e re-hidrata o Redis a cada hit. Tudo fail-soft: qualquer erro
# degrada silenciosamente para a API — cache nunca derruba uma execução.
# ──────────────────────────────────────────────────────────────────────────────


async def _l2_get(chaves: list[str]) -> dict[str, list[float]]:
    """Lê chaves da L2 em lote (1 SELECT). Retorna {chave: embedding}. Fail-soft → {}."""
    if not chaves:
        return {}
    try:
        from sqlalchemy import text

        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    text("SELECT chave, embedding FROM embeddings_cache WHERE chave = ANY(:chaves)"),
                    {"chaves": chaves},
                )
            ).all()
        out: dict[str, list[float]] = {}
        for chave, emb in rows:
            # Em query text() crua o asyncpg devolve VECTOR como string
            # "[0.1,0.2,...]" (codec pgvector só existe no caminho ORM);
            # ndarray/list cobrem outros drivers.
            if emb is None:
                continue
            if isinstance(emb, str):
                emb = json.loads(emb)
            elif hasattr(emb, "tolist"):
                emb = emb.tolist()
            elif not isinstance(emb, list):
                emb = list(emb)
            if not emb:
                continue
            out[str(chave)] = [float(x) for x in emb]
        return out
    except Exception as e:
        logger.warning("L2 embeddings_cache leitura falhou (%d chaves): %s", len(chaves), e)
        return {}


async def _l2_marcar_uso_em_lote(chaves: list[str]) -> None:
    """Atualiza usado_em em lote (1 UPDATE) — base da limpeza por uso. Fail-soft."""
    if not chaves:
        return
    try:
        from sqlalchemy import text

        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            await session.execute(
                text(
                    "UPDATE embeddings_cache SET usado_em = NOW() WHERE chave = ANY(:chaves)"
                ),
                {"chaves": chaves},
            )
            await session.commit()
    except Exception as e:
        logger.warning("L2 embeddings_cache usado_em update falhou: %s", e)


# Referências das escritas L2 em background — sem isso o GC pode cancelar a
# task antes de concluir (pitfall conhecido do asyncio.create_task).
_l2_bg_tasks: set[asyncio.Task] = set()


def _l2_put_bg(chave: str, embedding: list[float]) -> None:
    t = asyncio.create_task(_l2_put(chave, embedding))
    _l2_bg_tasks.add(t)
    t.add_done_callback(_l2_bg_tasks.discard)


async def _l2_put(chave: str, embedding: list[float]) -> None:
    """Persiste (upsert) um embedding na L2. Fail-soft."""
    if not embedding:
        return
    try:
        from sqlalchemy import text

        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO embeddings_cache (chave, embedding, criado_em, usado_em)
                    VALUES (:chave, CAST(:emb AS VECTOR(1024)), NOW(), NOW())
                    ON CONFLICT (chave) DO UPDATE SET usado_em = NOW()
                    """
                ),
                {"chave": chave, "emb": str(embedding)},
            )
            await session.commit()
    except Exception as e:
        logger.warning("L2 embeddings_cache escrita falhou key=%s: %s", chave, e)


async def gerar_embeddings_batch(
    textos: list[str],
    usuario_id: str,
    on_progress: BatchProgressCallback | None = None,
) -> list[list[float] | None]:
    if not textos:
        return []

    resultados: list[list[float] | None] = [None] * len(textos)
    keys = [_embed_cache_key(t) for t in textos]
    stats = EmbeddingCacheStats()

    # ── L1: Redis ────────────────────────────────────────────────────────────
    indices_pendentes: list[int] = []
    for i, key in enumerate(keys):
        cached = await cache_get_json(key)
        if isinstance(cached, list) and cached:
            resultados[i] = cached
            stats.l1 += 1
        else:
            indices_pendentes.append(i)

    # ── L2: Postgres (em lote, 1 SELECT para todos os misses da L1) ──────────
    if indices_pendentes:
        chaves_l2 = [keys[i] for i in indices_pendentes]
        try:
            l2_hits = await _l2_get(chaves_l2)
        except Exception as e:
            # Fail-soft: qualquer erro na L2 degrada para a API sem propagar.
            logger.warning("L2 embeddings_cache falhou (degradando para API): %s", e)
            l2_hits = {}
        ainda_pendentes: list[int] = []
        chaves_l2_hit: list[str] = []
        for i in indices_pendentes:
            emb = l2_hits.get(keys[i])
            if emb:
                resultados[i] = emb
                chaves_l2_hit.append(keys[i])
                stats.l2 += 1
                # Re-hidrata L1 (Redis SET barato, aguarda para ser determinístico).
                await cache_set_json(keys[i], emb, _EMBED_CACHE_TTL)
            else:
                ainda_pendentes.append(i)
        indices_pendentes = ainda_pendentes
        if chaves_l2_hit:
            await _l2_marcar_uso_em_lote(chaves_l2_hit)

    if not indices_pendentes:
        logger.info(
            "embeddings cache hit (%d textos): L1=%d L2=%d",
            len(textos), stats.l1, stats.l2,
        )
        if on_progress:
            with contextlib.suppress(Exception):
                await on_progress(1, 1, len(textos), len(textos))
        return resultados

    logger.info(
        "embeddings cache: %d/%d hits (L1=%d L2=%d), %d para gerar via API",
        len(textos) - len(indices_pendentes),
        len(textos),
        stats.l1,
        stats.l2,
        len(indices_pendentes),
    )

    embeddings_model = _get_embeddings_model()
    if not embeddings_model:
        return resultados

    total_batches = (len(indices_pendentes) + _BATCH_SIZE - 1) // _BATCH_SIZE
    n_processados = len(textos) - len(indices_pendentes)

    for batch_idx, offset in enumerate(range(0, len(indices_pendentes), _BATCH_SIZE), start=1):
        chunk_indices = indices_pendentes[offset : offset + _BATCH_SIZE]
        chunk_textos = [textos[i] for i in chunk_indices]
        try:
            batch_results = await embeddings_model.aembed_documents(chunk_textos)
            for j, emb in enumerate(batch_results):
                idx = chunk_indices[j]
                resultados[idx] = emb
                if emb:
                    stats.api += 1
                    await cache_set_json(keys[idx], emb, _EMBED_CACHE_TTL)
                    _l2_put_bg(keys[idx], emb)
        except Exception as e:
            logger.warning("Embeddings batch falhou (offset %d, size %d): %s", offset, len(chunk_textos), e)
            split_results = await _gerar_batch_com_split(chunk_textos, chunk_indices, keys, resultados, depth=0)
            for idx, emb in split_results:
                resultados[idx] = emb
                if emb:
                    stats.api += 1
                    await cache_set_json(keys[idx], emb, _EMBED_CACHE_TTL)
                    _l2_put_bg(keys[idx], emb)

        n_processados += len(chunk_indices)
        if on_progress:
            try:
                await on_progress(batch_idx, total_batches, n_processados, len(textos))
            except Exception as e:
                logger.debug("on_progress callback embeddings falhou: %s", e)

    return resultados


async def _gerar_batch_com_split(
    textos: list[str],
    indices: list[int],
    keys: list[str],
    resultados: list[list[float] | None],
    depth: int = 0,
) -> list[tuple[int, list[float] | None]]:
    if not textos:
        return []

    embeddings_model = _get_embeddings_model()
    if not embeddings_model:
        return [(idx, None) for idx in indices]

    if depth > 5:
        logger.error("Embedding split atingiu profundidade max; %d textos 1-a-1", len(textos))
        results = []
        for i, idx in enumerate(indices):
            try:
                emb = await embeddings_model.aembed_query(textos[i])
                results.append((idx, emb))
            except Exception:
                results.append((idx, None))
        return results

    try:
        batch_results = await embeddings_model.aembed_documents(textos)
        return list(zip(indices, batch_results, strict=False))
    except Exception as e:
        if len(textos) == 1:
            logger.warning("Embedding single falhou: %s", e)
            return [(indices[0], None)]
        meio = len(textos) // 2
        a, b = await asyncio.gather(
            _gerar_batch_com_split(textos[:meio], indices[:meio], keys, resultados, depth + 1),
            _gerar_batch_com_split(textos[meio:], indices[meio:], keys, resultados, depth + 1),
        )
        return a + b


async def gerar_embedding_single(texto: str, usuario_id: str) -> list[float] | None:
    key = _embed_cache_key(texto)
    # L1
    cached = await cache_get_json(key)
    if isinstance(cached, list) and cached:
        return cached

    # L2
    l2_hits = await _l2_get([key])
    emb_l2 = l2_hits.get(key)
    if emb_l2:
        await cache_set_json(key, emb_l2, _EMBED_CACHE_TTL)
        await _l2_marcar_uso_em_lote([key])
        return emb_l2

    # API
    embeddings_model = _get_embeddings_model()
    if not embeddings_model:
        return None
    try:
        emb = await embeddings_model.aembed_query(texto)
        if emb:
            await cache_set_json(key, emb, _EMBED_CACHE_TTL)
            _l2_put_bg(key, emb)
        return emb
    except Exception as e:
        logger.warning("Embedding single falhou: %s", e)
        return None


def media_embeddings(embeddings: list[list[float] | None]) -> list[float] | None:
    validos = [e for e in embeddings if e is not None]
    if not validos:
        return None
    arr = np.array(validos, dtype=float)
    media = arr.mean(axis=0)
    return media.tolist()


def cosine_seguro(a, b) -> float:
    try:
        result = float(np.dot(a, b) / (_np_norm(a) * _np_norm(b) + 1e-8))
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception:
        return 0.0


def _get_embeddings_model():
    try:
        if settings.llm_provider == "openai":
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model="text-embedding-3-small",
                dimensions=settings.embedding_dimensions,
                api_key=settings.openai_api_key,
            )
        else:
            from langchain_community.embeddings import ZhipuAIEmbeddings

            kwargs = {
                "model": settings.embedding_model,
                "api_key": settings.zhipuai_api_key,
            }
            if settings.embedding_dimensions:
                kwargs["dimensions"] = settings.embedding_dimensions
            return ZhipuAIEmbeddings(**kwargs)
    except Exception as e:
        logger.warning("Falha ao criar modelo de embeddings: %s", e)
        return None
