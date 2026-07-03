# SPEC — Ferramenta "Distribuir Inlinks"

**Status:** ✅ implementado · **Escopo:** backend (novo workflow + rota + worker) + frontend (nova página) + cobrança · **Crédito:** modelo separado, similar ao Inlinks Automáticos
**Reusos:** [[SPEC_Ferramenta_Inlinks_Automaticos]] (extrator, scraper, enriquecedor, cleaner, inseridor com Fix A/B/C, revisor, formatador, cache de vetores)

## 1. Visão geral

Ferramenta inversa ao Inlinks Automáticos. Hoje:

| Inlinks Automáticos | Distribuir Inlinks |
|---|---|
| 1 **pilar** + N candidatas | 1 **URL alvo** + N candidatas |
| Modifica o pilar inserindo links **para** as candidatas | Para cada candidata, descobre onde inserir um link **para** a URL alvo |
| Resultado: 1 markdown modificado | Resultado: até N markdowns modificados (uma por candidata viável) |

Caso de uso: o usuário acabou de publicar uma página comercial/landing/pillar e quer plantar links internos apontando para ela a partir de outros artigos do site.

## 2. Conceito de reuso

O inseridor.py já resolve "dado um pilar e candidatos, escolha trechos do pilar para virar âncoras dos candidatos". Invertendo a semântica, basta chamar `inserir_inlinks(candidata_md, [alvo], ...)` para cada candidata: a candidata passa a ser o "pilar local" da chamada, e a URL alvo é o único "candidato".

Toda a inteligência (boost de keyword, validação de palavra-chave, threshold relaxado quando kw passou, regra `min_distance_words`, etc.) é herdada automaticamente.

## 3. Modelo de dados

### 3.1 Reuso de tabelas existentes

Não cria tabelas novas. Reusos:

- **`execucoes_ferramentas`**: nova entrada `ferramenta='distribuir_inlinks'`. Campo `entrada_json` guarda `{url_alvo, candidatas_urls, threshold_score, max_inlinks_por_candidata, rel_attr}`. `resultado_json` espelha estrutura do Inlinks atual mas com lista de candidatas processadas em vez de 1 pilar.
- **`inlinks_sugeridos`**: campos semanticamente compatíveis. Para esta ferramenta:
  - `url_origem` = URL da candidata (onde o link será inserido)
  - `url_destino` = URL alvo (única, repete em todas as linhas da execução)
  - `paragrafo_idx`, `offset_chars`, `trecho_original`, `anchor_text`, `score_*`, `status`, `motivo_*` — idênticos.
- **`conteudos_vetores`**: cache compartilhado por `(usuario_id, url_canonica, html_hash)`. Se a URL alvo ou alguma candidata já foi processada por qualquer ferramenta, reusa embeddings.
- **`versao_artigo`**: hoje guarda 1 versão por execução. Para `distribuir_inlinks`, guardar N versões (uma por candidata viável), com `versao=1..N` e `origem=f"distribuir_v{idx}_{slug_candidata}"`. Já existe lógica de versionamento; só estender a chave `origem`.

### 3.2 Sem alteração de schema

Nenhuma migration necessária. Validei: `inlinks_sugeridos.url_origem` e `url_destino` são VARCHAR sem constraint que ligue ao pilar/candidata específico.

## 4. Backend

### 4.1 Schemas (`app/schemas/inlinks_reversos.py`, novo)

