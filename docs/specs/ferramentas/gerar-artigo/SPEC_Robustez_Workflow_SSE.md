# SPEC — Robustez do workflow + SSE de progresso

**Status:** ✅ aplicado (commit ddbeb88)
**Escopo:** backend (`workflow.py` + `routers/ferramentas.py`)
**Crédito:** não muda
**Esforço:** ~3h
**Depende de:** nada (pode ir em paralelo; se feita junto com a SPEC de Billing, coordenar edições no `workflow.py`)

## 1. Resumo

Conjunto de correções de robustez/escala no fluxo de aprovação humana e no streaming de progresso:

1. **Efeitos colaterais antes do `interrupt()`** em `node_aguardar_aprovacao` re-executam no resume (comportamento documentado do LangGraph) → eventos SSE duplicados e flip de status desnecessário.
2. **`pubsub = redis.pubsub()` duplicado** no endpoint de progresso (cria e descarta um pubsub).
3. **`aget_state` duplicado em branch morto** no `_run_workflow`.
4. **Mensagem de timeout fala "5 minutos"** mas o timeout real é 600s/10min.
5. **SSE faz polling do banco a cada 1s por cliente** — além do pub/sub. Não escala com muitos streams simultâneos.

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | Eventos duplicados / status pisca no resume | `workflow.py:138-166` (writes + `publish_event` antes do `interrupt` na linha 162) | LangGraph re-roda o nó do início no resume; doc: *"side effects before the pause run again"* |
| 2 | pubsub criado 2× | `routers/ferramentas.py:149-150` | Linha duplicada |
| 3 | Chamada redundante | `workflow.py:354-357` (`aget_state` de novo num `if` que nunca é verdadeiro: `aprovado_usuario` inicia `False`, nunca `None`) | Código morto |
| 4 | Mensagem enganosa | `workflow.py:338` (`"...tempo limite de 5 minutos"`) vs. `workflow_timeout_segundos=600` (`config.py:115`) | String hard-coded |
| 5 | 1 query/s por cliente conectado | `routers/ferramentas.py:174-221` (loop com `buscar_execucao` a cada iteração + `sleep(1)`) | Polling redundante ao pub/sub |

## 3. Decisão de arquitetura

- **#1 (idempotência):** separar os efeitos colaterais "vou aguardar" para um **nó próprio antes** do `interrupt`, seguindo a recomendação oficial (*"Separate side effects into separate nodes"* / *"Place side effects after interrupt calls"*). O nó novo é checkpointed e **não re-roda** no resume; o nó com `interrupt` fica só com a pausa + o pós-processamento.
- **#2, #3, #4:** correções pontuais.
- **#5:** manter o pub/sub como canal primário de progresso e **reduzir a frequência do poll de banco** (que só serve para detectar estado terminal), com um teto de duração do stream. Não dá pra remover o poll porque o estado terminal (`concluida/falhou/cancelada`) é setado pelo serviço e **não** é publicado no canal de eventos.

## 4. Mudanças

### 4.1 `workflow.py` — separar side effects do `interrupt`

Criar um nó que marca "aguardando" (roda uma vez, é checkpointed):

```python
@workflow_node("marcar_aguardando", "Aguardando revisao do usuario...")
async def node_marcar_aguardando(estado: EstadoWorkflow, session) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    from app.services import ferramenta_service

    eid = estado["execucao_id"]
    versao_atual = estado.get("versao_atual", 1)
    aprovado = estado.get("aprovado_revisor", False)
    score = estado.get("revisao", {}).get("score_qualidade", 0)

    status = "aguardando_aprovacao" if aprovado else "aguardando_revisao"
    if aprovado:
        msg = f"Artigo versao {versao_atual} aprovado pela IA (score {score}/100). Aguardando sua revisao..."
    else:
        msg = f"Artigo versao {versao_atual} precisa de ajustes (score {score}/100). Aguardando seu feedback..."
    await ferramenta_service.atualizar_execucao(session, eid, status=status)
    await publish_event(eid, "aguardando", "aguardar_aprovacao", msg)
    return {}
```

Reduzir `node_aguardar_aprovacao` ao essencial (só interrupt + pós-processamento):

