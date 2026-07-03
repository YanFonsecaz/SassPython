# SPEC — Ferramenta "Inlinks Automáticos" (Internal Linking via RAG)

> **Status:** ✅ implementado
> **Versão:** 1.0
> **Ferramenta:** 2ª do SaaS (após "Gerar Artigo SEO")
> **Modo de operação:** Autônomo (sem aprovação humana — "tudo por IA")

---

## 1. Contexto e objetivo

Dada uma arquitetura de fluxo proposta em diagrama (ver `fluxo-inlinks.html`), a ferramenta deve:

1. Receber um **conteúdo pilar** (URL ou texto markdown).
2. Receber uma **lista de URLs candidatas** a virar inlinks.
3. Extrair conteúdo limpo de todas as páginas.
4. Indexar tudo num banco vetorial (pgvector).
5. Fazer re-ranking semântico para escolher quais candidatas viram inlinks no pilar.
6. Gerar âncoras naturais e injetar nos pontos certos do texto.
7. Revisar automaticamente e entregar o resultado final — **sem intervenção do usuário**.

A infraestrutura existente cobre ~70% do que precisamos:

- **LangGraph + AsyncPostgresSaver** para orquestração resiliente — `backend/app/agents/workflow.py`
- **pgvector com `Vector(1024)` + HNSW + cosine ops** — `backend/app/models/conteudo_vetor.py`, migração `0003`
- **Redis pubsub** para SSE de progresso — `backend/app/core/workflow_events.py`
- **ARQ workers** com retry/semáforo/backoff 429 — `backend/app/core/llm_guard.py`, `app/worker.py`
- **Embeddings com fallback** OpenAI/Zhipu — `backend/app/core/graceful_degradation.py`
- **Frontend** com `useExecucao` + `BarraProgressoWorkflow` reusáveis — `frontend/src/hooks/use-execucao.ts`

O resto (scraping, re-ranker, injection de inlinks) é novo.

---

## 2. Análise crítica da arquitetura proposta no diagrama (problemas)

| # | Problema no diagrama | Impacto | Correção |
|---|---|---|---|
| 1 | LLM como "limpador de HTML" (remover footer/menus) | Custa ~1¢/URL × 50 URLs = $0.50 só em limpeza, e LLM não é determinístico | Substituir por **trafilatura + selectolax** (heurística determinística, 100× mais barato) |
| 2 | Dedup só por URL exata via Python | URLs com `?utm_*`, `#`, trailing slash, www vs apex passam como duplicatas | **Normalização de URL canônica** (lowercase host, strip de tracking, resolver redirects) antes da dedup |
| 3 | "Penalização por rejeição" sem origem definida | Fórmula do score depende de dado que não é gerado | Como decisão é "tudo por IA", removo penalização por rejeição na v1; mantém só `similaridade_semantica + relevancia_contextual` |
| 4 | Chunks com embedding sem critério de chunking | Chunking ruim (cortar no meio de frase) destrói embeddings | **Chunking semântico**: split por parágrafo, max 800 tokens, com overlap de 100 tokens |
| 5 | Sem batch de embeddings | N URLs × M chunks = centenas de chamadas individuais. 429 garantido | OpenAI `embeddings.create(input=[...])` aceita até 2048 inputs/call. Reduz N → ceil(N/100) |
| 6 | Sem cache | Re-rodar para mesmas URLs re-processa tudo | Cache por `sha256(html_normalizado)` em Redis (TTL 7 dias) → pula extração+embedding |
| 7 | Sem rate limit por host | 50 URLs do mesmo domínio em paralelo = banimento | Semáforo por host (`max_per_host=2`), respeitar `Retry-After`, `User-Agent` identificável |
| 8 | Risco de SSRF | URL arbitrária do usuário pode apontar para `localhost`, `169.254.169.254` (cloud metadata) | Validar host: rejeitar IPs privados/loopback, schemes != http/https, redirect chain validada |
| 9 | Sem robots.txt | Compliance/legal | `urllib.robotparser` antes de fetch; pula URL se disallowed |
| 10 | Sem idempotência | Worker reiniciar duplica vetores | Constraint UNIQUE em `(usuario_id, url_canonica, chunk_index)`; `ON CONFLICT DO UPDATE` |
| 11 | Agente revisor sem critério objetivo | "Limpa se tiver inlinks demais" — ambíguo | Regra heurística: **max 1 inlink/200 palavras, max 8 total, distância mínima 100 palavras**. LLM revisor só **valida** o cumprimento das regras |
| 12 | Sem versionamento | Rodar 2× sobrescreve resultado | Reusar `versoes_artigo` com `origem="inlinks_v{N}"` |
| 13 | Sem timeout/limite de tamanho de fetch | URL maliciosa de 1GB derruba worker | `max_response_bytes=5MB`, `timeout=20s` |
| 14 | Anchor text não modelado | Crítico em SEO; sem LLM gerando 2-3 opções de âncora natural | Agente "ancorador" gera anchor por inlink baseado no contexto |
| 15 | Score threshold arbitrário | "Filtrar por threshold" sem valor | Default `cosine ≥ 0.78`, configurável; metadata da execução guarda valor usado |
| 16 | Sem observabilidade granular | UI mostra só "executando" para 50 URLs | SSE com eventos finos: `extraindo:5/50`, `embeddings_batch:1/3`, `rerank`, `top_k=15`, etc. |
| 17 | Workflow monolítico | Falha de 1 URL no meio derruba tudo | Tolerância a falha por URL: log + skip, contador de sucessos/falhas no resultado |
| 18 | Não respeita `nofollow`/`sponsored`/`ugc` | SEO best practice ignorada | Default: link `rel="noopener"`, sem `nofollow`. Configurável por usuário |
| 19 | Sem custo previsto na UI | Usuário não sabe quanto vai gastar | Card de pré-execução: "X URLs × custo por URL = Y créditos" |