```python
from pydantic import BaseModel, Field, HttpUrl, field_validator

class DistribuirInlinksRequest(BaseModel):
    url_alvo: HttpUrl
    candidatas_urls: list[HttpUrl] = Field(..., min_length=1, max_length=100)
    threshold_score: float = Field(0.6, ge=0.0, le=1.0)
    max_inlinks_por_candidata: int = Field(1, ge=1, le=3)
    rel_attr: str = Field("noopener", pattern="^(noopener|nofollow|sponsored|ugc)$")

    @field_validator("candidatas_urls")
    @classmethod
    def alvo_nao_pode_estar_em_candidatas(cls, v, info):
        return v  # validação cruzada feita em endpoint após normalização


class CandidataResultado(BaseModel):
    url: str
    url_canonica: str
    titulo: str
    status: str  # "aplicado" | "sugestao_manual" | "sem_match" | "falhou_extracao"
    markdown_modificado: str | None = None
    anchor_text: str | None = None
    trecho_original: str | None = None
    paragrafo_idx: int | None = None
    justificativa: str | None = None
    score_total: float | None = None
    score_semantico: float | None = None
    motivo: str | None = None  # quando sem_match / falhou_extracao


class DistribuirInlinksResultado(BaseModel):
    url_alvo: str
    titulo_alvo: str
    n_candidatas_validas: int
    n_aplicadas: int
    n_sugestoes: int
    n_sem_match: int
    n_falhas: int
    candidatas: list[CandidataResultado]
```

### 4.2 Workflow (`app/agents/workflow_inlinks_reversos.py`, novo)

LangGraph estendendo o padrão do `workflow_inlinks.py`. Nós:

1. **validar_urls**: normaliza, dedup, remove `url_alvo` das candidatas se aparecer.
2. **extrair_alvo**: chama `extrair_pilar(url_alvo)`. Falha aqui aborta a execução.
3. **extrair_candidatas**: `extrair_candidatas(candidatas_urls)`. Falhas individuais não abortam — viram `status="falhou_extracao"`.
4. **enriquecer**: idêntico ao `node_enriquecer` atual — chama Cleaner + Enriquecedor + chunker + embedding para alvo + todas as candidatas, com cache `conteudos_vetores`. Mean pooling do alvo. Mean pooling de cada candidata individualmente (para o filtro do passo 5).
5. **filtrar_por_similaridade**: para cada candidata, calcula cosine `media(emb_alvo) × media(emb_candidata)`. Filtra `score >= threshold_score`. Acima do threshold viram input do passo 6; abaixo viram `status="sem_match"` com motivo "Conteúdo da candidata não tem similaridade temática com a URL alvo."
6. **inserir_em_cada_candidata** (paralelo com semáforo): para cada candidata viável:
   - monta `candidato_alvo` = dict no formato esperado pelo Inseridor (titulo, resumo, palavras_chave, score_semantico, score_total)
   - chama `inserir_inlinks(candidata_markdown, [candidato_alvo], usuario_id, max_inlinks=max_inlinks_por_candidata)` — reusa Fix A/B/C
   - captura `(markdown_modificado, lista_inlinks)`. Como passamos 1 só candidato, `lista_inlinks` tem 0 ou 1 elemento.
   - mapeia para `CandidataResultado`:
     - 0 inlinks → `sem_match` com motivo do Inseridor
     - 1 inlink `status=aplicado` → `aplicado`, markdown modificado
     - 1 inlink `status=sugestao_manual` → `sugestao_manual` + motivo
7. **revisar_em_lote** (opcional, ver §4.4): chama Revisor em batch para todas as candidatas aplicadas.
8. **persistir**: salva 1 `inlinks_sugeridos` por candidata processada; salva N `versao_artigo` (uma por candidata aplicada/sugestão), atualiza `resultado_json` com lista completa.

#### Concorrência

`asyncio.gather` com `asyncio.Semaphore(3)` no passo 6 (limite global de LLM). Cada inserção faz 1 chamada Inseridor + chamadas de embeddings em batch. Com 100 candidatas, 3 paralelas, ~15s por candidata: ~500s (8min) — dentro do timeout proposto.

#### Timeout

Adicionar setting `workflow_distribuir_inlinks_timeout: int = 1800` (30min). Diferente do timeout atual (600s) porque processa N vezes mais Inseridor.

### 4.3 Cleaner/Formatador

