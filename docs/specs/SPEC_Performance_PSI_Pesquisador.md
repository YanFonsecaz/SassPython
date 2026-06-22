# SPEC — Performance e robustez (pesquisador paralelo + cliente PSI)

**Status:** pendente
**Escopo:** backend (`agents/cwv/workflow.py` + `services/cwv_psi_client.py`)
**Crédito:** não muda
**Esforço:** ~4h
**Depende de:** nada (pode ir em paralelo)

## 1. Resumo

Dois pontos de latência/robustez:
1. **`node_pesquisar_outros`** roda em **série** (LLM + web research por problema, agente novo por URL) — é o maior custo de tempo quando há muitos problemas residuais.
2. **Cliente PSI** cria um `httpx.AsyncClient` por request (sem keep-alive) e só faz retry/fallback de key em **429/403** — um 5xx/erro de rede transitório derruba a URL (que some da análise).

## 2. Estado atual e problemas

| # | Local | Problema |
|---|---|---|
| 1 | `workflow.py:199-231` | loop por URL e por problema, `await pesquisador.documentar(...)` em série; `CWVPesquisadorAgent` novo por URL |
| 2 | `cwv_psi_client.py:29` | `async with httpx.AsyncClient(...)` por request (sem pool); worker tem `ctx["http"]` não usado |
| 3 | `cwv_psi_client.py:45-59` | retry só em 429/403 (fallback de key); 5xx/rede levanta `PSIError` imediatamente |

## 3. Decisão de arquitetura

- **Paralelizar o pesquisador** com `asyncio.gather` sobre todos os problemas residuais, limitado pelo `SEMAFORO_LLM` (já existe) para não estourar rate-limit. Reaproveitar um agente por (plataforma) em vez de por URL.
- **Cliente PSI**: usar um `httpx.AsyncClient` compartilhado (módulo, com `limits`) e adicionar **retry com backoff** em 5xx/`RequestError` (além do fallback de key em 429/403), reaproveitando a mesma estratégia do `llm_guard` (tentativas + backoff exponencial curto).

## 4. Mudanças

### 4.1 `workflow.py` — `node_pesquisar_outros` em paralelo

Coletar as tarefas e despachar com `gather` + semáforo:

```python
async def node_pesquisar_outros(estado):
    ...
    # 1) montar lista (chave, problema, plataforma) dos residuais (kb_codigo is None), limitada por chave
    tarefas = []
    agentes: dict[str, CWVPesquisadorAgent] = {}
    for chave, problemas in estado["problemas_por_url"].items():
        sem_kb = [p for p in problemas if p.get("kb_codigo") is None][:settings.cwv_pesquisador_max_por_analise]
        plataforma = estado["plataformas"].get(chave, "outros")
        if sem_kb and plataforma not in agentes:
            agentes[plataforma] = CWVPesquisadorAgent(usuario_id=usuario_id, plataforma=plataforma)
        for p in sem_kb:
            tarefas.append((chave, p, plataforma))

    async def _pesquisar_um(chave, p, plataforma):
        async with SEMAFORO_LLM:
            ctx = p.get("contexto_especifico", {})
            audit_dict = {... }   # igual ao atual
            try:
                nova_doc = await agentes[plataforma].documentar(audit=audit_dict, plataforma=plataforma)
                if nova_doc:
                    p["documentacao_md"] = nova_doc
                    p["pesquisado"] = True
                    return 1
            except Exception as e:
                logger.warning("Pesquisador falhou para audit %s: %s", ctx.get("audit_id"), e)
            return 0

    resultados = await asyncio.gather(*[_pesquisar_um(c, p, pl) for c, p, pl in tarefas])
    total_pesquisas = sum(resultados)
    # problemas_por_url ja foi mutado in-place (p["documentacao_md"]); retornar o mesmo dict
    return {"problemas_por_url": estado["problemas_por_url"]}
```