---

## 3. Arquitetura recomendada (camadas)

```
INGEST       → fetch HTTP + extrai com trafilatura → normaliza URL → cache miss/hit
ENRICH       → chunking semântico → embeddings em batch → classifica tipo/intenção → upsert vetor
MATCH        → busca pgvector Top-K (cosine) → LLM reranker (bonus contextual) → filtra threshold
ANCHOR       → LLM gera 2-3 opções de âncora por inlink candidato (contexto onde será inserido)
INJECT       → algoritmo determinístico escolhe posição (parágrafo + offset) → markdown patch
REVIEW       → revisor LLM valida (sentido preservado? regras heurísticas cumpridas?) → retry se falha
PERSIST      → versão N em `versoes_artigo` + linhas em `inlinks_sugeridos` + final markdown
```

---

## 4. Decisões técnicas confirmadas

| Decisão | Escolha | Alternativas avaliadas |
|---|---|---|
| Extração HTML | **trafilatura + selectolax** | LLM como limpador (caro), readability puro (qualidade pior) |
| Re-ranker | **Cosine pgvector + bônus contextual via 1 chamada LLM** | Cohere Rerank API ($), cross-encoder local (lento) |
| Renderização JS | **Não na v1 — só httpx + extração estática** | Playwright global, microserviço separado (postergado) |
| Aprovação | **100% IA — sem HITL `interrupt()`** | Granular por inlink, em lote, edição inline (postergado) |

---

## 5. Modelo de dados

### Migration nova (`backend/migrations/versions/XXXX_inlinks_automaticos.py`)

**Estender** `conteudos_vetores`:

```sql
ALTER TABLE conteudos_vetores ADD COLUMN url_canonica TEXT;
ALTER TABLE conteudos_vetores ADD COLUMN chunk_index INT;  -- NULL = resumo global
ALTER TABLE conteudos_vetores ADD COLUMN tipo_recurso VARCHAR(20);  -- 'pilar' | 'candidato'
ALTER TABLE conteudos_vetores ADD COLUMN html_hash VARCHAR(64);
ALTER TABLE conteudos_vetores ADD COLUMN tokens INT;
CREATE UNIQUE INDEX uniq_vetor_url_chunk ON conteudos_vetores (usuario_id, url_canonica, chunk_index)
  WHERE url_canonica IS NOT NULL;
```

**Nova tabela** `inlinks_sugeridos`:

```sql
CREATE TABLE inlinks_sugeridos (
  id UUID PRIMARY KEY,
  execucao_id UUID NOT NULL REFERENCES execucoes_ferramentas(id) ON DELETE CASCADE,
  url_origem TEXT NOT NULL,           -- pilar (alvo do inlink)
  url_destino TEXT NOT NULL,          -- candidato escolhido
  anchor_text TEXT NOT NULL,
  paragrafo_idx INT NOT NULL,
  offset_chars INT NOT NULL,
  score_total FLOAT NOT NULL,
  score_semantico FLOAT NOT NULL,
  score_contexto FLOAT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'aplicado',  -- 'aplicado' | 'rejeitado_revisor'
  motivo_rejeicao TEXT,
  rel_attr VARCHAR(50) DEFAULT 'noopener',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_inlinks_execucao ON inlinks_sugeridos(execucao_id);
```

