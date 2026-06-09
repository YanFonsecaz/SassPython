"""Regressao do cache de pesquisa (uq_pesquisas_cache_lookup).

Antes, quando existia uma entrada EXPIRADA para (usuario_id, query_hash, fonte),
o lookup filtrava por `expira_em > now()`, nao a encontrava, e o agente tentava
INSERIR uma nova linha -> UniqueViolationError -> workflow inteiro falhava.
Agora a entrada expirada e atualizada no lugar.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.agents.pesquisador import PesquisadorAgent
from app.models.pesquisa_cache import PesquisaCache


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeSession:
    """Sessao minima: execute() devolve o objeto pre-configurado."""

    def __init__(self, cache_obj):
        self._cache_obj = cache_obj
        self.added: list = []

    async def execute(self, _stmt):
        return _FakeResult(self._cache_obj)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


def _agent() -> PesquisadorAgent:
    return PesquisadorAgent(usuario_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_cache_expirado_atualiza_no_lugar_sem_inserir():
    usuario_id = str(uuid.uuid4())
    expirada = PesquisaCache(
        usuario_id=usuario_id,
        query_hash="hash",
        query_original="antiga",
        resultados_json={"dados": [{"velho": 1}]},
        fonte="serpapi",
        expira_em=datetime.now(UTC) - timedelta(days=1),  # expirada
    )
    session = _FakeSession(expirada)

    async def buscar_fn(_query):
        return [{"novo": 2}]

    dados, fallback, cache_entry = await _agent()._fetch_pesquisa(
        session, usuario_id, "tema", "serpapi", buscar_fn
    )

    # Reusa a linha existente (atualiza no lugar), nao retorna nova entrada p/ INSERT.
    assert cache_entry is None
    assert dados == [{"novo": 2}]
    assert fallback is False
    assert expirada.resultados_json == {"dados": [{"novo": 2}]}
    assert expirada.expira_em > datetime.now(UTC)


@pytest.mark.asyncio
async def test_cache_miss_retorna_nova_entrada_para_inserir():
    usuario_id = str(uuid.uuid4())
    session = _FakeSession(None)  # nenhuma linha existente

    async def buscar_fn(_query):
        return [{"a": 1}]

    dados, _fallback, cache_entry = await _agent()._fetch_pesquisa(
        session, usuario_id, "tema", "serpapi", buscar_fn
    )

    assert dados == [{"a": 1}]
    assert isinstance(cache_entry, PesquisaCache)
    assert cache_entry.fonte == "serpapi"
    assert cache_entry.resultados_json == {"dados": [{"a": 1}]}
    assert cache_entry.expira_em > datetime.now(UTC)


@pytest.mark.asyncio
async def test_cache_hit_valido_nao_chama_busca():
    usuario_id = str(uuid.uuid4())
    valida = PesquisaCache(
        usuario_id=usuario_id,
        query_hash="hash",
        query_original="tema",
        resultados_json={"dados": [{"cacheado": True}]},
        fonte="serpapi",
        expira_em=datetime.now(UTC) + timedelta(days=1),  # ainda valida
    )
    session = _FakeSession(valida)
    chamou = {"v": False}

    async def buscar_fn(_query):
        chamou["v"] = True
        return [{"naoDeveria": 1}]

    dados, _fallback, cache_entry = await _agent()._fetch_pesquisa(
        session, usuario_id, "tema", "serpapi", buscar_fn
    )

    assert chamou["v"] is False  # cache hit: nao busca de novo
    assert dados == [{"cacheado": True}]
    assert cache_entry is None