> Os `p` são mutados in-place (dicts do estado) — manter o retorno do dict para o reducer. Métrica `cwv_pesquisador_invocacoes.inc(len(tarefas))` uma vez. Cuidado: `SEMAFORO_LLM` é global do módulo (compartilhado com `analisar_seo`, que já terminou nesta etapa — sem conflito).

### 4.2 `cwv_psi_client.py` — cliente compartilhado + retry

```python
import asyncio
_PSI_CLIENT: httpx.AsyncClient | None = None

def _get_client() -> httpx.AsyncClient:
    global _PSI_CLIENT
    if _PSI_CLIENT is None or _PSI_CLIENT.is_closed:
        _PSI_CLIENT = httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _PSI_CLIENT

async def _fetch_psi_once(url, estrategia, api_key):
    params = {...}
    resp = await _get_client().get(PSI_ENDPOINT, params=params)
    resp.raise_for_status()
    return resp.json()
```

Retry em 5xx/rede dentro de `fetch_psi` (por key), antes de desistir:

```python
_PSI_MAX_RETRY = 2
async def _fetch_com_retry(url, estrategia, key):
    for tentativa in range(_PSI_MAX_RETRY + 1):
        try:
            return await _fetch_psi_once(url, estrategia, key)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and tentativa < _PSI_MAX_RETRY:
                await asyncio.sleep(2 ** tentativa)
                continue
            raise
        except httpx.RequestError:
            if tentativa < _PSI_MAX_RETRY:
                await asyncio.sleep(2 ** tentativa)
                continue
            raise
```

E `fetch_psi` chama `_fetch_com_retry` no lugar de `_fetch_psi_once` (mantendo o fallback de key em 429/403). Fechar o cliente no shutdown do worker (`ctx_shutdown`) — opcional; httpx fecha no GC.

> Alternativa: usar `ctx["http"]` (já criado no worker). Como o módulo PSI não recebe `ctx`, um cliente de módulo é mais simples; manter `limits` para não exceder o `SEMAFORO_PSI(5)`.

## 5. Verificação

### 5.1 Pesquisador paralelo

- Unit com stub de `documentar` que dorme 0.2s: N problemas residuais → tempo total ≈ `ceil(N/limite_semaforo)*0.2`, não `N*0.2`. Resultado (docs preenchidas) idêntico ao sequencial.
- Garantir que `p["documentacao_md"]`/`pesquisado` são setados nos mesmos problemas.

### 5.2 PSI retry/pool

- Mock 5xx duas vezes depois 200 → `fetch_psi` retorna ok após retries.
- Mock 5xx sempre → `PSIError` após `_PSI_MAX_RETRY`.
- 429 na key1 → fallback para key2 (comportamento atual preservado).
- Cliente reutilizado entre chamadas (mesmo objeto).

### 5.3 Regressão

Workflow CWV e2e (PSI mockado) inalterado em comportamento; só mais rápido/robusto.

## 6. Riscos

- **Paralelização e rate-limit do PSI/LLM**: já há `SEMAFORO_PSI(5)`/`SEMAFORO_LLM(3)` globais; manter. Monitorar 429.
- **Cliente PSI global em testes**: expor um `reset`/usar `is_closed` para evitar reutilizar cliente de loop fechado entre testes.
- **Retry aumenta latência no pior caso**: limitado a 2 tentativas com backoff curto; aceitável.

## 7. Fora de escopo

- Cache de resultados PSI entre execuções.
- Mover platform-detection para dentro do `coletar_psi`.

## 8. Arquivos alterados

- `backend/app/agents/cwv/workflow.py` — `node_pesquisar_outros` paralelo.
- `backend/app/services/cwv_psi_client.py` — cliente compartilhado + retry 5xx/rede.
- `backend/app/worker.py` (opcional) — fechar cliente PSI no shutdown.
- `backend/tests/unit/` — pesquisador paralelo + retry PSI.