- **Cleaner**: roda em cada candidata como hoje (limpa boilerplate de "Leia também", etc.). Necessário porque candidatas podem ser artigos com muito ruído.
- **Formatador**: NÃO roda. Diferente do Inlinks atual, aqui não estamos editando estruturalmente o pilar — só inserindo 1 link na candidata. Manter o markdown da candidata como está, exceto pelo link inserido.

### 4.4 Revisor

**Decisão:** revisor opcional, controlado por flag interna `usar_revisor=True` por default.

Cada candidata aplicada gera 1 inlink isolado. O Revisor original valida coerência de múltiplos inlinks no mesmo pilar — aqui só tem 1. Mas validações como "âncora gramaticalmente quebra a frase" e "tema desconectado" continuam valendo. Vale revisar.

Para evitar custo de N+1 chamadas, fazer uma chamada batch ao Revisor passando as N candidatas aplicadas como uma lista, prompt adaptado:

```
Para cada par (candidata, anchor, paragrafo modificado), valide.
Retorne array com status por par.
```

Se Revisor rejeitar uma, vira `sugestao_manual` com `motivo_rejeicao` do Revisor.

### 4.5 Rota (`app/routers/ferramentas_inlinks_reversos.py`, novo)

```python
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_user
from app.schemas.inlinks_reversos import DistribuirInlinksRequest
from app.services import ferramenta_service, credito_service

router = APIRouter(prefix="/api/ferramentas/distribuir-inlinks", tags=["distribuir-inlinks"])

@router.post("")
async def criar_execucao(req: DistribuirInlinksRequest, user=Depends(get_current_user), db=...):
    # 1. valida url_alvo não está em candidatas (após normalização)
    # 2. calcula custo (n_candidatas × CUSTO_POR_CANDIDATA_DISTRIBUIR)
    # 3. verifica saldo
    # 4. cria execucao_ferramentas com ferramenta='distribuir_inlinks'
    # 5. enfileira job no arq: executar_distribuir_inlinks(execucao_id)
    # 6. retorna {id, status: 'enfileirado', ...}

@router.get("/{execucao_id}")
async def buscar_execucao(execucao_id: str, user=Depends(get_current_user), db=...):
    # retorna estado + resultado_json (com candidatas[])

@router.get("/custo")
async def calcular_custo(n_candidatas: int, user=Depends(get_current_user)):
    # retorna { custo: int, detalhe: str }
```

Registrar em `app/main.py` junto com router de inlinks.

### 4.6 Worker (`app/worker.py`)

Adicionar:

```python
async def executar_distribuir_inlinks(ctx, execucao_id: str):
    logger.info("Iniciando distribuir inlinks execucao_id=%s", execucao_id)
    try:
        from app.agents.workflow_inlinks_reversos import executar_workflow_distribuir_inlinks
        await executar_workflow_distribuir_inlinks(execucao_id)
        logger.info("Distribuir inlinks concluido execucao_id=%s", execucao_id)
    except Exception as e:
        logger.error("Distribuir inlinks falhou execucao_id=%s: %s", execucao_id, e)
```

Em `WorkerSettings.functions`, adicionar `executar_distribuir_inlinks`.

### 4.7 Cobrança (`app/services/ferramenta_service.py`)

```python
CUSTO_BASE_DISTRIBUIR_INLINKS = 15
CUSTO_POR_CANDIDATA_DISTRIBUIR = 1

def calcular_custo_distribuir_inlinks(n_candidatas: int) -> int:
    return CUSTO_BASE_DISTRIBUIR_INLINKS + n_candidatas * CUSTO_POR_CANDIDATA_DISTRIBUIR
```

Política igual ao Inlinks atual:
- Se 0 candidatas processáveis: cobra 0 (extrações falharam).
- Se `n_aplicadas + n_sugestoes == 0`: cobra apenas custo por URL (sem base).
- Caso contrário: cobra integral.

## 5. Frontend

### 5.1 Página `/ferramentas/distribuir-inlinks`

Arquivo: `frontend/src/app/(app)/ferramentas/distribuir-inlinks/page.tsx`. Layout análogo a `/ferramentas/inlinks`:

