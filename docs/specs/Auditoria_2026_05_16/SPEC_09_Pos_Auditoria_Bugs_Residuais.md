# SPEC 09 — Correção dos 17 bugs residuais pós-auditoria

**Status:** a aplicar · **Escopo:** backend (vários arquivos) · **Severidade:** P0 (5) + P1 (6) + P2 (5) + P3 (1)
**Contexto:** Re-auditoria pós aplicação dos SPECs 01-08 identificou 17 issues. Cinco são P0 (críticos) introduzidos pelas próprias implementações dos SPECs. Os demais são concorrência (P1) e LangChain/LangGraph best practices (P2). Esta SPEC aplica todos em ordem de prioridade.

---

## P0 — Bugs críticos novos (aplicar IMEDIATAMENTE, ~30 min)

### 9.1 — `NameError` em `_gerar_batch_com_split` quando depth > 5

**Arquivo:** `backend/app/core/embeddings.py:100-136`
**Problema:** `embeddings_model` é referenciado no branch `if depth > 5` (linha 114) **antes** de ser definido (linha 120). Em recursões profundas (falha total da API embeddings), o código de fallback crasha com `NameError` em vez de degradar graciosamente.

**Fix:**
```python
async def _gerar_batch_com_split(
    textos: list[str],
    indices: list[int],
    keys: list[str],
    resultados: list[list[float] | None],
    depth: int = 0,
) -> list[tuple[int, list[float] | None]]:
    if not textos:
        return []

    embeddings_model = _get_embeddings_model()  # ← MOVER PARA AQUI (antes de depth > 5)
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
        return list(zip(indices, batch_results))
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
```

**Verificação:** mock `_get_embeddings_model` para retornar mock que sempre falha → batch de 64 textos → não pode crashar com NameError; todos devem retornar `(idx, None)`.

---

### 9.2 — Double-pause: `interrupt_before` + `interrupt()` no mesmo nó

**Arquivo:** `backend/app/agents/workflow.py:138-184, 236`
**Problema:** O nó `aguardar_aprovacao` tem **duas pausas**:
1. Compile com `interrupt_before=["aguardar_aprovacao"]` (linha 236)
2. Body do nó chama `interrupt({...})` (linha 162)

Resultado: depois do user aprovar, o body executa, hit `interrupt()` no meio, pausa de novo. Workflow trava porque `aprovar_reprovar` só envia 1 `Command(resume=...)`.

**Fix:** remover `interrupt_before` do compile e manter apenas `interrupt()` no body (padrão recomendado pela docs LangGraph v1):

```python
# workflow.py:236 — antes
return workflow.compile(checkpointer=checkpointer, interrupt_before=["aguardar_aprovacao"])

# depois
return workflow.compile(checkpointer=checkpointer)
```

O `interrupt()` no body já cobre human-in-the-loop. A função `retomar_workflow` em `workflow.py:413+` envia `Command(resume=value)` que é capturado pelo `interrupt()` → tudo funciona com 1 pausa.

**Verificação:** smoke test E2E gerar_artigo: submit → aguarda → aprovar via endpoint → workflow finaliza. Hoje pode ficar travado em segundo interrupt; após fix deve concluir.

---

### 9.3 — `_marcar_falhou` libera reserva da ferramenta errada

**Arquivos:**
- `backend/app/worker.py:78-90` (`_marcar_falhou`)
- `backend/app/services/ferramenta_service.py:246` (`finalizar_falha`)

**Problema:** Worker chama `finalizar_falha(session, execucao_id, msg)` sem `ferramenta`. Default `"gerar_artigo"` é usado mesmo quando execução é `inlinks` ou `distribuir_inlinks`. Reserva da ferramenta errada é liberada (valor incorreto), saldo reservado fica desalinhado.

**Fix:** sempre derivar ferramenta da própria execução no DB.

