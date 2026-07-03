# SPEC 06 — LangGraph: padrões de produção e modernização LangChain

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** `agents/workflow*.py`, `agents/base.py`, `agents/inlinks/*` · **Severidade:** Média
**Cobre issues:** #14 (checkpointer sem pool), #39 (mesmo), #40 (astream events não consumidos), #41 (interrupt declarativo), #42 (structured outputs), #43 (sem token-bucket no langchain), #45 (sem LCEL), #46 (boilerplate nó), #47 (BaseAgent ignora structured returns)

**Depende de:** SPEC_05 §5.4 (warmup do checkpointer pool no worker).

Baseado em melhores práticas extraídas via Context7 (`/websites/langchain_oss_python_langgraph`).

---

## 6.1 — `AsyncConnectionPool` para checkpointer

### Problema
3 workflows (`workflow.py`, `workflow_inlinks.py`, `workflow_inlinks_reversos.py`) duplicam:
```python
async with AsyncPostgresSaver.from_conn_string(URL) as cp:
    if not _setup_done:
        await cp.setup()
        _setup_done = True
    yield cp
```

Cada `from_conn_string` abre **uma conexão nova** para psycopg. 100 workflows = 100 ciclos open/close. Em prod isso é overhead real.

### Fix
Pool compartilhado, criado uma vez no startup do worker (SPEC 05 §5.4):

```python
# agents/checkpointer.py (novo)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from app.config import settings

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_setup_done = False
_lock = asyncio.Lock()

async def get_checkpointer() -> AsyncPostgresSaver:
    """Retorna checkpointer compartilhado. Singleton."""
    global _pool, _checkpointer, _setup_done
    if _checkpointer is not None:
        return _checkpointer
    async with _lock:
        if _checkpointer is None:
            db_url = settings.database_url.replace("+asyncpg", "")
            _pool = AsyncConnectionPool(conninfo=db_url, max_size=10, open=False)
            await _pool.open()
            _checkpointer = AsyncPostgresSaver(_pool)
            if not _setup_done:
                await _checkpointer.setup()
                _setup_done = True
    return _checkpointer

async def close_checkpointer():
    global _pool, _checkpointer
    if _pool:
        await _pool.close()
    _pool = None
    _checkpointer = None
```

Remover `_get_checkpointer()` dos 3 workflow files. Substituir por:
```python
from app.agents.checkpointer import get_checkpointer

# em executar_workflow_completo:
checkpointer = await get_checkpointer()
workflow = criar_workflow(checkpointer=checkpointer)
```

Worker `on_startup` chama `await get_checkpointer()` para inicializar. `on_shutdown` chama `await close_checkpointer()`.

---

## 6.2 — Consumir eventos do `astream` (eliminar `publish_event` espalhados)

### Problema
Cada nó faz manualmente:
```python
await publish_event(eid, "node_start", "pesquisar", "Pesquisando...")
# ... lógica ...
await publish_event(eid, "node_complete", "pesquisar", f"{n} encontrados")
```

15 linhas de boilerplate por nó × ~25 nós = ~375 linhas redundantes. Plus, se um nó crashar antes do `node_complete`, fica inconsistente.

### Fix
LangGraph emite eventos automaticamente via `astream`. Consumir e publicar no Redis:

```python
# agents/workflow_runner.py (novo, compartilhado entre os 3 workflows)
async def run_workflow_with_progress(
    workflow,
    estado_inicial: dict,
    config: dict,
    execucao_id: str,
    descricao_node: dict[str, str] | None = None,  # mapa node_id → texto amigável
) -> dict | None:
    """Roda workflow consumindo eventos e publicando progresso."""
    from app.core.workflow_events import publish_event

    descricao_node = descricao_node or {}

    async for event in workflow.astream_events(estado_inicial, config=config, version="v2"):
        kind = event.get("event")
        name = event.get("name", "")

        if kind == "on_chain_start" and name in descricao_node:
            await publish_event(
                execucao_id, "node_start", name,
                descricao_node[name],
            )
        elif kind == "on_chain_end" and name in descricao_node:
            output = event.get("data", {}).get("output", {})
            await publish_event(
                execucao_id, "node_complete", name,
                _resumir_output(name, output),
            )
        elif kind == "on_chain_error":
            await publish_event(
                execucao_id, "node_error", name,
                str(event.get("data", {}).get("error", "")),
            )

    snapshot = await workflow.aget_state(config)
    return snapshot.values if snapshot else None
```

