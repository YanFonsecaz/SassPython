# SPEC — Pesquisador não-bloqueante

**Status:** pendente
**Escopo:** backend (`PesquisadorAgent`)
**Crédito:** não muda
**Esforço:** ~2h
**Depende de:** nada (pode ir em paralelo com as demais)

## 1. Resumo

O nó `pesquisar` chama duas bibliotecas **síncronas** (SerpAPI e pytrends) de dentro de funções `async`. Isso **bloqueia a event loop inteira** do worker durante cada chamada de rede. Como o worker ARQ roda com `arq_max_jobs=20` (`config.py:119`) na mesma loop, uma única pesquisa lenta **congela os outros 19 jobs** e todos os streams de progresso SSE. Além disso, o `asyncio.gather` (que aparenta paralelizar pesquisa web + trends + busca vetorial) **não paraleliza de fato**, porque as chamadas síncronas não cedem o controle.

A correção é mover o I/O bloqueante para um thread pool via `asyncio.to_thread`.

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | Event loop trava durante a pesquisa | `pesquisador.py:96-113` (`_buscar_serpapi`: `GoogleSearch(...).get_dict()`) | `serpapi` é síncrono (usa `requests`) |
| 2 | Idem para tendências | `pesquisador.py:115-130` (`_buscar_google_trends`: `TrendReq(...)`, `build_payload`, `interest_over_time`, `related_queries`) | `pytrends` é síncrono |
| 3 | `asyncio.gather` (`:27`) não dá concorrência real | As coroutines bloqueiam antes de qualquer `await` que ceda | Sem `to_thread`/`run_in_executor` (confirmado por grep) |

**Por que importa (multi-tenant):** num SaaS, um usuário lento degradaria a experiência de todos os outros que tiverem jobs no mesmo worker. É um *head-of-line blocking* clássico.

## 3. Decisão de arquitetura

Envolver **todo o corpo bloqueante** de cada busca em `asyncio.to_thread`, mantendo a interface `async` atual (não muda o `gather` nem os callers). `to_thread` despacha a função síncrona para o `ThreadPoolExecutor` default do asyncio, liberando a loop para os outros jobs.

- Envolver a **função inteira** (não só a linha do `.get_dict()`), porque a construção de `TrendReq`/`GoogleSearch` e os acessos a DataFrame do pytrends também fazem rede/CPU.
- Não trocar de biblioteca (fora de escopo). `to_thread` é a correção mínima e segura.
- Atenção ao limite default do executor (nº de threads). Como cada job usa no máx. 2 threads de pesquisa por vez e `max_jobs=20`, o pico é ~40 threads — dentro do default (`min(32, os.cpu_count()+4)` pode ser menor). Ver §6 (risco) — opcionalmente configurar o executor no startup do worker.

## 4. Mudanças

### 4.1 `backend/app/agents/pesquisador.py`

Mover a lógica síncrona para helpers privados e despachar via `to_thread`:

```python
import asyncio
# ...

async def _buscar_serpapi(self, query: str) -> list[dict[str, Any]]:
    if not settings.serpapi_key:
        return []
    return await asyncio.to_thread(self._buscar_serpapi_sync, query)

def _buscar_serpapi_sync(self, query: str) -> list[dict[str, Any]]:
    from serpapi import GoogleSearch
    search = GoogleSearch({
        "q": query, "api_key": settings.serpapi_key,
        "num": 10, "hl": "pt-br", "gl": "br",
    })
    results = search.get_dict()
    organic = results.get("organic_results", [])
    return [
        {"titulo": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in organic
    ]
```

