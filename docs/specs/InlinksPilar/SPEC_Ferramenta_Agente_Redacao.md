# SPEC: Ferramenta de Agentes de Redacao SEO

> **Documento para consumo por Agente de IA.** Le esta spec na integra antes de escrever qualquer codigo.
> Cada regra marcada com `PROIBIDO` e inviolavel. Violacoes destas regras sao bugs criticos de seguranca.
> Todas as 25 regras de `SPEC_Login_e_Autenticacao.md` se aplicam integralmente a este documento.

| Campo | Valor |
|---|---|
| **Titulo** | Ferramenta de Agentes de Redacao SEO |
| **Versao** | 2.0 |
| **Data** | 2026-04-22 |
| **Classificacao** | Confidencial |
| **Referencia** | `docs/core/SDD.md`, `fluxo-agentes-redacao.html`, `docs/specs/SPEC_Login_e_Autenticacao.md` |

---

## 1. REGRAS ABSOLUTAS — NUNCA FACA (especificas desta ferramenta)

| # | PROIBIDO | Motivo |
|---|----------|--------|
| 1 | **NUNCA** debite creditos antes da conclusao com sucesso do workflow | Se o workflow falhar midway, o usuario perde creditos injustamente |
| 2 | **NUNCA** exponha prompts de sistema dos agentes ao cliente/frontend | Prompts sao propriedade intelectual e seguranca |
| 3 | **NUNCA** permita que o usuario passe instrucoes que contornem o persona/tom de voz | Toda instrucao do usuario passa pelo filtro de seguranca do agente |
| 4 | **NUNCA** retorne o texto do artigo completo em logs | Logs so contem: user_id, execucao_id, etapa, status, timestamp |
| 5 | **NUNCA** armazene embeddings de conteudo reprovado no banco vetorial | Apenas conteudo aprovado pelo usuario vai para o historico |
| 6 | **NUNCA** use `innerHTML` para renderizar o conteudo gerado pelo agente | XSS via conteudo LLM — use `innerText`, `createTextNode` ou markdown sanitizado |
| 7 | **NUNCA** permita o loop infinito de revisao (redator ↔ revisor) | Maximo 3 tentativas de revisao automatica. Apos isso, envia ao usuario |
| 8 | **NUNCA** permita o loop infinito de feedback humano (usuario ↔ redator) | Maximo 3 rodadas de feedback humano. Apos isso, retorna ultima versao com aviso |
| 9 | **NUNCA** faca chamadas a API de pesquisa (SerpAPI/Google Trends) sem cache | Sempre verifique cache antes de chamar APIs externas pagas |
| 10 | **NUNCA** armazene chaves de API (OpenAI, SerpAPI, Google Trends) no banco de dados | Variaveis de ambiente ou secrets manager apenas |
| 11 | **NUNCA** retorne dados de um cliente para outro usuario | Sempre validar ownership: `cliente.usuario_id == usuario_autenticado.id` |
| 12 | **NUNCA** permita SQL injection nas queries de similaridade vetorial | Usar sempre SQLAlchemy ORM parametrizado |
| 13 | **NUNCA** inclua dados sensiveis do cliente (API keys, credenciais) no `config_json` | `config_json` contem apenas metadados de persona e preferencias |
| 14 | **NUNCA** bloqueie a thread principal esperando resposta do LLM | Toda chamada LLM deve ser async (`await`) |
| 15 | **NUNCA** confie na saida do LLM sem validacao | Sempre valide: tamanho, formato, presenca de campos obrigatorios |
| 16 | **NUNCA** execute o workflow LangGraph na request thread do FastAPI | Workflow deve rodar em background (ARQ worker) — a request apenas enfileira |
| 17 | **NUNCA** exceda o rate limit da OpenAI — use semaphore async por usuario | Sem controle, multiplas geracoes simultaneas estouram RPM/TPM e causam falhas em cascata |
| 18 | **NUNCA** compartilhe cache de pesquisa entre usuarios sem scoping por `usuario_id` | Contexto (persona, cliente) e diferente para cada usuario |
| 19 | **NUNCA** descarte versoes intermediarias do artigo durante revisoes | O usuario pode querer comparar versoes ou voltar a uma anterior |
| 20 | **NUNCA** permita que um workflow fique rodando indefinidamente | Timeout global de 5 minutos. Apos isso, status = `falhou` |

---

## 2. STACK TECNOLOGICA

| Componente | Tecnologia | Versao | Observacao |
|---|---|---|---|
| LLM Principal | OpenAI GPT-4o | latest via LangChain | Configuravel via `config.py` |
| Embeddings | OpenAI `text-embedding-3-small` | 1536 dim | Via LangChain |
| Orquestracao de Agentes | LangGraph | 1.1.x | Grafos com branching condicional |
| Framework LLM | LangChain | 1.2.x | Chamadas LLM, embeddings, cache |
| Banco Vetorial | pgvector | PostgreSQL extension | HNSW index (veja §3.5) |
| Pesquisa Web | SerpAPI | latest | Resultados de busca |
| Tendencias | Google Trends API (pytrends) | latest | Tendencias de busca |
| Geracao de Imagem | DALL-E 3 (OpenAI) | latest | Imagens para blog/post |
| Fila de Tarefas | ARQ | latest | Worker async para workflows (usa Redis) |
| Streaming Progresso | SSE (Server-Sent Events) | FastAPI native | Progresso em tempo real |
| Checkpoint Store | PostgresSaver (LangGraph) | built-in | Persistencia de estado entre interrupts |

---

## 3. MODELO DE DADOS

### 3.1 `clientes`

Referencia: SDD §4.3

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | Identificador |
| `usuario_id` | UUID | FK → `usuarios.id`, NOT NULL | Dono |
| `nome` | VARCHAR(255) | NOT NULL | Nome do cliente |
| `site_url` | VARCHAR(500) | nullable | URL do site |
| `config_json` | JSONB | NOT NULL, default `{}` | Persona + configuracoes |
| `ativo` | BOOLEAN | NOT NULL, default true | Soft delete |
| `criado_em` | TIMESTAMPTZ | NOT NULL, default `now()` | Criacao |
| `atualizado_em` | TIMESTAMPTZ | NOT NULL, default `now()` | Atualizacao |

**Estrutura de `config_json` (expandida para multi-persona):**

```json
{
  "persona_global": {
    "tom_voz": "formal mas acessivel",
    "nivel_tecnico": "intermediario",
    "estilo_escrita": "didatico",
    "instrucoes_gerais": "Use tom profissional",
    "exemplos_textos": ["Exemplo de texto representativo..."]
  },
  "personas": [
    {
      "nome": "Gestor de Clinica",
      "tom_voz": "direto e persuasivo",
      "nivel_tecnico": "basico",
      "estilo_escrita": "direto",
      "objetivo": "converter leads em pacientes",
      "palavras_proibidas": ["impulsionar", "surpreendente", "revolucionario"],
      "palavras_recomendadas": ["resultado", "pratico", "comprovado"]
    }
  ]
}
```

**Indexes:** `idx_clientes_usuario_id` (usuario_id)

### 3.2 `contas_creditos`

Referencia: SDD §4.4

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → `usuarios.id`, UNIQUE | Um registro por usuario |
| `saldo_plano` | INTEGER | NOT NULL, default 0 | Creditos do plano atual |
| `saldo_extras` | INTEGER | NOT NULL, default 0 | Creditos extras (nao expiram) |
| `ciclo_inicio` | DATE | NOT NULL | Inicio do ciclo atual |
| `ciclo_fim` | DATE | NOT NULL | Fim do ciclo atual |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criacao |
| `atualizado_em` | TIMESTAMPTZ | NOT NULL | Atualizacao |