Nós ficam puros (só lógica de negócio):
```python
async def node_pesquisar(estado: EstadoWorkflow) -> dict:
    async with async_session_factory() as session:
        agente = PesquisadorAgent(estado["usuario_id"])
        resultado = await agente.executar(estado, session)
        await session.commit()
    return resultado  # publish_event removido
```

Map de descrições:
```python
WORKFLOW_DESCRICOES = {
    "pesquisar": "Pesquisando tendencias e conteudos...",
    "analisar": "Analisando conteudos selecionados...",
    "criar_brief": "Criando brief de redacao...",
    "redigir": "Redigindo artigo...",
    "revisar": "Revisando qualidade...",
    "aguardar_aprovacao": "Aguardando sua revisao...",
    "salvar_vetorial": "Indexando conteudo...",
    "gerar_imagem": "Gerando imagem com IA...",
}
```

Reduz ~300 linhas, garante consistência start/complete.

---

## 6.3 — `interrupt_before` declarativo

### Problema (#41)
`workflow.py:node_aguardar_aprovacao` usa `interrupt({...})` programático. Funciona, mas o ponto de pausa fica escondido dentro do nó.

### Fix
Usar declarativo no compile:
```python
workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["aguardar_aprovacao"],  # pausa AUTOMATICAMENTE antes
)
```

Mantém o nó simples (apenas update de DB). Retomada via `workflow.astream(Command(resume={...}))` como já é.

---

## 6.4 — Structured outputs (Pydantic) nos agents

### Problema (#42)
Vários agents fazem parse manual:
```python
resposta = await llm.invoke(prompt)
try:
    parsed = json.loads(resposta.content.strip())
except json.JSONDecodeError:
    # fallback frágil
```

Frágil e suscetível a alucinação de JSON malformado.

### Fix
LangChain 0.3+ tem `.with_structured_output(Schema)`:

```python
# agents/inlinks/revisor.py
from pydantic import BaseModel, Field

class RevisaoSchema(BaseModel):
    aprovado: bool = Field(description="True se o inlink deve ser aplicado")
    motivo_rejeicao: str | None = Field(None, description="Por que rejeitar (se aprovado=False)")
    score_qualidade: float = Field(ge=0, le=1, description="Score 0-1")

class _RevisorAgent(BaseAgent):
    async def revisar(self, contexto: dict) -> RevisaoSchema:
        chain = self.llm.with_structured_output(RevisaoSchema)
        return await chain.ainvoke({"role": "user", "content": ...})
```

Aplicar a:
- `revisor.py` (RevisorAgent — revisão de inlinks)
- `reranker.py` (RerankerAgent — score por candidata)
- `inseridor.py` (InseridorAgent — posicionamento)
- `revisor.py` global (RevisorAgent de artigo)
- `enriquecedor_metadados.py`

Reduz código, elimina try/except de parsing, ganha validação Pydantic.

---

## 6.5 — Refatorar `BaseAgent` para retornar dados estruturados

### Problema (#47)
`agents/base.py:31-33`:
```python
if isinstance(resultado, dict):
    return resultado
return {"output": resultado.content}
```

Achata BaseMessage para `{"output": str}` perdendo metadata, tool_calls etc.

