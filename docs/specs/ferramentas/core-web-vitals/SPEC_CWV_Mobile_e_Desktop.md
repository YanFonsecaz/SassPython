# SPEC — CWV: análise Mobile **e** Desktop (sempre as duas)

**Status:** ✅ implementado · **Escopo:** backend (workflow + custo + queries) + frontend (form, dashboard, evolução, histórico)
**Dependências:** workflow CWV atual · **Esforço estimado:** ~1–1,5 dia
**Migration de banco:** **NENHUMA** (ver §6).

## 1. Problema

Hoje a ferramenta analisa **uma estratégia só** por execução:
- O formulário envia um único `estrategia` (`schemas/cwv.py:67`, `estrategia: Estrategia = "mobile"`), default **mobile**.
- O workflow (`agents/cwv/workflow.py`) indexa todo o estado por `url` (string) e chama `fetch_psi(url, estado["estrategia"])` **uma vez por URL** (`:50`), gravando **1 `CwvAnalise` por URL** com aquela estratégia (`node_persistir`, `:249-265`).
- Resultado: o usuário só vê **mobile** (ou só desktop), nunca os dois.

O PageSpeed real mostra Mobile e Desktop lado a lado; o esperado para o cliente é ter as duas visões da mesma URL.

## 2. Decisão (produto)

Confirmado com o usuário:
1. **Sempre rodar Mobile + Desktop** — sem seletor no formulário. Toda análise gera as duas estratégias por URL.
2. **Dashboard com toggle Mobile | Desktop** no topo (como as abas do PageSpeed), trocando métricas + plano de ação + gráfico de evolução.

## 3. Mudanças — Backend

Constante única: `ESTRATEGIAS_CWV = ("mobile", "desktop")` (ex.: em `agents/cwv/workflow.py` ou `config`).

### 3.1 Workflow (`agents/cwv/workflow.py`) — núcleo da mudança
Hoje todo o estado é indexado por `url`. Passa a ser indexado por **`(url, estrategia)`**.

- `EstadoCWV`: trocar `estrategia: str` + `urls_por_template: list[tuple[str,str]]` por **`jobs: list[tuple[str,str,str]]`** = `(template, url, estrategia)`, onde **cada URL aparece duas vezes** (mobile e desktop). Os dicts (`psi_resultados`, `plataformas`, `problemas_por_url`, `llm_stats_por_url`) passam a ser chaveados por uma **chave composta** `chave = f"{estrategia}{url}"` (helper `_chave(url, estrategia)`).
- `node_coletar_psi` (`:33-72`): iterar `jobs`; `fetch_psi(url, estrategia)` por job; gravar em `psi_resultados[chave]`. O `SEMAFORO_PSI` (5) já limita concorrência — agora há ~2× chamadas.
- `node_detectar_plataformas`, `node_analisar_seo`, `node_documentar`, `node_pesquisar_outros`, `node_priorizar`: trocar todas as leituras/escritas de `[url]` por `[chave]`. (Plataforma é a mesma do site, mas detecta-se por job a partir do payload — barato.)
- `node_persistir` (`:236-271`): iterar `jobs`; `persistir_analise(..., estrategia=estrategia_do_job, ...)`. Gera **2 análises por URL**. `analises_persistidas` continua a lista de todos os ids.
- `executar_workflow_cwv` (entry, `:344-357`): construir `jobs` expandindo `urls_obj.itens()` × `ESTRATEGIAS_CWV`. Remover dependência de `entrada["estrategia"]`.

> A barra de progresso (`publish_event`) deve refletir o total dobrado (ex.: "Coletando PSI 3/10" considerando jobs, não URLs).

### 3.2 Schema da requisição (`schemas/cwv.py`)
- O campo `estrategia` da **requisição** (`:67`) deixa de ser usado. Manter compat (aceitar e ignorar) **ou** remover do payload do form. A resposta (`:99`) mantém `estrategia: str` por análise (já correto).

### 3.3 Custo (`services/ferramenta_service.py`)
- `calcular_custo_cwv(n_urls)` → **`base + n_urls × CUSTO_POR_URL_CWV × 2`** (2 estratégias). Ex.: `15 + n_urls*2`.
- Revisar `CUSTO_MAX_CWV` (hoje 50): com 50 URLs × 2 + 15 = 115; o cap atual zera o custo extra acima de ~17 URLs. **Decisão:** subir o cap (ex.: 100) para refletir o custo real de PSI, ou manter (subcobra, mas favorece o cliente). *Recomendado: subir para ~100.*
- Atualizar a reserva de créditos no POST (`routers/ferramentas_cwv.py`) e o endpoint de custo (`buscarCustoCwv`) para usar o novo cálculo.
- Atualizar o custo da **re-análise** (reanalisar roda ambas também).