- Header: "Distribuir Inlinks" + descrição "Encontre páginas do seu site para receber links apontando para uma URL específica."
- Wizard de 3 passos: **URL alvo** → **Candidatas** → **Confirmar**.

### 5.2 Formulário (`frontend/src/components/ferramentas/formulario-distribuir-inlinks.tsx`)

Reusar 80% do `formulario-inlinks.tsx`. Passos:

**Passo 1 — URL alvo**
- Único campo: `Input` com URL alvo.
- Validação: HTTPS only.

**Passo 2 — Candidatas**
- Mesma UI do Inlinks atual: toggle "Uma por uma" / "Colar em lote", chips com URLs adicionadas, limites 1-100.
- Configurações: `max_inlinks_por_candidata` (default 1), `threshold_score` (default 0.6), `rel_attr`.

**Passo 3 — Confirmar**
- Resumo: URL alvo, número de candidatas, custo estimado.
- Botão "Iniciar distribuição".

### 5.3 Tela de resultado (`frontend/src/components/ferramentas/distribuir-inlinks-resultado.tsx`)

Layout:

```
URL alvo: https://example.com/produto-x

Resumo: 12 aplicadas | 3 sugestões manuais | 8 sem match | 0 falhas

[Aba: Aplicadas (12) | Sugestões (3) | Sem match (8) | Falhas (0)]

Em cada aba, lista expansível por candidata:
  ✓ https://example.com/artigo-1
    Anchor: "linguagem mais usada" no parágrafo 5
    Justificativa: ...
    [Copiar markdown modificado] [Ver diff]
```

Componente `<CandidataAccordion>` reusável: ao expandir, mostra:
- Anchor + parágrafo
- Trecho original × trecho com link (diff inline)
- Botão "Copiar markdown modificado" (copia o markdown completo da candidata com o link aplicado)
- Botão "Ver markdown completo" (modal)

### 5.4 Navegação

Adicionar item na sidebar (`frontend/src/components/layout/sidebar.tsx`):

```
- Inlinks (existente)
- Distribuir Inlinks (novo, ícone reverso ou compartilhamento)
```

## 6. Performance e limites

### 6.1 Tempo estimado

Com 100 candidatas, concorrência LLM = 3, ~15s por chamada Inseridor + 1 chamada batch Revisor + extrações paralelas:

| Etapa | Tempo |
|---|---|
| Extração alvo + 100 candidatas (paralelo, semáforo 10) | ~30-60s |
| Enriquecer (Cleaner + Enriquecedor, paralelo 3) | ~3-5min (cold) ou 5-15s (cache) |
| Embedding batch | ~10-20s |
| Filtragem por cosine | <1s |
| Inseridor em paralelo (3 simultâneos) | ~5-8min para 100 candidatas |
| Revisor batch único | ~30-60s |
| Persistência | <5s |
| **Total cold** | **~10-15 min** |
| **Total cache hit total** | **~3-5 min** |

### 6.2 Caps de segurança

- `max_candidatas = 100`.
- `workflow_distribuir_inlinks_timeout = 1800` (30min, com margem 2x sobre estimativa).
- Se mais de 50% das extrações falharem, abortar com erro claro.

### 6.3 Cache

Aproveitamento crítico. URLs comuns (artigos do mesmo blog) tendem a ser reusadas entre execuções. `conteudos_vetores` indexado por `(usuario_id, url_canonica, html_hash, ativo=true)` deve dar hit > 80% após primeira execução.