**Propriedade computada:** `saldo_total = saldo_plano + saldo_extras`

### 3.3 `transacoes_creditos`

Referencia: SDD §4.5

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `conta_id` | UUID | FK → `contas_creditos.id`, NOT NULL | Conta |
| `tipo` | VARCHAR(30) | NOT NULL | `renovacao`, `debito`, `credito_extra`, `ajuste` |
| `quantidade` | INTEGER | NOT NULL | Positivo = credito, Negativo = debito |
| `descricao` | VARCHAR(500) | NOT NULL | Descricao legivel |
| `ferramenta` | VARCHAR(50) | nullable | Nome da ferramenta (se debito) |
| `execucao_id` | UUID | FK → `execucoes_ferramentas.id`, nullable | Relacao com execucao |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criacao |

**Indexes:** `idx_transacoes_conta_id` (conta_id, criado_em DESC)

### 3.4 `execucoes_ferramentas`

Referencia: SDD §4.6 (expandido para workflow multi-step com fila)

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → `usuarios.id`, NOT NULL | Usuario |
| `cliente_id` | UUID | FK → `clientes.id`, nullable | Cliente |
| `ferramenta` | VARCHAR(50) | NOT NULL | `gerar_artigo` |
| `creditos_cobrados` | INTEGER | NOT NULL, default 0 | Creditos debitados (0 enquanto nao conclui) |
| `status` | VARCHAR(20) | NOT NULL | Veja transicoes abaixo |
| `etapa_atual` | VARCHAR(50) | nullable | Etapa atual do workflow |
| `entrada_json` | JSONB | NOT NULL | Input do usuario |
| `resultado_json` | JSONB | nullable | Output final |
| `erro_msg` | VARCHAR(1000) | nullable | Mensagem de erro |
| `tentativas_revisao` | INTEGER | NOT NULL, default 0 | Contador de revisoes automaticas |
| `tentativas_feedback` | INTEGER | NOT NULL, default 0 | Contador de feedbacks humanos |
| `thread_id` | VARCHAR(255) | UNIQUE, NOT NULL | ID do checkpoint LangGraph (PostgresSaver) |
| `job_id` | VARCHAR(255) | nullable | ID do job ARQ (para rastreamento) |
| `timeout_em` | TIMESTAMPTZ | NOT NULL | Deadline absoluto (criacao + 5 min) |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criacao |
| `concluida_em` | TIMESTAMPTZ | nullable | Conclusao |

**Status e transicoes validas:**

```
pendente → enfileirado         (ARQ aceitou o job)
enfileirado → executando        (worker comecou)
executando → aguardando_aprovacao  (revisor aprovou, human-in-the-loop)
executando → aguardando_revisao    (revisor reprovou 3x, pede feedback ao usuario)
aguardando_aprovacao → executando  (usuario reprovou, volta ao redator)
aguardando_revisao → executando    (usuario enviou feedback, volta ao redator)
aguardando_aprovacao → concluida   (usuario aprovou → vetorial + imagem)
aguardando_aprovacao → cancelada   (usuario cancelou manualmente)
executando → falhou                (erro no workflow ou timeout)
enfileirado → falhou               (ARQ rejeitou o job)
```

**Indexes:** `idx_execucoes_usuario_id` (usuario_id, criado_em DESC), `idx_execucoes_thread_id` (thread_id)

### 3.5 `conteudos_vetores` (NOVO — banco vetorial)

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → `usuarios.id`, NOT NULL | Dono |
| `cliente_id` | UUID | FK → `clientes.id`, nullable | Cliente associado |
| `execucao_id` | UUID | FK → `execucoes_ferramentas.id`, nullable | Execucao que gerou |
| `titulo` | VARCHAR(500) | NOT NULL | Titulo do conteudo |
| `conteudo` | TEXT | NOT NULL | Texto completo |
| `tipo` | VARCHAR(50) | NOT NULL | `blog`, `produto`, `categoria`, `noticias`, `instagram`, `topico` |
| `intencao` | VARCHAR(50) | NOT NULL | `informacional`, `comercial`, `transacional`, `navegacional` |
| `palavras_chave` | JSONB | NOT NULL, default `[]` | Lista de palavras-chave |
| `atividades` | JSONB | NOT NULL, default `[]` | Lista de atividades/termos relacionados |
| `embedding` | vector(1536) | NOT NULL | Embedding (text-embedding-3-small) |
| `score_base` | FLOAT | NOT NULL, default 0.0 | Score calculado na insercao |
| `ativo` | BOOLEAN | NOT NULL, default true | Soft delete |
| `criado_em` | TIMESTAMPTZ | NOT NULL, default `now()` | Criacao |

