"""SPEC_Inlinks_Cache_Duravel_Embeddings — testes da camada L2 (Postgres).

Cobre os 3 contratos da spec:
1. miss no Redis (L1) + hit no Postgres (L2) re-hidrata o Redis e NÃO chama a API;
2. falha do Postgres degrada para a API sem exceção (cache nunca derruba execução);
3. hit na L1 não aciona L2 nem API.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import embeddings as emb


async def _noop(*a, **kw):
    return None


@pytest.mark.asyncio
async def test_miss_l1_hit_l2_rehidrata_e_nao_chama_api(monkeypatch):
    """Miss no Redis + hit no Postgres → API não é chamada, L1 re-hidratada."""
    texto = "exemplo de texto para embedding"
    chave = emb._embed_cache_key(texto)
    vetor = [0.1] * 8

    async def _l1_miss(_k):
        return None
    monkeypatch.setattr(emb, "cache_get_json", _l1_miss)

    set_calls: list[tuple[str, list[float]]] = []

    async def _set_capture(key, value, _ttl):
        set_calls.append((key, value))
    monkeypatch.setattr(emb, "cache_set_json", _set_capture)

    # L2 devolve o vetor.
    async def _l2_hit(chaves):
        assert chaves == [chave]
        return {chave: vetor}
    monkeypatch.setattr(emb, "_l2_get", _l2_hit)

    uso_calls: list[list[str]] = []

    async def _uso(chaves):
        uso_calls.append(chaves)
    monkeypatch.setattr(emb, "_l2_marcar_uso_em_lote", _uso)
    monkeypatch.setattr(emb, "_l2_put", _noop)

    # API NUNCA deve ser chamada.
    modelo = MagicMock()
    modelo.aembed_documents = AsyncMock(side_effect=AssertionError("API chamada indevidamente"))
    monkeypatch.setattr(emb, "_get_embeddings_model", lambda: modelo)

    out = await emb.gerar_embeddings_batch([texto], "user-1")

    assert out == [vetor]
    # Re-hidratou L1 com o vetor vindo da L2.
    assert (chave, vetor) in set_calls
    # Marcou usado_em no L2.
    assert uso_calls == [[chave]]


@pytest.mark.asyncio
async def test_falha_postgres_degrada_para_api(monkeypatch):
    """Se a L2 estoura exceção, o fluxo segue para a API sem propagar erro."""
    texto = "texto que vai à API"
    vetor_api = [0.2] * 8

    async def _l1_miss(_k):
        return None
    monkeypatch.setattr(emb, "cache_get_json", _l1_miss)
    monkeypatch.setattr(emb, "cache_set_json", _noop)

    # L2 estoura.
    async def _l2_boom(_chaves):
        raise RuntimeError("postgres fora do ar")
    monkeypatch.setattr(emb, "_l2_get", _l2_boom)
    monkeypatch.setattr(emb, "_l2_marcar_uso_em_lote", _noop)
    monkeypatch.setattr(emb, "_l2_put", _noop)

    modelo = MagicMock()
    modelo.aembed_documents = AsyncMock(return_value=[vetor_api])
    monkeypatch.setattr(emb, "_get_embeddings_model", lambda: modelo)

    out = await emb.gerar_embeddings_batch([texto], "user-1")

    assert out == [vetor_api]  # API foi chamada como fallback.


@pytest.mark.asyncio
async def test_l1_hit_nao_consulta_l2_nem_api(monkeypatch):
    """Hit na L1 (Redis) não aciona nem L2 nem API."""
    texto = "no cache quente"
    vetor = [0.3] * 8
    chave = emb._embed_cache_key(texto)

    async def _l1_hit(k):
        return vetor if k == chave else None
    monkeypatch.setattr(emb, "cache_get_json", _l1_hit)
    monkeypatch.setattr(emb, "cache_set_json", _noop)

    l2_calls: list = []

    async def _l2_track(chaves):
        l2_calls.append(chaves)
        return {}
    monkeypatch.setattr(emb, "_l2_get", _l2_track)

    modelo = MagicMock()
    modelo.aembed_documents = AsyncMock(side_effect=AssertionError("API chamada com L1 quente"))
    monkeypatch.setattr(emb, "_get_embeddings_model", lambda: modelo)

    out = await emb.gerar_embeddings_batch([texto], "user-1")

    assert out == [vetor]
    assert l2_calls == []  # L2 nem foi consultada.


@pytest.mark.asyncio
async def test_gerar_single_usa_l2_quando_l1_miss(monkeypatch):
    """gerar_embedding_single também consulta L2 e re-hidrata L1."""
    texto = "single hit no postgres"
    vetor = [0.4] * 8
    chave = emb._embed_cache_key(texto)

    async def _l1_miss(_k):
        return None
    monkeypatch.setattr(emb, "cache_get_json", _l1_miss)

    set_calls: list[str] = []

    async def _set_capture(key, _value, _ttl):
        set_calls.append(key)
    monkeypatch.setattr(emb, "cache_set_json", _set_capture)

    async def _l2_hit(chaves):
        return {chave: vetor}
    monkeypatch.setattr(emb, "_l2_get", _l2_hit)
    monkeypatch.setattr(emb, "_l2_marcar_uso_em_lote", _noop)
    monkeypatch.setattr(emb, "_l2_put", _noop)

    modelo = MagicMock()
    modelo.aembed_query = AsyncMock(side_effect=AssertionError("API single chamada indevidamente"))
    monkeypatch.setattr(emb, "_get_embeddings_model", lambda: modelo)

    out = await emb.gerar_embedding_single(texto, "user-1")

    assert out == vetor
    assert chave in set_calls  # re-hidratou L1