```python
# services/ferramenta_service.py:246
async def finalizar_falha(
    db, execucao_id: str, erro_msg: str, ferramenta: str | None = None
) -> ExecucaoFerramenta:
    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(f"Execucao {execucao_id} nao encontrada")

    from app.services import credito_service

    # Prefere ferramenta explicita (caller sabe); fallback p/ valor armazenado
    ferramenta_efetiva = ferramenta or execucao.ferramenta or "gerar_artigo"
    reserva = _obter_reserva_estimada(ferramenta_efetiva, execucao)
    if reserva > 0:
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)

    execucao.status = "falhou"
    execucao.erro_msg = erro_msg[:1000]
    execucao.creditos_cobrados = 0
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    logger.info(
        "execucao_falhou",
        extra={
            "event_type": "workflow.failed",
            "execucao_id": execucao_id,
            "ferramenta": ferramenta_efetiva,
            "erro_resumo": erro_msg[:100],
        },
    )
    return execucao
```

**Verificação:** unit test — criar execução `inlinks` com `creditos_reservados=15`, chamar `finalizar_falha` sem param, conferir que `saldo_reservado` desce em 15 (não 20).

---

### 9.4 — `RETRYABLE_ERRORS` ignora exceções OpenAI

**Arquivo:** `backend/app/core/llm_guard.py:13-19`
**Problema:** Rate limit 429 do OpenAI levanta `openai.RateLimitError` (não httpx). Não é retentado → workflow falha imediato em vez de fazer backoff.

**Fix:**
```python
# llm_guard.py — topo
import httpx
import openai

RETRYABLE_ERRORS: tuple = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    openai.RateLimitError,       # 429
    openai.APIConnectionError,   # rede
    openai.APITimeoutError,      # timeout
)


def _e_status_retryable(exc: Exception) -> bool:
    """Erros HTTP 5xx do OpenAI sao retryable; 4xx (exceto 429) nao."""
    if isinstance(exc, openai.APIStatusError):
        return 500 <= exc.status_code < 600
    return False


async def chamada_llm_com_retry(chain, input_data, usuario_id: str):
    for tentativa in range(MAX_RETRIES + 1):
        try:
            return await chamada_llm_segura(chain, input_data, usuario_id)
        except RETRYABLE_ERRORS as e:
            if tentativa == MAX_RETRIES:
                raise WorkflowError(f"LLM falhou apos {MAX_RETRIES + 1} tentativas: {e}") from e
            delay = min(BACKOFF_BASE ** tentativa, 60)
            logger.warning("LLM retry %d/%d em %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
            await asyncio.sleep(delay)
        except openai.APIStatusError as e:
            if _e_status_retryable(e) and tentativa < MAX_RETRIES:
                delay = min(BACKOFF_BASE ** tentativa, 60)
                logger.warning("LLM 5xx retry %d/%d em %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
                await asyncio.sleep(delay)
                continue
            raise WorkflowError(f"LLM erro nao-retryable: {e}") from e
```

Aplicar o mesmo em `chamada_llm_mensagem_com_retry`.

**Verificação:** mock `chain.ainvoke` para levantar `openai.RateLimitError` nas 2 primeiras tentativas e sucesso na terceira → deve retornar resultado em vez de propagar.

---

### 9.5 — `create_pool` ARQ por request (memory/conn leak)

**Arquivos:**
- `backend/app/routers/ferramentas.py:79`
- `backend/app/routers/ferramentas_inlinks.py:53`
- `backend/app/routers/ferramentas_inlinks_reversos.py:54`

**Problema:** Cada request `POST /api/ferramentas/*` chama:
```python
redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
job = await redis.enqueue_job(...)
```

Nunca fecha o pool. Cada conexão fica pendente até GC. Sob 10 req/s × 60s = 600 conexões ativas → exaure Redis `maxclients`.

**Fix:** usar `get_redis_pool()` singleton já existente em `core/redis_pool.py`.

```python
# routers/ferramentas.py — substituir bloco linhas 73-89
try:
    from app.core.redis_pool import get_redis_pool

    redis = await get_redis_pool()
    job = await redis.enqueue_job("executar_workflow", str(execucao.id))
    execucao.job_id = job.job_id
    execucao.status = "enfileirado"
    await db.flush()
except Exception as e:
    logger.error("Falha ao enfileirar workflow: %s", e)
    await credito_service.liberar_reserva(db, str(usuario.id), CUSTO_MINIMO)
    execucao.status = "falhou"
    execucao.erro_msg = "Falha ao enfileirar workflow"
    await db.flush()
```