**Indexes:**
- `idx_conteudos_vetores_usuario_id` (usuario_id)
- `idx_conteudos_vetores_cliente_id` (cliente_id)
- `idx_conteudos_vetores_embedding` — **HNSW** index (nao IVFFlat):

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE INDEX idx_conteudos_vetores_embedding
ON conteudos_vetores
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);
```

**Por que HNSW e nao IVFFlat:**
- HNSW nao requer treinamento periodico (IVFFlat precisa de `CREATE INDEX` + clusterizar apos inserts significativos)
- HNSW tem recall > 99% em qualquer tamanho de dataset
- IVFFlat so e superior em throughput puro com datasets muito grandes (>10M) — cenario improvavel nesta aplicacao (max ~100K por usuario)
- `m = 16`: balance entre precisao e memoria
- `ef_construction = 200`: qualidade de construcao do indice (mais alto = melhor recall, mais lento para inserir)

**Configuracao de busca:**

```python
# ef_search controla trade-off precisao vs velocidade na query
# Default e 40, mas para qualidade usamos 100
resultado = await session.execute(
    select(ConteudoVetor)
    .filter(ConteudoVetor.usuario_id == usuario_id)
    .order_by(
        ConteudoVetor.embedding.cosine_distance(query_embedding)
    )
    .limit(10)
    .execution_options(
        {"hnsw_ef_search": 100}
    )
)
```

### 3.6 `versoes_artigo` (NOVO — versionamento de conteudo)

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `execucao_id` | UUID | FK → `execucoes_ferramentas.id`, NOT NULL | Execucao |
| `versao` | INTEGER | NOT NULL | Numero da versao (1, 2, 3...) |
| `origem` | VARCHAR(30) | NOT NULL | `redator_inicial`, `revisao_auto`, `feedback_humano` |
| `conteudo_markdown` | TEXT | NOT NULL | Texto da versao |
| `titulo` | VARCHAR(500) | NOT NULL | Titulo da versao |
| `contagem_palavras` | INTEGER | NOT NULL | Palavras na versao |
| `score_revisao` | FLOAT | nullable | Score do revisor (se aplicavel) |
| `feedback_recebido` | TEXT | nullable | Feedback que gerou esta versao |
| `criado_em` | TIMESTAMPTZ | NOT NULL, default `now()` | Criacao |

**Unique:** `(execucao_id, versao)`

**Indexes:** `idx_versoes_execucao_id` (execucao_id, versao DESC)

**Regras:**
- Toda geracao/redacao cria uma nova versao
- O usuario pode comparar versoes na tela de aprovacao
- Versoes sao mantidas por 30 dias apos a conclusao (cleanup job)

### 3.7 `pesquisas_cache` (NOVO — cache de pesquisas web, scoped por usuario)

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → `usuarios.id`, NOT NULL | Dono do cache |
| `query_hash` | VARCHAR(64) | NOT NULL | SHA-256 da query normalizada |
| `query_original` | VARCHAR(1000) | NOT NULL | Query original |
| `resultados_json` | JSONB | NOT NULL | Resultados em cache |
| `fonte` | VARCHAR(30) | NOT NULL | `serpapi`, `google_trends` |
| `expira_em` | TIMESTAMPTZ | NOT NULL | Data de expiracao (7 dias) |
| `criado_em` | TIMESTAMPTZ | NOT NULL, default `now()` | Criacao |

**Unique:** `(usuario_id, query_hash, fonte)` — cache scoped por usuario para respeitar contexto

**Indexes:** `idx_pesquisas_cache_lookup` (usuario_id, query_hash, fonte)

### 3.8 `pacotes_creditos`

Referencia: SDD §4.10

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `nome` | VARCHAR(50) | NOT NULL | `boost_100`, `boost_500`, `boost_1500` |
| `creditos` | INTEGER | NOT NULL | Quantidade de creditos |
| `preco` | DECIMAL(10,2) | NOT NULL | Preco em reais |
| `ativo` | BOOLEAN | NOT NULL, default true | Disponivel |

### 3.9 `compras`

Referencia: SDD §4.11

| Coluna | Tipo | Restricao | Descricao |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → `usuarios.id`, NOT NULL | Usuario |
| `tipo` | VARCHAR(20) | NOT NULL | `assinatura`, `addon` |
| `pacote_id` | UUID | FK → `pacotes_creditos.id`, nullable | Pacote (se addon) |
| `plano_id` | UUID | FK → `planos.id`, nullable | Plano (se assinatura) |
| `valor_pago` | DECIMAL(10,2) | NOT NULL | Valor pago |
| `gateway_id` | VARCHAR(255) | nullable | ID da transacao no gateway |
| `status` | VARCHAR(20) | NOT NULL | `pendente`, `pago`, `cancelado`, `reembolsado` |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criacao |

### 3.10 Diagrama ER (relacoes relevantes a esta ferramenta)

```
usuarios 1──1 contas_creditos
usuarios 1──N clientes
usuarios 1──N conteudos_vetores
usuarios 1──N pesquisas_cache
usuarios 1──N execucoes_ferramentas
usuarios 1──N versoes_artigo (via execucoes)
contas_creditos 1──N transacoes_creditos
clientes 1──N conteudos_vetores
clientes 1──N execucoes_ferramentas
execucoes_ferramentas 1──0..1 transacoes_creditos
execucoes_ferramentas 1──N versoes_artigo
execucoes_ferramentas 1──0..1 conteudos_vetores
```

---

## 4. ARQUITETURA DE EXECUCAO — FILA + SSE

### 4.1 Por que nao rodar o workflow na request thread

O workflow `gerar_artigo` pode demorar **2-5 minutos** (multiplas chamadas LLM + revisoes + imagem).
Rodar na request thread do FastAPI causaria:
- Timeout do reverse proxy (nginx/Caddy default: 60-90s)
- Bloqueio do worker uvicorn (reduz throughput para outros usuarios)
- Nenhum progresso visivel para o usuario ate a conclusao

### 4.2 Arquitetura: ARQ Worker + SSE Streaming

```
┌──────────┐     POST       ┌──────────┐     enqueue      ┌──────────┐
│ Frontend │ ────────────→  │ FastAPI  │ ──────────────→  │   ARQ    │
│  (SSE)   │                │  Router  │                   │  Worker  │
│          │  ←───────────  │          │                   │          │
│          │   SSE stream   │          │                   │  LangGraph│
│          │   (progresso)  │          │                   │  Workflow│
└──────────┘                └──────────┘                   └────┬─────┘
                                  │                             │
                                  ▼                             ▼
                           ┌──────────┐                   ┌──────────┐
                           │ PostgreSQL│                  │  OpenAI  │
                           │ (checkpoints,                 │  API     │
                           │  estado, vetores)             │          │
                           └──────────┘                   └──────────┘
```

**Fluxo:**
1. `POST /api/ferramentas/gerar-artigo` → valida, cria execucao (`pendente`), enfileira no ARQ
2. ARQ worker pega o job, muda status para `executando`, inicia o LangGraph workflow
3. Worker publica progresso via `asyncio.Event` + channel (Redis pub/sub ou PostgreSQL NOTIFY)
4. FastAPI expoe `GET /api/ferramentas/historico/{id}/progresso` como **SSE endpoint**
5. Frontend se conecta ao SSE e recebe updates em tempo real
6. Workflow chega no human-in-the-loop → interrompe (`interrupt`), salva checkpoint no PostgresSaver
7. Usuario aprova/reprova → `POST /api/ferramentas/historico/{id}/aprovacao` → retoma workflow via `thread_id`
8. Workflow conclui → worker debita creditos, salva resultado, muda status para `concluida`

### 4.3 ARQ — Configuracao

**Por que ARQ e nao Celery:**
- ARQ e nativamente async (built for asyncio) — Celery e sync por natureza
- ARQ usa Redis como broker (mesmo Redis que ja sera adicionado para pub/sub)
- ARQ e leve (~500 LOC) — Celery e monolitico
- ARQ suporta job scheduling nativo (para cron de renovacao de creditos)

```python
# backend/app/worker.py
import asyncio
from arq import create_pool
from arq.connections import RedisSettings

async def ctx_startup(ctx):
    ctx["db_session"] = await get_async_session()

async def ctx_shutdown(ctx):
    await ctx["db_session"].close()

async def executar_workflow(ctx, execucao_id: str):
    from app.services.ferramenta_service import FerramentaService
    service = FerramentaService(ctx["db_session"])
    await service.executar_workflow(execucao_id)

class WorkerSettings:
    functions = [executar_workflow]
    on_startup = ctx_startup
    on_shutdown = ctx_shutdown
    redis_settings = RedisSettings(host="redis", port=6379)
    max_jobs = 3  # Max 3 workflows simultaneos por worker
    job_timeout = 300  # 5 minutos max por job
```

**Execucao do worker:**

```bash
arq app.worker.WorkerSettings
```

### 4.4 Redis — Novo servico no Docker Compose

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/var/lib/redis
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  redis_data:
```

### 4.5 PostgresSaver — Checkpoint persistente

LangGraph usa `PostgresSaver` como checkpoint store para persistir o estado entre interrupts:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def get_checkpointer():
    return AsyncPostgresSaver.from_conn_string(
        dsn=settings.database_url.replace("+asyncpg", "postgresql")
    )