---

## 6. Workflow LangGraph

Arquivo novo: `backend/app/agents/workflow_inlinks.py`

```
StateGraph(EstadoInlinks):

  validar_e_normalizar    → valida URLs (SSRF, robots.txt), normaliza canônica, dedup
  extrair_pilar           → trafilatura, gera html_hash, classifica tipo/intenção
  extrair_candidatos      → asyncio.gather com Semaphore(per_host=2, global=10), com cache Redis
                            → produz lista [(url, html_limpo)] tolerando falhas
  enriquecer_pilar        → chunking + embeddings batch + upsert vetor (chunk_index NULL = resumo)
  enriquecer_candidatos   → chunking + embeddings batch + upsert vetor por chunk
  match_e_rerank          → query pgvector com embedding do resumo do pilar
                            → Top-K (default 30) por cosine
                            → LLM reranker classifica relevância contextual (1 chamada com lista)
                            → score = 0.7*cosine + 0.3*contexto_llm
                            → filtra threshold (≥0.78) → max 8
  gerar_ancoras           → para cada candidato escolhido, LLM gera 2-3 opções de âncora
                            naturais para o contexto onde serão inseridas no pilar
  injetar                 → algoritmo determinístico: encontra parágrafos do pilar com
                            keywords compatíveis, calcula posição, aplica patch markdown,
                            respeita regras (1/200 palavras, distância mínima)
  revisar                 → LLM revisor checa: (a) sentido preservado, (b) regras cumpridas,
                            (c) âncoras soam naturais → marca aplicado/rejeitado por inlink
                            → se rejeitar > 50%, faz 1 retry da injeção com feedback
  persistir               → INSERT em inlinks_sugeridos, versoes_artigo (origem='inlinks_v1'),
                            atualiza execucao com resultado_json
```

**Sem `interrupt()` HITL** — fluxo autônomo conforme decisão.

---

## 7. Componentes técnicos novos

### 7.1 Scraper resiliente — `backend/app/core/scraper.py`

- `httpx.AsyncClient` com `timeout=20`, `follow_redirects=True`, `max_redirects=5`
- `trafilatura.extract(html, output_format='markdown', include_links=False, include_images=False)`
- Validação SSRF: rejeita hosts em `127.0.0.0/8`, `10/8`, `192.168/16`, `172.16/12`, `169.254/16`, `::1`, IPv6 ULAs
- `robots.txt`: cache em Redis 24h, parse com `urllib.robotparser`
- User-Agent: `SeoSaaSBot/1.0 (+https://seo-saas.app/bot)`
- Limite de bytes: ler em chunks, abortar se > 5MB
- Retorno: `dict(url, url_canonica, html_hash, conteudo_md, titulo, tokens, falhou=False)` ou erro estruturado

### 7.2 Embeddings batch — `backend/app/core/embeddings.py`

- Wrapper que aceita `list[str]`, particiona em batches de 100, chama provider, retorna `list[list[float]]`
- Cache por `sha256(texto)` em Redis (TTL 30 dias)
- Reusa fallback de `graceful_degradation.py:30-56`

### 7.3 Chunker — `backend/app/core/chunker.py`

- Split por parágrafo (`\n\n`)
- Acumula até `max_tokens=800` (tokenizer tiktoken)
- Overlap de 100 tokens entre chunks
- Retorna `list[Chunk(texto, tokens, ordem)]`

### 7.4 Re-ranker LLM (dentro do agente match)

- Prompt: "Para o tópico X, classifique cada URL abaixo de 0–10 quanto à relevância contextual"
- 1 chamada LLM com lista (não N chamadas)
- Output JSON estruturado (`response_format={"type": "json_object"}`)

### 7.5 Injetor determinístico — `backend/app/agents/inlinks/injector.py`

Para cada inlink candidato:

1. Encontra todos os parágrafos do pilar onde palavras-chave do candidato aparecem
2. Pontua cada candidato-parágrafo (densidade de keywords)
3. Escolhe melhor parágrafo + offset (primeira ocorrência da keyword da âncora)
4. Aplica patch: `paragrafo[:offset] + f"[{anchor}]({url})" + paragrafo[offset+len(anchor_match):]`
5. Atualiza tracker de distância para próximo inlink

---

## 8. Frontend (Next.js 16)

### 8.1 Rotas

- `app/(app)/ferramentas/inlinks-automaticos/page.tsx` — formulário de execução
- O detalhe e histórico **reusam** `app/(app)/ferramentas/historico/[id]/page.tsx` (já genérico — usa `execucao.ferramenta` para discriminar)