Aplicar mudança idêntica em:
- `routers/ferramentas_inlinks.py:49-67`
- `routers/ferramentas_inlinks_reversos.py:50-68`

**Verificação:**
```bash
# Antes: cada submit cria nova conn
redis-cli CLIENT LIST | wc -l  # alta
# Depois: reusa pool
redis-cli CLIENT LIST | wc -l  # estavel
```

E2E: 20 submits paralelos não devem aumentar `CLIENT LIST` count significativamente.

---

## P1 — Concorrência e robustez (~1h)

### 9.6 — Token bucket polling 60s causa latência cumulativa

**Arquivo:** `backend/app/core/llm_guard.py:71-78, 97-104`
**Problema:** `for _ in range(60): await asyncio.sleep(1)`. Workflow com 5 LLMs pode esperar 5 × 60s = 5min sem feedback. Capacidade 5 + refill 0.5/s = 30/min — mas semáforo process-local de 3 limita pior.

**Fix:**
1. Subir `llm_global_concurrency` default para 10 (config.py) — semáforo local não é mais a barreira.
2. Reduzir loop para 30s + retornar `RateLimitExcedido` mais cedo.
3. Logar quando esperar > 5s para identificar gargalos.

```python
# llm_guard.py
async def _aguardar_token_llm(usuario_id: str, max_wait_seconds: int = 30) -> None:
    inicio = time.monotonic()
    for tentativa in range(max_wait_seconds):
        if await _adquirir_token_llm(usuario_id):
            duracao = time.monotonic() - inicio
            if duracao > 5:
                logger.info(
                    "llm_bucket_wait",
                    extra={"event_type": "llm.bucket.wait", "usuario_id": usuario_id, "duracao_s": duracao},
                )
            return
        await asyncio.sleep(1)
    from app.core.excecoes import RateLimitExcedido
    raise RateLimitExcedido("LLM bucket vazio apos 30s, tente novamente")


async def chamada_llm_segura(chain, input_data, usuario_id: str):
    await _aguardar_token_llm(usuario_id)
    async with _llm_semaphore:
        return await chain.ainvoke(input_data)
```

Aplicar idêntico em `chamada_llm_mensagem_segura`.

### 9.7 — Token bucket sem segregação por modelo

**Arquivo:** `backend/app/core/llm_guard.py:57`
**Fix:** chave do bucket inclui modelo:

```python
async def _adquirir_token_llm(usuario_id: str, model: str = "default") -> bool:
    ...
    r = await redis.eval(
        LLM_BUCKET_SCRIPT, 1,
        f"llm:bucket:{usuario_id}:{model}",
        time.time(), capacidade, refill,
    )
    ...
```

Caller pode passar `model = chain.model_name` se disponível. Default `"default"` mantém compat.

### 9.8 — `_llm_semaphore` process-local: redimensionar ou remover

**Arquivo:** `backend/app/core/llm_guard.py:11`
**Fix:** ou `llm_global_concurrency=20` (process-local fica relaxado, deixa bucket Redis ser barreira), ou remover semáforo completamente (confiar 100% no bucket distribuído).

Recomendação: **remover** — bucket Redis já coordena cross-process. Semáforo local só ajuda em single-process e atrapalha em multi-worker.

```python
# llm_guard.py — remover linha 11 e blocks "async with _llm_semaphore:"
async def chamada_llm_segura(chain, input_data, usuario_id: str):
    await _aguardar_token_llm(usuario_id)
    return await chain.ainvoke(input_data)
```

### 9.9 — Rate limit fail-open em auth endpoints

**Arquivo:** `backend/app/dependencies.py:96-110`
**Problema:** Se Redis cai, todos endpoints ficam sem rate limit (fail-open). Atacante derruba Redis e tem brute-force livre em `/login`.

**Fix:** suporte a fail-mode por endpoint.