```

**Garbage collection de checkpoints:**
- Job cron diario (APScheduler) remove checkpoints de execucoes concluidas/canceladas/falhadas com mais de 7 dias
- Checkpoints em `aguardando_aprovacao` sao mantidos indefinidamente (ate o usuario agir ou cancelar)
- Job cron semanal cancela execucoes em `aguardando_aprovacao` com mais de 30 dias

### 4.6 SSE Endpoint — Streaming de progresso

```
GET /api/ferramentas/historico/{id}/progresso
Accept: text/event-stream
```

**Eventos emitidos:**

```json
{"type": "etapa", "etapa": "pesquisar", "label": "Pesquisando tendências...", "timestamp": "..."}
{"type": "etapa", "etapa": "analisar", "label": "Analisando conteúdos...", "timestamp": "..."}
{"type": "etapa", "etapa": "criar_brief", "label": "Criando brief...", "timestamp": "..."}
{"type": "etapa", "etapa": "redigir", "label": "Redigindo conteúdo...", "timestamp": "..."}
{"type": "etapa", "etapa": "revisar", "label": "Revisando conteúdo...", "timestamp": "..."}
{"type": "revisao_resultado", "score": 82, "aprovado": true, "tentativas": 2}
{"type": "aguardando_aprovacao", "versao": 3, "score": 82}
{"type": "etapa", "etapa": "salvar_vetorial", "label": "Salvando no banco vetorial...", "timestamp": "..."}
{"type": "etapa", "etapa": "gerar_imagem", "label": "Gerando imagem...", "timestamp": "..."}
{"type": "concluida", "execucao_id": "..."}
{"type": "falhou", "erro": "..."}
```

**Implementacao:**

```python
@router.get("/historico/{execucao_id}/progresso")
async def stream_progresso(execucao_id: UUID):
    async def evento_stream():
        while True:
            execucao = await execucao_repo.buscar(execucao_id)
            yield f"data: {json.dumps({'type': 'status', 'status': execucao.status, 'etapa': execucao.etapa_atual})}\n\n"
            if execucao.status in ("concluida", "falhou", "cancelada"):
                yield f"data: {json.dumps({'type': execucao.status})}\n\n"
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        evento_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
```

### 4.7 LLM Rate Limiting — Semaphore async

Para evitar estourar o rate limit da OpenAI com multiplas geracoes simultaneas:

```python
import asyncio

_llm_semaphore = asyncio.Semaphore(3)  # Max 3 chamadas LLM simultaneas (global)
_llm_per_user_semaphores: dict[str, asyncio.Semaphore] = {}

def get_user_semaphore(usuario_id: str) -> asyncio.Semaphore:
    if usuario_id not in _llm_per_user_semaphores:
        _llm_per_user_semaphores[usuario_id] = asyncio.Semaphore(1)  # Max 1 por usuario
    return _llm_per_user_semaphores[usuario_id]

async def chamada_llm_segura(chain, input_data, usuario_id: str):
    async with _llm_semaphore:
        async with get_user_semaphore(usuario_id):
            return await chain.ainvoke(input_data)
```

**Limites configuraveis:**

```env
LLM_GLOBAL_CONCURRENCY=3
LLM_PER_USER_CONCURRENCY=1
```

---

## 5. FLUXO COMPLETO — 10 ETAPAS

### Visao geral do grafo LangGraph

```
USUARIO (input)
    → AGENTE_PESQUISADOR (Step 03)
    → AGENTE_ANALISADOR (Step 04)
    → AGENTE_BRIEF (Step 05)
    → AGENTE_REDATOR (Step 06)
    → AGENTE_REVISOR (Step 07)
        ├── [reprovado → AGENTE_REDATOR] (max 3x)
        └── [aprovado → HUMANO_VALIDA] (Step 08)
            ├── [reprovado → AGENTE_REDATOR] (max 3x)
            └── [aprovado → SALVAR_VETORIAL] (Step 09)
                → AGENTE_IMAGEM (Step 10)
                → ENTREGA_FINAL
```

### Estado compartilhado do workflow

```python
class EstadoWorkflow(TypedDict):
    execucao_id: str
    usuario_id: str
    cliente_id: str
    cliente_config: dict
    persona_selecionada: dict

    topico: str
    palavra_chave_principal: str
    palavras_chave_secundarias: list[str]
    tipo_conteudo: str
    meta_palavras: int
    objetivo: str
    artigo_introdutorio: str
    perguntas_clientes: str
    instrucoes_adicionais: str

    pesquisa_resultados: list[dict]
    conteudos_similares: list[dict]
    brief: dict
    artigo: str
    artigo_titulo: str
    revisao: dict
    feedback_usuario: str

    tentativas_revisao: int
    tentativas_feedback: int
    versao_atual: int
    aprovado_revisor: bool
    aprovado_usuario: bool

    imagem_url: str | None
    imagem_prompt: str | None
    conteudo_final: dict
```

---

## 6. AGENTES — ESPECIFICACAO DETALHADA

### 6.1 Agente 1 — Pesquisador de Tendencias (Step 03)

**Responsabilidade:** Pesquisar o topico na web, Google Trends e SERPs, identificando conteudos relevantes e em alta.

**Input:** `topico`, `palavra_chave_principal`, `palavras_chave_secundarias`

**Output:**
```python
@dataclass
class PesquisaResultado:
    resultados_web: list[dict]
    tendencias: list[dict]
    conteudos_vetoriais: list[dict]
    insights: str
```

**Comportamento:**
1. Normaliza a query (lowercase, remove acentos, trim)
2. Verifica cache em `pesquisas_cache` scoped por `usuario_id` (TTL: 7 dias)
3. Se cache miss: chama SerpAPI + Google Trends (graceful degradation, veja §8)
4. Salva resultados no cache
5. Busca no banco vetorial conteudos similares (cosine similarity, threshold > 0.5)
6. LLM resume os achados em insights acionaveis

**Custo LLM:** 1 chamada (resumo de insights)

---

### 6.2 Agente 2 — Analisador de Conteudos (Step 04)

**Responsabilidade:** Analisar conteudos do banco vetorial e selecionar os 3-5 melhores para base do artigo.

**Input:** `pesquisa_resultados`, `topico`, `palavra_chave_principal`, `intenção`

**Output:**
```python
@dataclass
class AnaliseResultado:
    conteudos_selecionados: list[dict]
    scores: list[dict]
    resumo_analise: str
```

**Formula de pontuacao:**

```
score = (
    Vec{similaridade_coseno} * 0.35 +          # 0..1
    Vec{relevancia_contextual} * 0.30 +         # 0..1
    Vec{atualizacao_por_regiao}{Top 4} * 0.20 + # 0..1
    Vec{penalizacao_por_repeticao}{Top 4} * 0.15 # -0.3..0
)
```

**Pos-processing:** ordenar por score descendente, filtrar threshold > 0.3, selecionar Top 4/5.

**Custo LLM:** 1 chamada (resumo da analise)

---

### 6.3 Agente 3 — Criador de Brief (Step 05)

**Responsabilidade:** Criar um brief completo com outline e estrutura do conteudo.

**Input:** `pesquisa_resultados`, `conteudos_selecionados`, `topico`, `palavra_chave_principal`, `palavras_chave_secundarias`, `tipo_conteudo`, `meta_palavras`, `objetivo`, `artigo_introdutorio`, `perguntas_clientes`, `persona_selecionada`

**Output:**
```python
@dataclass
class BriefResultado:
    titulo_sugerido: str
    meta_description: str
    outline: list[dict]
    palavras_chave_distribuidas: dict
    tom_voz: str
    referencia_conteudos: list[str]
    estimativa_palavras: dict
    total_estimado: int
```

**Custo LLM:** 1 chamada

---

### 6.4 Agente 4 — Redator (Step 06)

**Responsabilidade:** Redigir o conteudo completo respeitando o brief e o tom de voz da persona.

**Input:** `brief`, `conteudos_selecionados`, `persona_selecionada`, `instrucoes_adicionais`, `feedback_usuario` (se revisao)

**Output:**
```python
@dataclass
class ArtigoResultado:
    titulo: str
    conteudo_markdown: str
    meta_description: str
    palavras_chave_usadas: list[str]
    contagem_palavras: int
    secoes_geradas: list[dict]