```python
async def node_aguardar_aprovacao(estado: EstadoWorkflow) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    from app.services import ferramenta_service

    eid = estado["execucao_id"]
    resume_value = interrupt({
        "tipo": "aprovacao_usuario",
        "versao": estado.get("versao_atual", 1),
        "score": estado.get("revisao", {}).get("score_qualidade", 0),
    })

    aprovado_usuario = False
    feedback_usuario = ""
    if isinstance(resume_value, dict):
        aprovado_usuario = resume_value.get("aprovado_usuario", False)
        feedback_usuario = resume_value.get("feedback_usuario", "")

    async with async_session_factory() as session:
        await ferramenta_service.atualizar_execucao(session, eid, status="executando")
        await session.commit()

    await publish_event(
        eid, "node_complete", "aguardar_aprovacao",
        "Aprovado" if aprovado_usuario else "Feedback recebido, reiniciando revisao",
    )
    return {
        "aprovado_usuario": aprovado_usuario,
        "feedback_usuario": feedback_usuario,
        "tentativas_feedback": estado.get("tentativas_feedback", 0) + (0 if aprovado_usuario else 1),
    }
```

Ligar o novo nó no grafo (`criar_workflow`, `:203-236`):

```python
workflow.add_node("marcar_aguardando", node_marcar_aguardando)
workflow.add_node("aguardar_aprovacao", node_aguardar_aprovacao)
# revisar -> marcar_aguardando (no lugar de -> aguardar_aprovacao)
workflow.add_conditional_edges(
    "revisar", roteamento_revisor,
    {"redigir": "redigir", "aguardar_aprovacao": "marcar_aguardando"},
)
workflow.add_edge("marcar_aguardando", "aguardar_aprovacao")
```

> O `roteamento_usuario` (saída de `aguardar_aprovacao`) continua igual. No resume, só `aguardar_aprovacao` re-roda; `marcar_aguardando` já está checkpointed → sem evento/flip duplicado.
> O SSE quebra em `node_complete aguardar_aprovacao` (`routers/ferramentas.py:210`) — preservado. O evento `"aguardando"` do novo nó é informativo; o front pode tratá-lo como "node_progress" (já cai no `else` que ignora tipos desconhecidos — confirmar no handler do SSE em §4.5).

### 4.2 `workflow.py` — remover `aget_state` morto

Em `_run_workflow` (`:351-357`), apagar o bloco:

```python
# REMOVER — aprovado_usuario inicia False, nunca é None; re-fetch idêntico
if estado_final and estado_final.get("aprovado_usuario") is None and estado_final.get("aprovado_revisor") is not False:
    snapshot = await workflow.aget_state(config)
    if snapshot and snapshot.values:
        estado_final = snapshot.values
```

Fica só o `snapshot`/`estado_final` da primeira leitura (`:351-352`).

### 4.3 `workflow.py` — mensagem de timeout dinâmica

`:336-338`:

```python
except TimeoutError:
    minutos = settings.workflow_timeout_segundos // 60
    async with async_session_factory() as session:
        await ferramenta_service.finalizar_falha(
            session, execucao_id, f"Workflow excedeu o tempo limite de {minutos} minutos"
        )
        await session.commit()
```

### 4.4 `routers/ferramentas.py` — pubsub duplicado

`:149-150`: remover a segunda linha `pubsub = redis.pubsub()` (deixar uma só).

### 4.5 `routers/ferramentas.py` — reduzir poll de banco no SSE

Trocar o poll de 1s por um intervalo de reconciliação maior, mantendo o pub/sub como canal primário. Esboço do loop (`evento_stream`, `:174-221`):