```python
def rate_limit(
    key_prefix: str,
    max_requests: int,
    window_seconds: int,
    fail_mode: str = "open",  # "open" | "closed"
):
    async def _check(request: Request):
        client_ip = get_client_ip(request)
        try:
            from app.core.rate_limit import check_rate_limit_redis
            key = f"rl:{key_prefix}:{client_ip}"
            if not await check_rate_limit_redis(key, max_requests, window_seconds):
                raise RateLimitExcedido()
        except RateLimitExcedido:
            raise
        except Exception:
            if fail_mode == "closed":
                logger.error("rate_limit_redis_indisponivel_fail_closed", extra={"key_prefix": key_prefix})
                raise RateLimitExcedido("Servico de rate limit indisponivel")
            # fail-open: log mas continua
            logger.warning("rate_limit_redis_indisponivel_fail_open", extra={"key_prefix": key_prefix})

    return _check
```

Endpoints sensíveis usam `fail_mode="closed"`:
- `routers/auth.py:/login` → `rate_limit("login", 5, 900, fail_mode="closed")`
- `routers/auth.py:/cadastro` → `fail_mode="closed"`
- `routers/auth.py:/recuperar-senha` → `fail_mode="closed"`
- `routers/auth.py:/resetar-senha` → `fail_mode="closed"`

### 9.10 — Chave de rate limit + LLM bucket usa só IP

**Arquivo:** `backend/app/dependencies.py:102`
**Problema:** `key = f"rl:{key_prefix}:{client_ip}"`. Para endpoints autenticados, melhor segregar por user_id (atrás de CDN/proxy IPs convergem).

**Fix:** dependency separado para rate limit autenticado, que vê o user:

```python
def rate_limit_autenticado(key_prefix: str, max_requests: int, window_seconds: int):
    async def _check(
        request: Request,
        usuario: Usuario = Depends(get_current_user),
    ):
        bucket = str(usuario.id)
        key = f"rl:{key_prefix}:user:{bucket}"
        from app.core.rate_limit import check_rate_limit_redis
        if not await check_rate_limit_redis(key, max_requests, window_seconds):
            raise RateLimitExcedido()
    return _check
```

Aplicar em endpoints autenticados (`gerar-artigo`, `distribuir-inlinks`, etc.).

### 9.11 — `WorkflowError` propaga ao worker como exceção genérica

**Arquivo:** `backend/app/core/llm_guard.py:66, 90`
**Problema:** `WorkflowError` herda de `Exception`, mas worker em `_executar_job` (`worker.py:93`) só trata `ErroTransitorio` e `ErroPermanente`. Cai em `else` → `_marcar_falhou` + `raise` → ARQ retry padrão (3 tentativas).

**Fix:** `WorkflowError` deve ser `ErroPermanente` (esgotou retentativas — não retentar de novo no ARQ):

```python
# llm_guard.py
from app.core.excecoes import ErroPermanente, ErroTransitorio

class WorkflowError(ErroPermanente):
    """Workflow exauriu retries de LLM. Nao retentar."""
    pass
```

---

## P2 — LangChain/LangGraph best practices (~2-3h)

### 9.12 — Migrar parsing manual de JSON para `with_structured_output`

**Arquivos:**
- `backend/app/agents/pesquisador.py`
- `backend/app/agents/analisador.py`
- `backend/app/agents/criador_brief.py`
- `backend/app/agents/revisor.py`
- `backend/app/agents/inlinks/revisor.py`
- `backend/app/agents/inlinks/reranker.py`

**Padrão a aplicar (exemplo revisor):**
```python
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

class RevisaoInlinkItem(BaseModel):
    indice: int = Field(description="Indice do inlink (1-based)")
    status: str = Field(description='"aplicado" ou "rejeitado_revisor"')
    motivo: str = Field(default="", description="Motivo de rejeicao se aplicavel")

class RevisaoInlinks(BaseModel):
    revisao: list[RevisaoInlinkItem]


class _RevisorAgent(BaseAgent):
    async def revisar_estruturado(self, prompt: str) -> RevisaoInlinks:
        chain = self.llm.with_structured_output(RevisaoInlinks)
        return await chamada_llm_mensagem_com_retry(
            chain, [HumanMessage(content=prompt)], self.usuario_id,
        )


# revisar_inlinks usa:
schema = await agente.revisar_estruturado(prompt)
for item in schema.revisao:
    if item.indice in mapa:
        mapa[item.indice]["status"] = item.status
        mapa[item.indice]["motivo_rejeicao"] = item.motivo
```