```

**Regras do Redator:**
1. Seguir o outline do brief rigorosamente
2. Respeitar o tom de voz da persona (tom_voz, nivel_tecnico, estilo_escrita)
3. **NUNCA** usar palavras proibidas da persona
4. Incluir palavras recomendadas da persona quando natural
5. Aplicar SEO on-page (H1 unico, H2/H3 hierarquicos, meta description, paragrafos curtos)
6. Respeitar `meta_palavras` (+/- 10%)
7. Se `feedback_usuario` estiver presente, aplicar as correcoes solicitadas
8. Apos gerar, salvar versao em `versoes_artigo` (veja §3.6)

**Custo LLM:** 1-2 chamadas (dependendo do tamanho do artigo)

---

### 6.5 Agente 5 — Revisor (Step 07)

**Responsabilidade:** Analisar o conteudo gerado e verificar aderencia ao brief, coerencia, SEO e tom de voz.

**Input:** `artigo`, `brief`, `persona_selecionada`

**Output:**
```python
@dataclass
class RevisaoResultado:
    aprovado: bool
    score_qualidade: float
    problemas: list[dict]
    sugestoes: list[str]
    feedback_para_redator: str
    checagens: dict
```

**Checagens:**

| Checagem | Descricao | Peso |
|---|---|---|
| `aderencia_outline` | Todas as secoes do outline foram cobertas? | 20% |
| `tom_voz` | O conteudo segue o tom de voz da persona? | 20% |
| `palavras_chave` | Palavras-chave foram distribuidas corretamente? | 15% |
| `coerencia_textual` | O texto e coerente e fluído? | 15% |
| `seo_on_page` | H1, H2/H3, meta description estao corretos? | 15% |
| `palavras_proibidas` | Nenhuma palavra proibida foi usada? | 10% |
| `contagem_palavras` | Dentro da meta (+/- 10%)? | 5% |

**Threshold de aprovacao:** `score_qualidade >= 70`

**Branching:**
- `aprovado == true` → Step 08 (validacao humana)
- `aprovado == false` AND `tentativas_revisao < 3` → retorna ao Redator
- `aprovado == false` AND `tentativas_revisao >= 3` → Step 08 com aviso

**Custo LLM:** 1 chamada

---

### 6.6 Agente 6 — Gerador de Imagem (Step 10)

**Responsabilidade:** Gerar prompt de imagem e criar imagem via DALL-E 3.

**Input:** `artigo` (conteudo final aprovado), `tipo_conteudo`

**Output:**
```python
@dataclass
class ImagemResultado:
    prompt_usado: str
    url_imagem: str
    alt_text: str
```

**Regras:**
1. Prompt gerado pelo LLM com base no conteudo
2. Estilo visual adequado (blog, profissional)
3. NUNCA incluir texto legivel na imagem
4. Alt text descritivo para acessibilidade
5. Imagem 1792x1024 (landscape) para blog

**Custo:** 1 chamada LLM (gerar prompt) + 1 chamada DALL-E 3

---

## 7. WORKFLOW LANGGRAPH — IMPLEMENTACAO

### 7.1 Definicao do grafo

```python
from langgraph.graph import StateGraph, END

def criar_workflow(checkpointer):
    workflow = StateGraph(EstadoWorkflow)

    workflow.add_node("pesquisar", agente_pesquisador.executar)
    workflow.add_node("analisar", agente_analisador.executar)
    workflow.add_node("criar_brief", agente_brief.executar)
    workflow.add_node("redigir", agente_redator.executar)
    workflow.add_node("revisar", agente_revisor.executar)
    workflow.add_node("aguardar_aprovacao", pausar_para_usuario)
    workflow.add_node("salvar_vetorial", salvar_no_vetorial)
    workflow.add_node("gerar_imagem", agente_imagem.executar)

    workflow.set_entry_point("pesquisar")
    workflow.add_edge("pesquisar", "analisar")
    workflow.add_edge("analisar", "criar_brief")
    workflow.add_edge("criar_brief", "redigir")
    workflow.add_edge("redigir", "revisar")

    workflow.add_conditional_edges(
        "revisar",
        roteamento_revisor,
        {
            "redigir": "redigir",
            "aguardar_aprovacao": "aguardar_aprovacao",
        }
    )

    workflow.add_conditional_edges(
        "aguardar_aprovacao",
        roteamento_usuario,
        {
            "redigir": "redigir",
            "salvar_vetorial": "salvar_vetorial",
        }
    )

    workflow.add_edge("salvar_vetorial", "gerar_imagem")
    workflow.add_edge("gerar_imagem", END)

    return workflow.compile(checkpointer=checkpointer)
```

### 7.2 Funcoes de roteamento

```python
def roteamento_revisor(estado: EstadoWorkflow) -> str:
    if estado["aprovado_revisor"]:
        return "aguardar_aprovacao"
    if estado["tentativas_revisao"] < 3:
        return "redigir"
    return "aguardando_aprovacao"

def roteamento_usuario(estado: EstadoWorkflow) -> str:
    if estado["aprovado_usuario"]:
        return "salvar_vetorial"
    if estado["tentativas_feedback"] < 3:
        return "redigir"
    return "salvar_vetorial"
```

### 7.3 Mecanismo de human-in-the-loop (PostgresSaver + interrupt)

```python
async def pausar_para_usuario(estado: EstadoWorkflow):
    from langgraph.types import interrupt

    interrupt({
        "tipo": "aprovacao_usuario",
        "versao": estado["versao_atual"],
    })

    return estado
```

**Ciclo de vida completo do interrupt:**

```
1. Workflow chega no node "aguardar_aprovacao"
2. interrupt() e chamado → PostgresSaver salva checkpoint com thread_id
3. Worker finaliza — a funcao do ARQ retorna (nao bloqueia o worker)
4. Estado da execucao: status = "aguardando_aprovacao", thread_id salvo
5. Frontend detecta via polling ou SSE que status mudou
6. Usuario acessa pagina de aprovacao, ve o artigo + revisao
7. Usuario aprova/reprova via POST
8. Backend busca o checkpoint via thread_id + PostgresSaver
9. Backend retoma o grafo com Command(resume=value) contendo a decisao
10. Workflow continua de onde parou
```

**Retomada do workflow:**

```python
async def retomar_workflow(execucao_id: UUID, acao: str, feedback: str | None):
    execucao = await execucao_repo.buscar(execucao_id)

    checkpointer = await get_checkpointer()
    workflow = criar_workflow(checkpointer)

    config = {"configurable": {"thread_id": execucao.thread_id}}

    valor_resume = {
        "acao": acao,  # "aprovar" ou "reprovar"
        "feedback": feedback,
    }

    async for evento in workflow.astream(
        Command(resume=valor_resume),
        config=config,
    ):
        await processar_evento_workflow(evento, execucao_id)
```

### 7.4 Timeout global

```python
WORKFLOW_TIMEOUT_SEGUNDOS = 300  # 5 minutos

async def executar_workflow_seguro(execucao_id: str):
    try:
        await asyncio.wait_for(
            executar_workflow(execucao_id),
            timeout=WORKFLOW_TIMEOUT_SEGUNDOS,
        )
    except asyncio.TimeoutError:
        await execucao_repo.atualizar(
            execucao_id,
            status="falhou",
            erro_msg="Workflow excedeu o tempo limite de 5 minutos",
        )
```

### 7.5 Retry com exponential backoff — Erros retryable

```python
import httpx

RETRYABLE_ERRORS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.InternalServerError,
)

MAX_RETRIES = 2
BACKOFF_BASE = 2  # 2s, 4s