## 7. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Timeout em execuções grandes | Cap em 100, timeout 30min, paralelismo controlado. Se ainda estourar, paginar (mas v2). |
| Custo alto de tokens | gpt-4.1 só onde necessário (Inseridor + Revisor). Cleaner e Enriquecedor permanecem em gpt-4o-mini. |
| URL alvo na lista de candidatas | Validar no router após `_normalizar_url`. Retornar erro 400 claro. |
| Candidata = mesma URL do alvo | Tratado pela validação acima. |
| Candidata sem fit nenhum | Já tratado pelo filtro de similaridade (passo 5) + Fix C do Inseridor (sugestao_manual visível). |
| Inseridor escolhe trecho não-literal | Comportamento herdado do Inlinks atual (Fix A reforçou). Variabilidade do LLM existe. |
| Race condition no cache | `IntegrityError` + retry já existe em `node_enriquecer`. |
| Cobrança de execução que falha cedo | `_finalizar_sucesso_distribuir_inlinks` aplica mesma política: 0 candidatas válidas → 0 créditos. |

## 8. Plano de execução em fases

### Fase 1 — Backend core (2-3h)

1. `app/schemas/inlinks_reversos.py` — Pydantic models.
2. `app/agents/workflow_inlinks_reversos.py` — workflow LangGraph com os 8 nós.
3. `app/services/ferramenta_service.py` — adicionar `calcular_custo_distribuir_inlinks`, `_finalizar_sucesso_distribuir_inlinks`.
4. `app/routers/ferramentas_inlinks_reversos.py` — POST/GET endpoints.
5. `app/main.py` — registrar router.
6. `app/worker.py` — handler `executar_distribuir_inlinks` + adicionar em `WorkerSettings`.
7. `app/config.py` — `workflow_distribuir_inlinks_timeout = 1800`.

### Fase 2 — Frontend (2-3h)

1. `frontend/src/app/(app)/ferramentas/distribuir-inlinks/page.tsx` — página principal.
2. `frontend/src/components/ferramentas/formulario-distribuir-inlinks.tsx` — wizard 3 passos.
3. `frontend/src/components/ferramentas/distribuir-inlinks-resultado.tsx` — tela de resultado com abas.
4. `frontend/src/components/layout/sidebar.tsx` — link na sidebar.
5. `frontend/src/lib/api.ts` — clientes para POST/GET da nova rota.

### Fase 3 — Validação E2E (1h)

1. Restart backend + worker.
2. Rebuild frontend + copiar para `backend/static`.
3. Teste manual via UI: URL alvo + 3-5 candidatas reais.
4. Validar: aplicadas têm markdown modificado correto, sugestões têm motivo claro, sem_match têm cosine baixo registrado, falhas têm erro registrado.
5. Verificar persistência em `inlinks_sugeridos` e `versao_artigo`.
6. Conferir cobrança de créditos.

### Fase 4 — Polimento (1h)

1. Adicionar à página de histórico (filtro por ferramenta).
2. Texto de ajuda inline (tooltip "O que é?" em cada campo).
3. Mensagens de erro user-friendly.
4. Testar threshold edge cases (0.1, 0.95).

Esforço total estimado: **6-8h de implementação**.

## 9. Não-objetivos

- Sugerir candidatas automaticamente a partir de sitemap (v2).
- Cross-encoder reranker para os candidatos viáveis (v2).
- Aplicar mudanças diretamente no CMS via API (Wordpress, etc.) — v3.
- Análise de já-existência de links no destino (anti-duplicação de links existentes na candidata para o alvo) — v2.
- Suporte a multi-alvo numa execução (lista de alvos × lista de candidatas) — fora de escopo.

## 10. Critério de pronto

- POST `/api/ferramentas/distribuir-inlinks` aceita request válido, retorna `id` + status `enfileirado`.
- Worker processa: log mostra etapas (extrair_alvo, extrair_candidatas, enriquecer, filtrar, inserir, revisar, persistir).
- GET retorna resultado completo com lista de candidatas e seus estados.
- UI mostra wizard funcional, tela de resultado com abas, copy de markdown funciona.
- Cobrança alinhada: 0 valor → 0 créditos; com valor → créditos normais.
- Execução E2E real com 5 candidatas produz pelo menos 1 aplicada quando o fit é forte (pilar do alvo tema relacionado).
- Persistência em `inlinks_sugeridos` e `versao_artigo` correta para inspeção posterior.