### 8.2 Componentes novos

- **`components/ferramentas/formulario-inlinks.tsx`**
  - Step 1: Conteúdo pilar (URL **ou** textarea markdown)
  - Step 2: URLs candidatas (textarea, 1 por linha) ou upload `.txt/.csv` — limite 100 URLs
  - Step 3: Configurações (threshold de score, max de inlinks, rel_attr)
  - Step 4: Confirmação com **estimativa de custo** computada localmente
- **`components/ferramentas/inlinks-resultado.tsx`** — tabela com colunas: URL destino, âncora aplicada, parágrafo, score; chips status; botão "Ver no contexto" (highlight no preview)

### 8.3 Reuso direto

- `useExecucao` (já tem `criarExecucao`, `conectarProgresso`, sem aprovação)
- `BarraProgressoWorkflow` — adicionar nomes dos novos nodes em `NODE_LABELS`
- `PreviewArtigo` — render do markdown final (com inlinks visíveis como `[âncora](url)`)
- `PageHeader`, `StatCard`, `EmptyState`

### 8.4 Catálogo

- Editar `app/(app)/ferramentas/page.tsx:62-103` — adicionar 3º card linkando para `/ferramentas/inlinks-automaticos` com ícone `Link2Icon`
- Atualizar `StatCard "Ferramentas ativas"` de `1` para `2`

### 8.5 Tipos — `src/types/ferramenta.ts`

```ts
type InlinksRequest = {
  pilar_url?: string;
  pilar_markdown?: string;
  candidatas_urls: string[];
  threshold_score?: number;  // default 0.78
  max_inlinks?: number;      // default 8
  rel_attr?: 'noopener' | 'nofollow' | 'sponsored' | 'ugc';
};

type InlinkSugerido = {
  url_destino: string;
  anchor_text: string;
  paragrafo_idx: number;
  score_total: number;
  status: 'aplicado' | 'rejeitado_revisor';
  motivo_rejeicao: string | null;
};
```

---

## 9. Pricing / billing

Atualizar `backend/app/services/ferramenta_service.py`:

- Custo base: **15 créditos** (extração pilar + revisor + persistência)
- Custo por URL processada com sucesso: **+1 crédito** (capping em 60)
- Imagem: **0** (não há geração de imagem)
- Métrica: cobrar **só URLs que produziram embedding** (falha de fetch não conta)
- Fórmula: `min(15 + n_candidatas_processadas, 60)`
- UI mostra estimativa: `15 + len(candidatas_urls) → max 60`

---

## 10. Segurança / Compliance

- **SSRF**: lista de hosts bloqueados + validação de IP resolvido (DNS lookup antes do fetch)
- **Robots.txt**: respeitado, cache 24h
- **User-Agent identificável**
- **Tamanho máximo**: 5MB por resposta
- **Timeout**: 20s
- **TLS**: validar certificados (httpx default), sem `verify=False`
- **Validação Pydantic**: máx 100 URLs, schemes http/https, comprimento URL ≤ 2048

---

## 11. Caching e idempotência

- **Cache de scrape**: chave `scrape:{url_canonica}:{html_hash}` Redis TTL 7d → reusa entre execuções
- **Cache de embedding**: chave `emb:{sha256(texto)}` Redis TTL 30d
- **Cache robots.txt**: chave `robots:{host}` Redis TTL 24h
- **Idempotência DB**: UNIQUE em `(usuario_id, url_canonica, chunk_index)` com ON CONFLICT DO UPDATE
- **Idempotência execução**: ARQ `job_id = execucao_id` evita duplo enqueue

---

## 12. Observabilidade

Eventos SSE granulares (publicar via `workflow_events.publish_event`):

- `validar_urls`, `extrair_pilar`, `extrair_candidatos:N/M` (progresso live)
- `embeddings_batch:i/total`, `rerank`, `top_k_selected:K`
- `gerando_ancoras`, `injetando`, `revisando`, `concluida`

Resultado final em `resultado_json`:

```json
{
  "n_candidatas_validas": 47,
  "n_aplicadas": 6,
  "n_rejeitadas": 2,
  "custo": 62,
  "top_scores": [0.92, 0.88, 0.85, 0.82, 0.80, 0.79],
  "inlinks": [...]
}
```

Logs estruturados (mantém `logging` padrão do projeto, não introduzir structlog ainda).

---

## 13. Testes (`backend/tests/`)