async def chamada_llm_com_retry(chain, input_data, usuario_id: str):
    for tentativa in range(MAX_RETRIES + 1):
        try:
            async with _llm_semaphore:
                async with get_user_semaphore(usuario_id):
                    return await chain.ainvoke(input_data)
        except RETRYABLE_ERRORS as e:
            if tentativa == MAX_RETRIES:
                raise WorkflowError(f"LLM falhou apos {MAX_RETRIES + 1} tentativas: {e}")
            await asyncio.sleep(BACKOFF_BASE ** tentativa)
        except Exception:
            raise  # Erros nao-retryable (auth, bad request) propagam imediatamente
```

### 7.6 Graceful degradation — APIs externas

| API | Falha | Comportamento |
|---|---|---|
| SerpAPI | Timeout / erro | Loga warning, continua sem resultados web. Brief usa apenas banco vetorial |
| Google Trends | Timeout / erro | Loga warning, continua sem tendencias. Nao e bloquente |
| OpenAI (LLM) | Erro retryable | Retry 2x com backoff. Se falhar → workflow falha, creditos NAO debitados |
| OpenAI (embeddings) | Erro | Usa busca textual (keyword match) como fallback. Loga warning |
| DALL-E 3 | Erro | Workflow conclui com status `concluida` mas `imagem_url = null`. Loga warning |
| PostgreSQL | Erro | Workflow falha, creditos NAO debitados |

---

## 8. SISTEMA DE CREDITOS — REAJUSTADO

### 8.1 Problema do custo flat

Custo flat de 25 creditos para `gerar_artigo` nao reflete o custo real:
- Minimo: 6 chamadas LLM + 1 DALL-E = ~$0.08
- Maximo (3 revisoes + 3 feedbacks): 16 chamadas LLM + 1 DALL-E = ~$0.25

**Solucao:** Custo base + custo por revisao.

### 8.2 Nova tabela de custos

| Ferramenta / Etapa | Custo (creditos) | Chamadas LLM estimadas |
|---|---|---|
| `gerar_artigo` (base: Steps 03-06) | 15 | 4-5 |
| `gerar_artigo` (revisao automatica) | 3 por revisao | 2 (redator + revisor) |
| `gerar_artigo` (feedback humano) | 3 por rodada | 1-2 (redator) |
| `gerar_artigo` (gerar imagem) | 5 | 1 LLM + 1 DALL-E |
| `gerar_artigo` (salvar vetorial) | 0 | 0 |

**Custo total maximo (pior caso):** 15 + (3 × 3) + (3 × 3) + 5 = 38 creditos
**Custo total tipico:** 15 + (1 × 3) + 5 = 23 creditos
**Custo total minimo (sem revisoes):** 15 + 5 = 20 creditos

**Debito:** Creditos sao debitados ao final do workflow (apos conclusao ou falha).
- Sucesso: debita `custo_base + (custo_revisao × tentativas) + custo_imagem`
- Falha: NAO debita

### 8.3 Display no frontend

Na tela de confirmacao (Step 4 do wizard):

```
Custo estimado: 20-38 creditos
├── Geracao base: 15 creditos (fixo)
├── Revisoes: 3 creditos cada (max 3 automaticas + 3 feedbacks)
├── Imagem: 5 creditos (fixo)
└── Seu saldo atual: 350 creditos
```

### 8.4 Custo das demais ferramentas (inalterado)

| Ferramenta | Custo (creditos) |
|---|---|
| `gerar_outline` | 8 |
| `mapear_interlinks` | 12 |
| `revisar_conteudo` | 10 |
| `gerar_faq` | 5 |
| `analisar_keywords` | 6 |
| `gerar_schema` | 4 |
| `gerar_h1` | 3 |
| `gerar_meta_description` | 3 |
| `gerar_title_tag` | 3 |

### 8.5 Fluxo de debito

```
POST /api/ferramentas/gerar-artigo
    → verificar autenticacao
    → verificar ownership do cliente
    → verificar saldo (saldo_total >= custo_minimo = 20)
    → criar execucao (status=pendente, creditos_cobrados=0)
    → enfileirar no ARQ
    → retornar {id, status: "pendente"}

... workflow executa no worker ...

→ SUCESSO:
    → calcular custo_final = 15 + (3 × revisoes_auto) + (3 × feedbacks) + 5
    → verificar saldo >= custo_final (double-check)
    → debitar custo_final creditos
    → criar transacao_credito com descricao detalhada
    → status = concluida, creditos_cobrados = custo_final

→ FALHA:
    → creditos_cobrados = 0
    → NAO debitar
    → status = falhou
