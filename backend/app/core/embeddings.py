import asyncio
import contextlib
import hashlib
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


async def gerar_embeddings_batch(
    textos: list[str],
    usuario_id: str,
    on_progress: BatchProgressCallback | None = None,
) -> list[list[float] | None]:
    if not textos:
        return []

    resultados: list[list[float] | None] = [None] * len(textos)
    keys = [_embed_cache_key(t) for t in textos]

    indices_pendentes: list[int] = []
    for i, key in enumerate(keys):
        cached = await cache_get_json(key)
        if isinstance(cached, list) and cached:
            resultados[i] = cached
        else:
            indices_pendentes.append(i)

    if not indices_pendentes:
        logger.info("embeddings 100%% cache hit (%d textos)", len(textos))
        if on_progress:
            with contextlib.suppress(Exception):
                await on_progress(1, 1, len(textos), len(textos))
        return resultados

    logger.info(
        "embeddings cache: %d/%d hits, %d para gerar",
        len(textos) - len(indices_pendentes),
        len(textos),
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
                    await cache_set_json(keys[idx], emb, _EMBED_CACHE_TTL)
        except Exception as e:
            logger.warning("Embeddings batch falhou (offset %d, size %d): %s", offset, len(chunk_textos), e)
            split_results = await _gerar_batch_com_split(chunk_textos, chunk_indices, keys, resultados, depth=0)
            for idx, emb in split_results:
                resultados[idx] = emb
                if emb:
                    await cache_set_json(keys[idx], emb, _EMBED_CACHE_TTL)

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
    cached = await cache_get_json(key)
    if isinstance(cached, list) and cached:
        return cached

    embeddings_model = _get_embeddings_model()
    if not embeddings_model:
        return None
    try:
        emb = await embeddings_model.aembed_query(texto)
        if emb:
            await cache_set_json(key, emb, _EMBED_CACHE_TTL)
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