- `test_scraper_extracao.py` — fixtures HTML estáticos (blog comum, página produto), valida limpeza
- `test_scraper_ssrf.py` — tenta IPs privados, redirect chain malicioso, scheme `file://` → todos bloqueados
- `test_chunker.py` — texto longo gera chunks com overlap correto e tamanho ≤ max
- `test_workflow_inlinks_e2e.py` — mock httpx + LLM, roda workflow completo em Postgres de teste
- `test_injector.py` — valida regras (max 1/200 palavras, distância mínima)
- Frontend: `e2e/inlinks.spec.ts` (Playwright) — formulário → execução → resultado

---

## 14. Roadmap por fases

### Fase 1 (MVP, ~3-4 dias)
Fluxo completo: extrai → indexa → encontra → injeta → revisa → persiste

- migration alembic
- scraper + extração trafilatura
- embeddings batch + chunker
- workflow LangGraph + nodes
- frontend formulário + resultado
- pricing
- testes essenciais

### Fase 2 (~1-2 dias) — refinos

- Cache Redis (scrape + embedding)
- Rate limit por host
- robots.txt
- Observabilidade SSE granular
- Testes e2e

### Fase 3 (futuro) — opcionais

- Histórico de performance dos inlinks (CTR via integração GA?)
- Penalização por rejeição via histórico
- Playwright fallback em microserviço se demanda surgir
- Cohere Rerank se qualidade do reranker LLM não for suficiente

---

## 15. Arquivos críticos a modificar/criar

### Criar (backend)
- `backend/migrations/versions/XXXX_inlinks_automaticos.py`
- `backend/app/core/scraper.py`
- `backend/app/core/chunker.py`
- `backend/app/core/embeddings.py` (wrapper batch — pode ser inline em `graceful_degradation` se preferir)
- `backend/app/agents/workflow_inlinks.py`
- `backend/app/agents/inlinks/extrator.py`
- `backend/app/agents/inlinks/reranker.py`
- `backend/app/agents/inlinks/ancorador.py`
- `backend/app/agents/inlinks/injector.py`
- `backend/app/agents/inlinks/revisor.py`
- `backend/app/models/inlink_sugerido.py`
- `backend/app/routers/ferramentas_inlinks.py` (ou estender `ferramentas.py`)
- `backend/app/services/inlink_service.py`

### Criar (frontend)
- `frontend/src/app/(app)/ferramentas/inlinks-automaticos/page.tsx`
- `frontend/src/components/ferramentas/formulario-inlinks.tsx`
- `frontend/src/components/ferramentas/inlinks-resultado.tsx`

### Editar
- `backend/app/models/conteudo_vetor.py` — adicionar campos
- `backend/app/worker.py` — registrar tarefa `executar_inlinks`
- `backend/app/services/ferramenta_service.py` — fórmula de custo da nova ferramenta
- `backend/pyproject.toml` — `trafilatura>=1.12`, `selectolax>=0.3.21`, `tiktoken>=0.8`
- `frontend/src/app/(app)/ferramentas/page.tsx` — adicionar card no catálogo
- `frontend/src/hooks/use-execucao.ts` — `NODE_LABELS` com novos nodes
- `frontend/src/types/ferramenta.ts` — `InlinksRequest`, `InlinkSugerido`

---

## 16. Verificação end-to-end

1. **Banco**: `make migrate` aplica migration sem erro; `psql` confirma tabela `inlinks_sugeridos` e colunas novas em `conteudos_vetores`
2. **Backend isolado**: `pytest tests/test_workflow_inlinks_e2e.py -v` — workflow completo verde
3. **Backend integrado**: rodar `make dev` + `arq app.worker.WorkerSettings`; `curl POST /api/ferramentas/inlinks-automaticos` com JSON válido → retorna `execucao_id`; `curl GET /api/ferramentas/historico/{id}/progresso` → SSE com nodes esperados em ordem
4. **SSRF**: `curl POST` com `pilar_url=http://localhost:5432` → 422; com `pilar_url=http://169.254.169.254` → 422
5. **Frontend**: abrir `http://localhost:3000/ferramentas/inlinks-automaticos`, preencher 5 URLs reais (ex: posts de um blog), submeter → ver progresso em tempo real → resultado com inlinks aplicados
6. **Idempotência**: rodar mesma execução duas vezes consecutivas → segunda hit cache (visível em logs `cache hit`), tempo total < 10s
7. **Robustez**: passar 1 URL inválida + 4 válidas → execução completa, resultado mostra `n_candidatas_falhas=1, n_aplicadas≤4`
8. **Custo**: 5 URLs → exatamente 20 créditos debitados (15 base + 5)
9. **Catálogo**: dashboard `/ferramentas` mostra 3º card com link funcionando, contador "Ferramentas ativas" = 2