```

---

## 9. API ENDPOINTS

### 9.1 Clientes

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| GET | `/api/clientes` | Listar clientes do usuario | Sim |
| POST | `/api/clientes` | Criar cliente | Sim |
| GET | `/api/clientes/{id}` | Detalhes do cliente | Sim + Dono |
| PUT | `/api/clientes/{id}` | Editar cliente | Sim + Dono |
| DELETE | `/api/clientes/{id}` | Remover cliente (soft) | Sim + Dono |

**POST /api/clientes — Request:**

```json
{
  "nome": "Clinica OdontoVida",
  "site_url": "https://odontovida.com.br/",
  "config_json": {
    "persona_global": {
      "tom_voz": "formal mas acessivel",
      "nivel_tecnico": "intermediario",
      "estilo_escrita": "didatico",
      "instrucoes_gerais": "Foque em resultados praticos",
      "exemplos_textos": []
    },
    "personas": [
      {
        "nome": "Gestor de Clinica",
        "tom_voz": "direto e persuasivo",
        "nivel_tecnico": "basico",
        "estilo_escrita": "direto",
        "objetivo": "converter leads em pacientes",
        "palavras_proibidas": ["impulsionar", "surpreendente"],
        "palavras_recomendadas": ["resultado", "pratico", "comprovado"]
      }
    ]
  }
}
```

**Validacoes server-side:**
- `nome`: obrigatorio, 2-255 caracteres
- `site_url`: opcional, URL valida com prefixo barra final (veja SPEC_Login §23)
- `config_json`: validado contra schema JSON
- `personas[].nome`: obrigatorio, unico dentro do cliente
- `personas[].palavras_proibidas`: max 50 palavras
- `personas[].palavras_recomendadas`: max 50 palavras

### 9.2 Ferramenta: Gerar Artigo

| Metodo | Rota | Descricao |
|---|---|---|
| POST | `/api/ferramentas/gerar-artigo` | Enfileirar geracao de artigo |
| GET | `/api/ferramentas/historico` | Listar execucoes |
| GET | `/api/ferramentas/historico/{id}` | Detalhes da execucao |
| GET | `/api/ferramentas/historico/{id}/progresso` | SSE stream de progresso |
| POST | `/api/ferramentas/historico/{id}/aprovacao` | Aprovar/reprovar conteudo |
| POST | `/api/ferramentas/historico/{id}/cancelar` | Cancelar execucao |
| GET | `/api/ferramentas/historico/{id}/versoes` | Listar versoes do artigo |
| GET | `/api/ferramentas/custos` | Tabela de custos por acao |

**POST /api/ferramentas/gerar-artigo — Request:**

```json
{
  "cliente_id": "uuid",
  "persona_id": "Gestor de Clinica",
  "topico": "Guia completo de SEO local para clinicas odontologicas",
  "palavra_chave_principal": "seo local para clinicas",
  "palavras_chave_secundarias": ["posicionamento google", "clinica perto de mim", "google meu negocio odonto"],
  "tipo_conteudo": "blog",
  "meta_palavras": 2000,
  "objetivo": "Educar gestores de clinicas sobre a importancia de SEO local",
  "artigo_introdutorio": "A maioria dos pacientes pesquisa clinicas no Google antes de marcar consulta...",
  "perguntas_clientes": "Quanto custa SEO? Quanto tempo leva para aparecer no Google?",
  "instrucoes_adicionais": "Inclua dados estatisticos sobre busca local"
}
```

**POST /api/ferramentas/gerar-artigo — Response (202 Accepted):**

```json
{
  "id": "uuid-da-execucao",
  "ferramenta": "gerar_artigo",
  "status": "pendente",
  "etapa_atual": null,
  "creditos_cobrados": 0,
  "criado_em": "2026-04-22T10:00:00Z"
}
```

**Nota:** Retorna `202 Accepted` (nao `200 OK`) pois o processamento e assincrono.

**GET /api/ferramentas/historico/{id}/versoes — Response:**

```json
{
  "execucao_id": "uuid",
  "versoes": [
    {
      "versao": 1,
      "origem": "redator_inicial",
      "titulo": "Guia de SEO Local",
      "contagem_palavras": 1850,
      "score_revisao": 58,
      "criado_em": "2026-04-22T10:01:00Z"
    },
    {
      "versao": 2,
      "origem": "revisao_auto",
      "titulo": "Guia Completo de SEO Local para Clinicas",
      "contagem_palavras": 1987,
      "score_revisao": 75,
      "feedback_recebido": null,
      "criado_em": "2026-04-22T10:02:30Z"
    },
    {
      "versao": 3,
      "origem": "feedback_humano",
      "titulo": "Guia Completo de SEO Local para Clinicas Odontologicas",
      "contagem_palavras": 2010,
      "score_revisao": 82,
      "feedback_recebido": "Simplifique o vocabulario...",
      "criado_em": "2026-04-22T10:05:00Z"
    }
  ]
}
```

**POST /api/ferramentas/historico/{id}/cancelar — Response:**

```json
{
  "id": "uuid-da-execucao",
  "status": "cancelada",
  "creditos_cobrados": 0,
  "mensagem": "Execucao cancelada. Nenhum credito foi debitado."
}
```

### 9.3 Creditos

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| GET | `/api/creditos/saldo` | Saldo detalhado | Sim |
| GET | `/api/creditos/transacoes` | Historico de transacoes | Sim |

### 9.4 Billing

| Metodo | Rota | Descricao | Auth |
|---|---|---|---|
| GET | `/api/billing/plano` | Plano atual do usuario | Sim |
| GET | `/api/billing/pacotes` | Pacotes de creditos extras | Sim |
| POST | `/api/billing/comprar-pacote` | Comprar pacote | Sim |
| GET | `/api/billing/historico` | Historico de compras | Sim |

---

## 10. PAGINAS FRONTEND

### 10.1 Rotas

| Rota | Tipo | Descricao |
|---|---|---|
| `/clientes` | Protegida | Lista de clientes com busca e filtros |
| `/clientes/novo` | Protegida | Formulario de criacao de cliente |
| `/clientes/[id]` | Protegida | Detalhe/editar cliente + gerenciar personas |
| `/ferramentas` | Protegida | Catalogo de ferramentas com custo em creditos |
| `/ferramentas/gerar-artigo` | Protegida | Formulario de geracao de artigo (multi-step wizard) |
| `/ferramentas/historico` | Protegida | Historico de todas as execucoes |
| `/ferramentas/historico/[id]` | Protegida | Detalhe + aprovacao + comparar versoes |
| `/creditos` | Protegida | Saldo, transacoes, pacotes disponiveis |

### 10.2 Formulario de Geracao de Artigo — Steps (Wizard)

**Step 1: Selecionar Cliente + Persona**
- Dropdown de clientes cadastrados
- Dropdown de personas do cliente selecionado
- Botao "Cadastrar novo cliente" (abre modal)

**Step 2: Configurar Conteudo**
- Campo: Topico (obrigatorio)
- Campo: Palavra-chave principal (obrigatorio)
- Campo: Palavras-chave secundarias (tags/chips)
- Campo: Tipo de conteudo (select: blog, artigo, etc.)
- Campo: Meta de palavras (number input)
- Campo: Objetivo (textarea)

**Step 3: Contexto Adicional**
- Campo: Artigo introdutorio (textarea, opcional)
- Campo: Perguntas de clientes (textarea, opcional)
- Campo: Instrucoes adicionais para IA (textarea, opcional)

**Step 4: Confirmacao**
- Resumo de todas as opcoes
- Custo detalhado:
  ```
  Custo estimado: 20-38 creditos
  ├── Geracao base: 15 creditos
  ├── Revisoes: 3 creditos cada (0-6 possiveis)
  └── Imagem: 5 creditos
  Seu saldo atual: 350 creditos
  ```
- Botao: "Gerar Artigo" → `POST` → redirect para `/ferramentas/historico/[id]`

### 10.3 Pagina de Detalhe da Execucao (`/ferramentas/historico/[id]`)

**Enquanto executando (`status == "executando"`) — SSE progresso:**
- Barra de progresso animada com etapa atual
- Labels: "Pesquisando tendencias...", "Analisando conteudos...", "Redigindo...", "Revisando..."
- Status de cada etapa (pendente, em andamento, concluida)
- Tempo decorrido

**Aguardando aprovacao (`status == "aguardando_aprovacao"`):**
- Preview do artigo em markdown (sanitizado, nunca innerHTML)
- Score de revisao visual (badge colorido)
- Lista de problemas/sugestoes da revisao
- Contador: "Revisao 2 de 3" ou "Feedback 1 de 3"
- **Comparador de versoes** (se houver multiplas versoes):
  - Side-by-side diff das versoes
  - Score de cada versao
  - Feedback que gerou cada versao
- Botoes:
  - "Aprovar e Continuar" (verde)
  - "Solicitar Alteracoes" (amarelo) → abre textarea para feedback
  - "Cancelar Execucao" (vermelho) → confirma e cancela, NAO debita creditos

**Concluida (`status == "concluida"`):**
- Artigo final em markdown
- Imagem gerada (se disponivel)
- Botao "Copiar Markdown"
- Botao "Baixar Imagem"
- Custo total debitado
- Link "Gerar novo artigo"

**Falhou (`status == "falhou"`):**
- Mensagem de erro generica
- Botao "Tentar Novamente" (recria execucao, nao debita)
- Custo debitado: 0

### 10.4 Componentes

| Componente | Arquivo | Descricao |
|---|---|---|
| `formulario-cliente.tsx` | `components/clientes/` | Criar/editar cliente com config_json |
| `formulario-persona.tsx` | `components/clientes/` | Criar/editar persona dentro do cliente |
| `card-cliente.tsx` | `components/clientes/` | Card de cliente na listagem |
| `formulario-gerar-artigo.tsx` | `components/ferramentas/` | Wizard multi-step para geracao |
| `painel-aprovacao.tsx` | `components/ferramentas/` | Tela de aprovacao/rejeicao |
| `preview-artigo.tsx` | `components/ferramentas/` | Preview markdown sanitizado |
| `comparador-versoes.tsx` | `components/ferramentas/` | Side-by-side diff de versoes |
| `barra-progresso-workflow.tsx` | `components/ferramentas/` | Progresso SSE em tempo real |
| `tabela-execucoes.tsx` | `components/ferramentas/` | Tabela de historico de execucoes |
| `saldo-creditos.tsx` | `components/layout/` | Badge de saldo no header |
| `modal-creditos-insuficientes.tsx` | `components/layout/` | Modal quando saldo esgotado |

### 10.5 Hooks

| Hook | Descricao |
|---|---|
| `use-creditos.ts` | Saldo, transacoes, polling para atualizacao |
| `use-clientes.ts` | CRUD de clientes |
| `use-execucao.ts` | SSE connection para progresso, polling de status |
| `use-versoes.ts` | Buscar versoes de uma execucao |

---

## 11. CONFIGURACAO

### 11.1 Novas variaveis de ambiente

```env
# Redis (ARQ broker + pub/sub)
REDIS_URL=redis://redis:6379/0

