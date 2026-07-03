# SPEC — Inlinks: descoberta automática de candidatas (índice do site por cliente)

**Status:** ✅ implementada (2026-07-03) · **o próximo salto de valor das duas ferramentas**

> **Notas da implementação** (desvios conscientes da v1):
> - Endpoints em `/api/clientes/{id}/indexar-site`, `/{id}/indice-site` e `/{id}/candidatas`
>   (a descoberta ficou no router de clientes, não em `/ferramentas/inlinks/candidatas`).
> - Páginas sem conteúdo redacional são contadas como falha (não indexadas via pseudo-slug) —
>   o pseudo-alvo de slug para o Distribuir fica para a v1.1.
> - Reserva fixa pelo teto (500 páginas → 30 créditos); confirmação pelo real (só páginas novas).
> - Indexar uma URL desativa vetores ativos anteriores dela (unique parcial por
>   usuario+url+chunk) — a versão mais recente do conteúdo vence, inclusive para as ferramentas.
**Escopo:** backend (migration, scraper/sitemap, worker, 2 endpoints) + frontend (2 formulários + página do cliente)
**Crédito:** nova cobrança de indexação (ver §4); descoberta (consulta) é grátis
**Depende de:** nada das specs planejadas; recomendável após [SPEC_Inlinks_Cache_Duravel_Embeddings](SPEC_Inlinks_Cache_Duravel_Embeddings.md)
**Vale para:** Receber ([[.]]) e Distribuir ([[../inlinks-reversos]])

---

## Contexto

Hoje o usuário precisa **colar as URLs candidatas na mão** — quem tem um blog com 300 posts não
sabe de cabeça quais deles podem linkar (ou receber link de) uma página. Esse é o maior atrito de
uso das duas ferramentas e a razão de execuções pequenas (3-10 candidatas). A infraestrutura para
resolver já existe quase toda: pgvector com HNSW (`conteudos_vetores`), scraper resiliente com
SSRF/robots/cache, chunker, embeddings em batch e worker ARQ. Falta ligar: **indexar o site do
cliente uma vez e deixar o banco vetorial encontrar as candidatas**.

Bônus estrutural: o índice por cliente corrige o known-issue documentado em
`workflow_inlinks.py` ("vetores não são por-cliente nesta versão") — o reuso de vetores passa a
ser escopado por `cliente_id`.

## Decisões de produto (travadas nesta spec)

| Tema | Decisão |
|---|---|
| Fonte | `sitemap.xml` (e índices de sitemap) do domínio do cliente — **sem crawl profundo** de links na v1 |
| Autonomia | Descoberta **sugere, o usuário revisa**: a lista entra pré-marcada no formulário e é editável antes de executar. A execução em si continua cobrando por URL processada como hoje |
| Escopo do índice | Por `cliente_id`; teto de páginas por índice (default 500) |
| Atualização | Manual ("Reindexar") na v1; agendamento automático é v2 |

## Mudanças

### 1. Modelo de dados

- `conteudos_vetores`: preencher `cliente_id` (coluna já existe? verificar — senão migration) e
  novo `tipo_recurso='site'`; índice `(cliente_id, tipo_recurso)`.
- Nova tabela `indices_site`: `cliente_id` (unique), `dominio`, `status`
  (indexando/pronto/falhou), `n_paginas`, `n_falhas`, `atualizado_em`, `erro_msg`.
- Reuso do workflow de vetores existente (cleaner/enriquecedor/chunker/embeddings + upsert por
  `html_hash`) — reindexar só reprocessa páginas cujo hash mudou.

### 2. Backend — indexação (job ARQ)

- `POST /api/clientes/{id}/indexar-site` → valida domínio do cliente, reserva créditos, enfileira
  `indexar_site` (job ARQ novo, timeout próprio ~30min).
- Pipeline do job: baixar sitemap (aceitar sitemap-index; respeitar robots; SSRF guard do scraper)
  → filtrar URLs do mesmo domínio, deduplicar, cortar no teto → scrape em paralelo (semáforo
  por host já existente) → cleaner+enriquecedor+embeddings **somente para hash novo** → upsert
  em `conteudos_vetores` com `cliente_id` → atualizar `indices_site` + SSE de progresso
  (`extraindo N/M`, reusar eventos).
- Páginas sem conteúdo redacional (boilerplate/categoria): indexar mesmo assim com o pseudo-alvo
  de slug (mecanismo do Distribuir) — são alvos válidos para o Distribuir.

### 3. Backend — descoberta (consulta síncrona, grátis)

`GET /api/ferramentas/inlinks/candidatas?cliente_id=...&url=...|texto=...&modo=receber|distribuir&k=30`
1. Resolve o embedding da consulta: URL → scrape+embedding (com cache); texto → embedding direto.
2. Busca pgvector top-K em `conteudos_vetores` do cliente (`tipo_recurso='site'`, cosine,
   excluindo a própria URL).
3. Retorna `[{url, titulo, score, resumo}]` ordenado — **sem LLM** (o juiz roda na execução;
   a descoberta é recall barato, coerente com a arquitetura "cosine = pré-ranking").

### 4. Billing

- Indexação: `10 + ceil(n_paginas_processadas/25)` créditos, teto 40; reindexação incremental
  cobra só pelas páginas com hash novo (mínimo 5). Reserva pelo teto, confirma pelo real —
  mesmo padrão `_obter_reserva_estimada` das demais ferramentas.
- Descoberta: 0 créditos (consulta a índice já pago).
- Execução das ferramentas: inalterada.

### 5. Frontend

- **Formulários (Receber e Distribuir)**: no passo de candidatas, botão "Buscar candidatas do
  site" (habilitado se o cliente selecionado tem índice `pronto`): abre lista com checkbox por
  sugestão (score visível), pré-marcadas as top-10; "Adicionar selecionadas" injeta na lista
  atual. Sem índice: CTA "Indexar site do cliente" levando à página do cliente.
- **Página do cliente**: card "Índice do site" — status, nº de páginas, última atualização,
  botão Indexar/Reindexar com custo estimado, barra de progresso (SSE reusado).
- Seleção de cliente passa a ser primeiro campo dos dois formulários (hoje o Receber não pede
  cliente — verificar impacto no billing/histórico).

## Não-objetivos (v1)

Crawl além do sitemap · atualização agendada · executar a ferramenta direto da descoberta sem
revisão da lista · descoberta cross-cliente.

## Verificação

- Unit: parse de sitemap (index + urlset + malformado), teto de páginas, incremental por hash,
  billing da indexação, busca escopada por cliente (cliente A nunca vê vetor do B).
- E2E: indexar um site real pequeno (~30 páginas) → descoberta para um pilar retorna candidatas
  óbvias no top-5 → rodar o Receber com as sugeridas → resultado normal do pipeline.
- Segurança: sitemap apontando para host privado → URLs bloqueadas pelo SSRF guard (teste).

## Riscos

- **Sites grandes**: teto de 500 páginas na v1 + mensagem clara ("indexamos as 500 primeiras do
  sitemap"); priorizar URLs por profundidade de path como heurística.
- **Sitemap ausente/ruim**: fallback v1 = erro claro com instrução ("informe URLs manualmente
  como hoje") — crawl de links só na v2.
- **Volume no pgvector**: 500 páginas × ~4 chunks × 1024 dims ≈ 8MB/cliente no Supabase free
  (500MB) — ok para dezenas de clientes; monitorar.
- **Multi-tenant**: o escopo por `cliente_id` nas consultas é requisito de segurança (IDOR) —
  cobrir com teste de autorização no endpoint.