### Fix
```python
# agents/base.py
from langchain_core.messages import AIMessage
from typing import Generic, TypeVar
T = TypeVar("T")

class BaseAgent(Generic[T]):
    output_schema: type[T] | None = None  # opcional

    def __init__(self, usuario_id: str):
        self.usuario_id = usuario_id
        self.llm = self._criar_llm()

    def _criar_llm(self):
        if settings.llm_provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=settings.llm_model, ...)
        else:
            from langchain_community.chat_models import ChatZhipuAI
            return ChatZhipuAI(...)

    async def invoke_structured(self, prompt, schema: type[T]) -> T:
        chain = self.llm.with_structured_output(schema)
        return await chamada_llm_mensagem_com_retry(chain, prompt, self.usuario_id)

    async def invoke_raw(self, prompt) -> AIMessage:
        return await chamada_llm_mensagem_com_retry(self.llm, prompt, self.usuario_id)
```

Agents herdam e usam `invoke_structured(prompt, MeuSchema)`.

---

## 6.6 — LCEL para chains compostas

### Problema (#45)
Vários agents fazem `await llm.invoke(prompt1); await llm.invoke(prompt2)` manualmente.

### Fix (onde aplicável)
```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_messages([
    ("system", "..."),
    ("user", "{input}"),
])
chain = prompt | self.llm | StrOutputParser()
return await chain.ainvoke({"input": texto})
```

Benefícios: streaming nativo, parallelism gratuito (`RunnableParallel`), composability.

Aplicar progressivamente; não é refactor obrigatório.

---

## 6.7 — Decorator `@workflow_node` para reduzir boilerplate (#46)

```python
# agents/workflow_helpers.py
from functools import wraps

def workflow_node(node_name: str, descricao: str):
    """Decorator que adiciona: publish_event, atualizar_etapa, session lifecycle."""
    def decorator(func):
        @wraps(func)
        async def wrapper(estado: dict) -> dict:
            from app.core.workflow_events import publish_event
            from app.services import ferramenta_service

            eid = estado["execucao_id"]
            await publish_event(eid, "node_start", node_name, descricao)

            async with async_session_factory() as session:
                await ferramenta_service.atualizar_etapa(session, eid, node_name)
                resultado = await func(estado, session)
                await session.commit()

            await publish_event(eid, "node_complete", node_name, _resumir(node_name, resultado))
            return resultado
        return wrapper
    return decorator
```

Uso:
```python
@workflow_node("pesquisar", "Pesquisando tendencias...")
async def node_pesquisar(estado, session):
    agente = PesquisadorAgent(estado["usuario_id"])
    return await agente.executar(estado, session)
```

3 linhas em vez de 15. (Alternativa ao §6.2; pode coexistir — usar §6.2 para granularidade e este para conveniência local.)

---

## 6.8 — LangSmith / Langfuse tracing

```python
# main.py / worker.py - lifespan/startup
import os

if settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project or "seo-saas"
```

```python
# config.py
langsmith_api_key: str = ""
langsmith_project: str = "seo-saas"
```

Detalhado em SPEC 07 (Observability).

---

## Critério de pronto

- [ ] `app/agents/checkpointer.py` com pool singleton
- [ ] Worker `on_startup` inicializa pool; `on_shutdown` fecha
- [ ] 3 workflows usam `get_checkpointer()`; `_get_checkpointer` antigo removido
- [ ] `astream_events` substitui `publish_event` manuais em pelo menos `workflow.py`
- [ ] `interrupt_before=[...]` declarativo em `workflow.py`
- [ ] Pelo menos `revisor.py` e `reranker.py` usam `with_structured_output`
- [ ] `BaseAgent.invoke_structured` disponível
- [ ] Documentação `docs/architecture/agents.md` com padrões

## Riscos
- `with_structured_output` requer modelo compatível (gpt-4.1 ok; zhipuai precisa verificar). Manter parse manual como fallback.
- LCEL refactor é viral — fazer aos poucos, não bundling com outras mudanças.
- `interrupt_before` mantém checkpoint mesmo se interrupted; documentar como retomar.
- Pool size 10 em multi-worker → 10 × N workers conexões. Verificar limite Postgres.