```python
async def _buscar_google_trends(self, query: str) -> list[dict[str, Any]]:
    if not settings.google_trends_enabled:
        return []
    return await asyncio.to_thread(self._buscar_google_trends_sync, query)

def _buscar_google_trends_sync(self, query: str) -> list[dict[str, Any]]:
    from pytrends.request import TrendReq
    pytrends = TrendReq(hl="pt-BR", tz=-3, timeout=(10, 25))
    pytrends.build_payload(kw_list=[query[:50]], timeframe="today 3-m", geo="BR")
    interest = pytrends.interest_over_time()
    if interest.empty:
        return []
    related = pytrends.related_queries()
    related_data = related.get(query[:50], {}).get("rising", [])
    if related_data is None or related_data.empty:
        return []
    return [
        {"termo": row.get("query", ""), "valor": int(row.get("value", 0))}
        for _, row in related_data.head(10).iterrows()
    ]
```

> Nenhuma mudança em `executar`, `_fetch_pesquisa` ou no `asyncio.gather` — eles já são `async` e agora ganham concorrência real.

### 4.2 (Opcional) Executor dedicado no worker

Se o monitoramento mostrar saturação de threads, configurar no `worker.py` (`ctx_startup`):

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
loop = asyncio.get_running_loop()
loop.set_default_executor(ThreadPoolExecutor(max_workers=64, thread_name_prefix="io"))
```

Deixar como follow-up; não bloquear esta SPEC.

## 5. Verificação

### 5.1 Unit — não bloqueia a loop

`backend/tests/unit/test_pesquisador_cache.py` (ou novo):

```python
async def test_serpapi_roda_em_thread(monkeypatch):
    agent = PesquisadorAgent("user-1")
    # função síncrona que dorme; se rodasse na loop, o sleep concorrente abaixo não sobreporia
    def fake_get_dict(self):
        import time; time.sleep(0.3)
        return {"organic_results": [{"title": "t", "link": "u", "snippet": "s"}]}
    monkeypatch.setattr("serpapi.GoogleSearch.get_dict", fake_get_dict)
    monkeypatch.setattr(settings, "serpapi_key", "x")

    t0 = time.monotonic()
    # roda a busca em paralelo com um asyncio.sleep — se não bloquear, o tempo total ~0.3s
    _, ticks = await asyncio.gather(
        agent._buscar_serpapi("q"),
        _contar_ticks(0.3),   # incrementa a cada 0.05s via asyncio.sleep
    )
    assert ticks >= 3   # a loop continuou rodando durante o to_thread
```

(Implementar `_contar_ticks` como helper que faz `await asyncio.sleep(0.05)` em loop por `dur` segundos e conta iterações.)

### 5.2 Manual — concorrência real

Com `serpapi_key` e `google_trends_enabled=True`, logar o tempo de cada busca dentro de `executar` e o tempo total do `gather`. Esperado: `total ≈ max(web, trends, vetorial)`, não a soma.

### 5.3 Regressão

Os testes existentes de `pesquisador` (cache hit/miss em `test_pesquisador_cache.py`) devem continuar passando — a interface pública não mudou.

## 6. Riscos

- **Saturação do thread pool**: pico teórico ~40 threads (20 jobs × 2 buscas). Aceitável; monitorar. Mitigação em §4.2.
- **Thread-safety das libs**: cada chamada cria sua própria instância de `GoogleSearch`/`TrendReq` (sem estado compartilhado) → seguro em threads.
- **pytrends instável (429 do Google)**: já tratado a montante (`web_fallback`/`trends_fallback` e cache). `to_thread` não muda isso.

## 7. Fora de escopo

- Trocar SerpAPI/pytrends por clientes async nativos (`httpx`).
- Retry específico de pytrends.
- Configurar o executor dedicado (vira follow-up se necessário).

## 8. Arquivos alterados

- `backend/app/agents/pesquisador.py` — `_buscar_serpapi`/`_buscar_google_trends` viram wrappers `to_thread` + helpers `_sync`.
- `backend/tests/unit/test_pesquisador_cache.py` (ou novo `test_pesquisador_nao_bloqueia.py`).
- (opcional) `backend/app/worker.py` — executor dedicado.