```python
RECONCILE_S = 5          # consulta o banco a cada 5s (só p/ estado terminal)
MAX_STREAM_S = 1800      # teto de vida do stream (30 min)
inicio = time.monotonic()
ultimo_reconcile = 0.0

async def evento_stream():
    try:
        while True:
            if time.monotonic() - inicio > MAX_STREAM_S:
                break
            agora = time.monotonic()
            if agora - ultimo_reconcile >= RECONCILE_S:
                ultimo_reconcile = agora
                async with async_session_factory() as session:
                    execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
                    if not execucao:
                        yield f"data: {json.dumps({'type': 'falhou', 'erro': 'Execucao nao encontrada'})}\n\n"
                        break
                    yield f"data: {json.dumps({'type':'status','status':execucao.status,'etapa':execucao.etapa_atual,'timestamp':datetime.now(UTC).isoformat()})}\n\n"
                    if execucao.status in ("concluida", "falhou", "cancelada"):
                        final = {"type": execucao.status}
                        if execucao.status == "falhou":
                            final["erro"] = execucao.erro_msg
                        elif execucao.status == "concluida":
                            final["creditos_cobrados"] = execucao.creditos_cobrados
                        yield f"data: {json.dumps(final)}\n\n"
                        break
            # drenar eventos de progresso do pub/sub (curto timeout)
            try:
                msg = await asyncio.wait_for(redis_queue.get(), timeout=1.0)
                parsed = json.loads(msg) if isinstance(msg, str) else msg
                if parsed.get("type") in ("node_start", "node_complete"):
                    yield f"data: {json.dumps({'type':'node_progress','node':parsed.get('node'),'detail':parsed.get('detail'),'timestamp':parsed.get('timestamp')})}\n\n"
                    if parsed.get("type") == "node_complete" and parsed.get("node") == "aguardar_aprovacao":
                        break
            except TimeoutError:
                pass
    finally:
        if redis_sub_task:
            redis_sub_task.cancel()
```

> Importar `time`. O comportamento percebido melhora (progresso vem do pub/sub quase em tempo real); a carga no Postgres cai ~5×. O teto `MAX_STREAM_S` evita streams pendurados eternamente.

## 5. Verificação

### 5.1 Idempotência no resume (#1)

E2E (`backend/tests/e2e/test_e2e_workflow.py`): rodar até a pausa, contar eventos publicados no canal `workflow:{eid}`, dar `Command(resume=...)`, e assertar que **não** há um segundo evento `"aguardando"`/`node_start` para `aguardar_aprovacao` (só os pós-resume). Antes da correção, havia duplicata.

### 5.2 Smoke do grafo

`backend/tests/unit/test_workflow_syntaxerror.py` (já existe — valida import/compile): garantir que `criar_workflow()` compila com o novo nó e arestas.

### 5.3 SSE (#5)

- Teste manual: abrir o stream e contar queries ao Postgres num intervalo (log/`pg_stat_statements`) — deve cair para ~1 a cada 5s.
- Garantir que estados terminais ainda fecham o stream em ≤ `RECONCILE_S`.
- Stream que nunca termina fecha em `MAX_STREAM_S`.

### 5.4 Regressões pontuais

- #2: inspecionar que só há um `pubsub` (sem `ResourceWarning` de pubsub não fechado).
- #4: forçar `TimeoutError` (mockar `asyncio.wait_for`) → `erro_msg` diz "10 minutos".

## 6. Riscos

- **Mudança no grafo (#1)**: adicionar nó/arestas exige recompilar; o checkpointer Postgres versiona por `thread_id`, execuções **em andamento** durante o deploy podem divergir do novo grafo. Mitigação: deployar quando não houver execuções pausadas, ou drenar a fila antes. (Mesmo cuidado de qualquer mudança de topologia do LangGraph.)
- **#5 reconcile maior**: estado terminal demora até 5s para refletir no stream — aceitável para UX de geração de artigo (que leva minutos).
- **Coordenação com a SPEC de Billing**: ambas editam `workflow.py`. Fazer rebase/merge com atenção (a de Billing mexe em `_run_workflow`/`_run_resumed_workflow`; esta mexe nos nós e na limpeza do `aget_state`).

## 7. Fora de escopo

- Publicar evento de estado terminal no pub/sub para eliminar 100% o poll (exigiria publicar em `finalizar_sucesso/falha`); avaliável como follow-up.
- WebSocket no lugar de SSE.
- Backpressure/limite global de streams concorrentes.

## 8. Arquivos alterados

- `backend/app/agents/workflow.py` — novo nó `marcar_aguardando`; `node_aguardar_aprovacao` enxuto; remoção do `aget_state` morto; mensagem de timeout dinâmica; arestas atualizadas.
- `backend/app/routers/ferramentas.py` — remover `pubsub` duplicado; loop do SSE com reconcile/teto.
- `backend/tests/e2e/test_e2e_workflow.py` + `backend/tests/unit/test_workflow_syntaxerror.py`.