Elimina `_parse_revisao`, `_parse_rankings`, `json.loads` manual + try/except.

**Verificação:** smoke E2E inlinks; respostas inválidas do LLM agora geram ValidationError do Pydantic em vez de silent fallback.

### 9.13 — `BaseAgent` cria `ChatOpenAI` por instância

**Arquivo:** `backend/app/agents/base.py:13-30`
**Fix:** factory cached via `functools.lru_cache` ou singleton.

```python
# agents/base.py
from functools import lru_cache
from langchain_core.language_models import BaseChatModel


@lru_cache(maxsize=8)
def _get_chat_model(provider: str, model: str, temperature: float, api_key: str) -> BaseChatModel:
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)
    from langchain_community.chat_models import ChatZhipuAI
    return ChatZhipuAI(model=model, temperature=temperature, api_key=api_key)


class BaseAgent:
    def __init__(self, usuario_id: str):
        self.usuario_id = usuario_id
        self.llm = _get_chat_model(
            settings.llm_provider, settings.llm_model,
            settings.llm_temperature,
            settings.openai_api_key if settings.llm_provider == "openai" else settings.zhipuai_api_key,
        )
```

Cache reusa instâncias entre execuções no mesmo processo. Workflow de 8 nós cria 8 agents mas só 1 ChatOpenAI subjacente.

### 9.14 — Código morto: `run_workflow_with_progress` em workflow_helpers.py

**Arquivo:** `backend/app/agents/workflow_helpers.py:73-101`
**Problema:** Função existe mas nenhum workflow chama. `executar_workflow_completo` usa `_run_workflow` próprio.

**Fix:** remover função (ou marcar `@deprecated`). Decoradores `@workflow_node` cobrem o caso de uso.

### 9.15 — `WORKFLOW_DESCRICOES` hardcoded só para gerar_artigo

**Arquivo:** `backend/app/agents/workflow_helpers.py:9-18`
**Fix:** mover descrições para o próprio workflow:

```python
# workflow.py
@workflow_node("pesquisar", "Pesquisando tendencias e conteudos...")
async def node_pesquisar(...): ...
```

(já é o padrão). Então remover `WORKFLOW_DESCRICOES` global.

### 9.16 — `cosine_seguro` importa numpy a cada chamada

**Arquivo:** `backend/app/core/embeddings.py:169-181`
**Fix:**
```python
# topo do arquivo
import math
import numpy as np
from numpy.linalg import norm as _np_norm

def cosine_seguro(a, b) -> float:
    try:
        result = float(np.dot(a, b) / (_np_norm(a) * _np_norm(b) + 1e-8))
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception:
        return 0.0
```

---

## P3 — Pequenos

### 9.17 — Resumo de pesquisa mostra "0 fontes"

**Arquivos:**
- `backend/app/agents/pesquisador.py:48-57` retorna `pesquisa_resultados.resultados_web`
- `backend/app/agents/workflow_helpers.py:49-51` lê `pesquisa_resultados.resultados`

**Fix:** alinhar chaves. Mais natural ajustar o helper:
```python
def _resumir(node_name, resultado, descricao):
    if node_name == "pesquisar":
        pr = resultado.get("pesquisa_resultados", {})
        n_web = len(pr.get("resultados_web", []))
        n_trends = len(pr.get("tendencias", []))
        return f"Pesquisa concluida ({n_web} fontes web, {n_trends} tendencias)"
    ...
```

---

## Ordem de aplicação