### 3.4 Queries de persistência (`services/cwv_persistencia.py`)
Agora há 2 análises por URL por execução. As consultas precisam ficar **strategy-aware**:
- `buscar_analise_com_problemas` (`:97`) / endpoint GET da análise: incluir no retorno os **ids irmãos** por estratégia, ex.: `irmas: {"mobile": <id>, "desktop": <id>}` (mesma `execucao_id` + `url_canonica`). É isso que alimenta o toggle do dashboard.
- `buscar_ultima_analise_url` (`:149`) e `buscar_historico_url` (`:115`): passar a considerar `estrategia` (ex.: retornar a última de **cada** estratégia, ou aceitar `estrategia` como filtro). Os itens do histórico devem expor `estrategia`.
- A resposta de histórico/resumo (`CwvAnaliseResumo`) ganha o campo `estrategia`.

## 4. Mudanças — Frontend

### 4.1 Formulário (`components/cwv/cwv-form.tsx`)
- **Remover** o seletor Mobile/Desktop. Substituir por um aviso discreto: *"Analisamos Mobile e Desktop automaticamente."*
- Remover `estrategia` do submit (`analisarCwv`).
- Atualizar a prévia de custo (passa a ser ×2 por URL) usando o novo `buscarCustoCwv`.

### 4.2 Dashboard da URL (`components/cwv/cwv-url-client.tsx` + `cwv-dashboard-client.tsx`)
- **Toggle Mobile | Desktop** no topo (estado `estrategiaAtiva`). Trocar: `MetricasResumo`, `CwvEstadoBanner`, `PlanoAcaoAccordion`, comparador e `EvolucaoChart`.
- Carregar as duas análises da URL: usar o campo `irmas` do response para buscar a irmã (ou um único endpoint que retorne ambas). Default do toggle = mobile.

### 4.3 Gráfico de evolução (`components/cwv/cwv-evolucao-chart.tsx`)
- Filtrar o histórico pela **estratégia ativa** (comparar mobile↔mobile, desktop↔desktop). Requer `estrategia` em `CwvAnaliseResumo` (`lib/api/cwv.ts`).

### 4.4 Histórico (`components/cwv/cwv-historico-client.tsx`)
- Cada URL passa a ter as duas. Mostrar ambos os scores no card (ex.: *"Mobile 51 · Desktop 88"*) e linkar ao dashboard (que tem o toggle). `buscarHistoricoCwv` deve agrupar por URL trazendo as duas estratégias.

### 4.5 Tipos (`lib/api/cwv.ts`)
- Adicionar `estrategia` em `CwvAnaliseResumo`; adicionar `irmas`/links por estratégia no response da análise.

## 5. Custo (resumo)
- **Antes:** `15 + n_urls × 1` (uma estratégia).
- **Depois:** `15 + n_urls × 2` (mobile + desktop). Tempo e quota PSI ~2×.
- Deixar isso explícito no resumo do formulário (passo Confirmar).

## 6. Migration de banco — **não é necessária**
`CwvAnalise` já suporta as duas:
- `CheckConstraint estrategia IN ('mobile','desktop')` (`models/cwv_analise.py:53-56`).
- **Não há unique constraint em `(execucao_id, url_canonica)`** → 2 linhas (mobile+desktop) por URL na mesma execução são permitidas.
- Índices existentes cobrem as consultas (`ix_cwv_analise_cliente_url_data`, `ix_cwv_analise_execucao`).
- *Opcional (não bloqueante):* índice incluindo `estrategia` se o filtro por estratégia ficar quente — provavelmente desnecessário.

## 7. Critérios de aceite
- [ ] Uma execução com N URLs cria **2N análises** (`status=sucesso`), uma `mobile` e uma `desktop` por URL.
- [ ] Custo cobrado = `15 + N×2` (e prévia no form bate com o cobrado).
- [ ] Dashboard da URL tem toggle Mobile|Desktop que troca métricas, plano de ação e evolução; default mobile.
- [ ] Evolução compara mesma estratégia ao longo do tempo (mobile↔mobile).
- [ ] Histórico mostra as duas estratégias por URL.
- [ ] Re-análise também gera as duas.
- [ ] `tsc`/`build` verdes; sem migration nova; deploy roda `alembic upgrade head` no-op.

## 8. Verificação E2E
Backend no host + `teste@seosaas.com`. Rodar nova análise com 1–2 URLs → confirmar 2N análises no banco (`select estrategia,count(*) from cwv_analise where execucao_id=...`), abrir o dashboard, alternar Mobile/Desktop e ver métricas distintas (PSI mobile ≠ desktop), conferir custo debitado e a evolução por estratégia. Screenshots dos dois estados do toggle.

## 9. Riscos / notas
- **Quota PSI dobra** — o fallback de 2 chaves (`fetch_psi`) e o `SEMAFORO_PSI=5` ajudam; monitorar `cwv_psi_quota_exhausted_total`.
- **Tempo ~2×** por execução — barra de progresso deve refletir jobs (2N).
- **Créditos** — comunicar a mudança de preço (×2/URL) ao usuário final.
- Relacionado: [[SPEC_CWV_Reanalisar_Comparador_Chart]], [[SPEC_Ferramenta_Core_Web_Vitals]].