# LLM
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096
OPENAI_API_KEY=sk-...

# LLM Concurrency
LLM_GLOBAL_CONCURRENCY=3
LLM_PER_USER_CONCURRENCY=1

# Embeddings
EMBEDDING_MODEL=text-embedding-3-small

# Pesquisa Web
SERPAPI_KEY=...
GOOGLE_TRENDS_ENABLED=false

# Imagem
DALL_E_MODEL=dall-e-3

# Cache
PESQUISA_CACHE_TTL_DAYS=7

# Workflow
WORKFLOW_TIMEOUT_SEGUNDOS=300
WORKFLOW_MAX_REVISAOES=3
WORKFLOW_MAX_FEEDBACK=3

# ARQ Worker
ARQ_MAX_JOBS=3
ARQ_JOB_TIMEOUT=300
```

### 11.2 Novas dependencias (pyproject.toml)

```toml
[project]
dependencies = [
    "langchain>=1.2.0",
    "langchain-openai>=0.3.0",
    "langchain-community>=0.3.0",
    "langgraph>=0.4.0",
    "pgvector>=0.3.0",
    "google-search-results>=2.4.0",
    "pytrends>=4.9.0",
    "arq>=0.26.0",
    "redis>=5.0.0",
]
```

---

## 12. REGRAS DE SEGURANCA ESPECIFICAS

### 12.1 Validacao de input

- `topico`: max 500 caracteres, strip HTML
- `palavra_chave_principal`: max 200 caracteres, strip HTML
- `palavras_chave_secundarias`: max 20 items, cada max 100 caracteres
- `instrucoes_adicionais`: max 2000 caracteres
- `feedback_usuario`: max 2000 caracteres

### 12.2 Seguranca do banco vetorial

- Queries de similaridade usam sempre SQLAlchemy ORM parametrizado
- Acesso ao banco vetorial sempre filtrado por `usuario_id`
- Nenhum conteudo de um usuario e visivel para outro

### 12.3 Rate limiting

| Rota | Limite |
|---|---|
| `POST /api/ferramentas/gerar-artigo` | 3 req/min por usuario |
| `GET /api/ferramentas/historico/{id}/progresso` | 30 req/min por usuario |
| `POST /api/ferramentas/historico/*/aprovacao` | 10 req/min por usuario |

### 12.4 Logging

**Logs PODEM conter:** `user_id`, `execucao_id`, `etapa_atual`, `status`, `timestamp`, `request_url`, `versao`, `job_id`

**Logs NUNCA podem conter:** conteudo gerado pelo LLM, prompts de sistema, tokens, chaves de API, dados pessoais, feedback textual do usuario

---

## 13. JOBS CRON (APScheduler)

| Job | Schedule | Descricao |
|---|---|---|
| `renovar_ciclos_vencidos` | Diario, 00:00 | Renova creditos do plano para contas com ciclo vencido |
| `limpar_checkpoints_antigos` | Diario, 03:00 | Remove checkpoints LangGraph de execucoes concluidas/falhadas/canceladas com +7 dias |
| `cancelar_execucoes_abandonadas` | Semanal, 02:00 | Cancela execucoes em `aguardando_aprovacao` com +30 dias |
| `limpar_versoes_antigas` | Diario, 04:00 | Remove versoes de artigos com +30 dias de execucoes concluidas |
| `limpar_cache_expirado` | Diario, 05:00 | Remove registros de `pesquisas_cache` com `expira_em < now()` |

---

## 14. DADOS INICIAIS

### 14.1 Planos

| nome | creditos_por_mes | preco_mensal | cliente_limite | permite_extras |
|---|---|---|---|---|
| free | 50 | 0.00 | 3 | false |
| pro | 500 | 97.00 | 15 | true |
| business | 2000 | 247.00 | -1 | true |

### 14.2 Pacotes de Creditos

| nome | creditos | preco |
|---|---|---|
| boost_100 | 100 | 29.00 |
| boost_500 | 500 | 97.00 |
| boost_1500 | 1500 | 197.00 |

---

## 15. ESTRUTURA DE DIRETORIOS (novos arquivos)

```
backend/
  app/
    models/
      cliente.py              # NOVO
      conta_credito.py        # NOVO
      transacao_credito.py    # NOVO
      execucao_ferramenta.py  # NOVO
      conteudo_vetor.py       # NOVO
      versao_artigo.py        # NOVO (versionamento)
      pesquisa_cache.py       # NOVO (scoped por usuario)
      pacote_credito.py       # NOVO
      compra.py               # NOVO
    schemas/
      cliente.py              # NOVO
      credito.py              # NOVO
      ferramenta.py           # NOVO
      billing.py              # NOVO
    routers/
      clientes.py             # NOVO
      ferramentas.py          # NOVO
      creditos.py             # NOVO
      billing.py              # NOVO
    services/
      cliente_service.py      # NOVO
      credito_service.py      # NOVO
      ferramenta_service.py   # NOVO
      billing_service.py      # NOVO
    agents/
      base.py                 # NOVO (base + LLM semaphore + retry)
      pesquisador.py          # NOVO
      analisador.py           # NOVO
      criador_brief.py        # NOVO
      redator.py              # NOVO
      revisor.py              # NOVO
      gerador_imagem.py       # NOVO
      workflow.py             # NOVO (grafo LangGraph + PostgresSaver)
    core/
      llm_guard.py            # NOVO (semaphore + retry logic)
      graceful_degradation.py # NOVO (fallbacks para APIs externas)
    worker.py                 # NOVO (ARQ WorkerSettings)
    scheduler.py              # NOVO (APScheduler cron jobs)

frontend/
  src/
    app/(app)/
      clientes/
        page.tsx              # NOVO
        novo/page.tsx         # NOVO
        [id]/page.tsx         # NOVO
      ferramentas/
        page.tsx              # NOVO
        gerar-artigo/page.tsx # NOVO
        historico/
          page.tsx            # NOVO
          [id]/page.tsx       # NOVO
      creditos/
        page.tsx              # NOVO
    components/
      clientes/
        formulario-cliente.tsx     # NOVO
        formulario-persona.tsx     # NOVO
        card-cliente.tsx           # NOVO
      ferramentas/
        formulario-gerar-artigo.tsx # NOVO
        painel-aprovacao.tsx       # NOVO
        preview-artigo.tsx         # NOVO
        comparador-versoes.tsx     # NOVO (side-by-side diff)
        barra-progresso-workflow.tsx # NOVO (SSE progress)
        tabela-execucoes.tsx       # NOVO
      layout/
        saldo-creditos.tsx         # NOVO
        modal-creditos-insuficientes.tsx # NOVO
    hooks/
      use-creditos.ts         # NOVO
      use-clientes.ts         # NOVO
      use-execucao.ts         # NOVO (SSE + polling)
      use-versoes.ts          # NOVO
    lib/
      sse-client.ts           # NOVO (SSE helper)
```