| Etapa | SPECs | Tempo | Comentário |
|---|---|---|---|
| 1 | 9.1 (NameError) | 5 min | Trivial, alta criticidade |
| 2 | 9.5 (create_pool leak) | 15 min | 3 arquivos, mesmo padrão |
| 3 | 9.3 (ferramenta no finalizar_falha) | 15 min | Backend + verificar uso |
| 4 | 9.4 (RETRYABLE_ERRORS OpenAI) | 10 min | Acrescentar exceções |
| 5 | 9.2 (interrupt_before) | 5 min + smoke test 10min | Mudança 1-linha + validar fluxo gerar_artigo |
| **Subtotal P0** | | **~1h** | **Aplicar AGORA** |
| 6 | 9.6 + 9.8 (LLM bucket wait + remover semáforo local) | 20 min | |
| 7 | 9.7 (bucket por modelo) | 15 min | |
| 8 | 9.9 (rate limit fail-mode) | 20 min | |
| 9 | 9.10 (rate limit por user) | 30 min | Touch nos endpoints |
| 10 | 9.11 (WorkflowError → ErroPermanente) | 5 min | |
| **Subtotal P1** | | **~1.5h** | **Aplicar antes de 10+ users** |
| 11 | 9.13 (lru_cache chat model) | 15 min | |
| 12 | 9.16 (numpy imports) | 5 min | |
| 13 | 9.14 + 9.15 (limpeza workflow_helpers) | 15 min | |
| 14 | 9.17 (resumo pesquisa) | 5 min | |
| 15 | 9.12 (structured output) | 2-3h | 6 arquivos, mais cuidadoso |
| **Subtotal P2-P3** | | **~3-4h** | **Sustainability** |

**Total:** 5-7h cumulativos.

---

## Verificação final (E2E)

### Teste 1: gerar_artigo com aprovação
1. Submit `POST /api/ferramentas/gerar-artigo`
2. Aguarda `aguardando_aprovacao`
3. Submit `POST /historico/{id}/aprovacao {acao=aprovar}`
4. **Esperado:** workflow finaliza em ~30s. Status `concluida`. Sem double-pause.

### Teste 2: distribuir_inlinks com falha
1. Submit com URL alvo inválida.
2. Workflow falha em `extrair_alvo`.
3. **Esperado:** reserva de 15 créditos liberada (não 20). Conferir via `obter_saldo`.

### Teste 3: LLM rate limit
1. Mock OpenAI para retornar 429 → succeed na terceira tentativa.
2. Workflow continua após 3 retries.
3. **Esperado:** logs mostram `LLM retry`. Sem falha imediata.

### Teste 4: Redis offline (fail-mode)
1. `docker stop redis`.
2. `POST /api/auth/login` → **fail-closed** retorna 429.
3. `GET /api/ferramentas/historico` (não-sensível) → **fail-open** funciona.

### Teste 5: Conn pool stable
1. Loop submit 20 jobs paralelos.
2. `redis-cli INFO clients` → `connected_clients` não cresce significativamente.

---

## Riscos

| Risco | Mitigação |
|---|---|
| Remover `interrupt_before` quebra fluxo de aprovação | E2E gerar_artigo antes/depois; rollback simples. |
| `with_structured_output` falha com modelos não-OpenAI | Manter parse manual como fallback; tag por agent. |
| `lru_cache` no factory mantém instâncias velhas após restart de config | Cache de 8 entradas, refresh on app restart. OK. |
| `fail_mode="closed"` em auth quando Redis fora derruba login | Monitorar Redis; documentar como dependência crítica de auth. |

---

## Critério de pronto

- [ ] 9.1: batch de embeddings com mock-failure não crasha
- [ ] 9.2: gerar_artigo + aprovação E2E conclui sem timeout
- [ ] 9.3: `inlinks` falha libera 15 créditos
- [ ] 9.4: mock 429 retorna sucesso após retries
- [ ] 9.5: 20 submits paralelos não vazam conexões Redis
- [ ] 9.6-9.8: workflow de 5 LLMs em <60s no caminho feliz
- [ ] 9.9: Redis offline + login = 429
- [ ] 9.10: rate limit segregado por user_id em endpoints autenticados
- [ ] 9.11: WorkflowError não causa retry ARQ
- [ ] 9.12: pelo menos revisor + reranker usam Pydantic schema
- [ ] 9.13: factory cached
- [ ] 9.14-9.17: limpeza e ajustes feitos

## Não-objetivos
- Refatorar todos os agents para LCEL (SPEC 06 §6.6 — deixar progressivo)
- LangSmith `@traceable` em todos agents (opcional, valor incremental)
- Migrar embeddings para `init_chat_model`/`init_embeddings` (preferência mantida em LangChain bare)
