# AUDITORIA :: Planilha NPBR (CWV & Loading Speed) × Ferramenta CWV

> **Data:** 2026-07-13
> **Fonte de referência:** `[OFFICIAL ENTERPRISE TEMPLATE - 2026] CWV and Loading Speed Audit _ Neil Patel Brazil.xlsx` (58 abas)
> **Objetivo:** mapear tudo que a planilha entrega manualmente, comparar com a ferramenta CWV atual e definir o caminho para 100% de automação.

---

## Etapa 1 — Análise da planilha

### 1.1 Inventário de abas (58 no total)

| Aba | Estado | Finalidade |
|---|---|---|
| **Client Health Score** | visível | Capa do documento: nome do cliente, URLs analisadas (até 8), objetivo, impactos esperados, participação mobile/desktop (12 meses), gráficos de health score antes/depois |
| **Scores Achieved** | visível | Snapshots mensais por URL: prints de PageSpeed + GTmetrix (CWV mobile/desktop). Estrutura repetida por mês (`» month/25`) — é o registro fotográfico da evolução |
| **Page Experience History** | visível | Prints do relatório CWV do Google Search Console (mobile/desktop), com contagem calculada de métricas pendentes (POOR/IMPROVEMENTS por LCP/INP/CLS) |
| **Checklist** | visível | **Núcleo da auditoria.** 13 itens de Page Experience + 36 audits de PageSpeed. Colunas: item, Status BEFORE (Pass/Fail), Status AFTER (Pass/Fail), Metric Impact (VLOOKUP), Client Implementation Status (dropdown), Client Note, Priority (fórmula sequencial dos Fails), Score Before/After (fórmula), Description, SEO Note. Header calcula % de health antes/depois |
| **CWV Metrics** | visível | Mapa audit → métrica (TBT/INP, LCP, LCP/FCP, CLS, None) com status e prioridade puxados do Checklist por VLOOKUP |
| **TBTINP CWV / LCPFCP CWV / CLS CWV** | visíveis | Visões filtradas do checklist por família de métrica (para o cliente atacar uma métrica por vez) |
| **Checklist base** | oculta | Lista-mestra dos audits (nome EN canônico + descrição; linhas 45-83 mapeiam nomes GTmetrix) — alimenta os dropdowns e VLOOKUPs |
| **Control** | oculta | Série de dados dos gráficos de pizza Pass/Fail antes/depois |
| **Dados** | oculta | Automação embrionária: `IMPORTHTML` do relatório GTmetrix + listas de mapeamento de nomes de audits EN↔PT (PageSpeed e GTmetrix) |
| **AUDITORIA** | oculta | Matriz de priorização **por template**: ~50 itens × 4 tipos de página (Home site, Página interna, Home blog, Artigo blog). Dropdowns: prioridade (ALTA, ALTA/MÉDIA, MÉDIA, MÉDIA/BAIXA, BAIXA, N/A, NENHUMA), status (Aprovado/Reprovado), implementação (Implementado/Não Executado/Em Andamento) |
| **~45 abas por problema** | ocultas | Uma por audit (EN e PT misturados). Estrutura padrão: título + "WHAT DOES IT MEAN?" (explicação didática), tabela de evidências (URL + colunas numéricas específicas do audit com threshold no cabeçalho, ex.: "Task Duration (< 100 ms per task)"), coluna "Strategies" (ação por recurso), "DETAIL OF THE PROBLEM" (guia longo de correção), bloco "Actions needed:" (recomendações redigidas caso a caso) e "Benchmarks closest to the ideal time" (comparação com sites de referência/concorrentes) |

### 1.2 Campos — origem e automatização

Legenda de dificuldade: 🟢 trivial · 🟡 média · 🔴 alta

| Campo | Aba | Tipo | Origem hoje (manual) | Como automatizar | IA? | Validação humana | Dif. |
|---|---|---|---|---|---|---|---|
| Nome do cliente | Health Score | texto | digitado | já existe (cadastro de clientes) | não | não | 🟢 |
| URLs analisadas (até 8) | Health Score | lista URL | digitado | já existe (form URLs por template) | não | sim (escolha) | 🟢 |
| Visitas mobile/desktop 12m | Health Score | número | Google Analytics | GA4 Data API (OAuth) ou aproximar com `form_factors` do CrUX | não | não | 🟡/🔴 |
| Texto de objetivo/impactos | Health Score | texto fixo | template | template + personalização LLM | sim | não | 🟢 |
| Prints PSI/GTmetrix por mês | Scores Achieved | imagem | screenshot manual | métricas estruturadas + gráfico próprio (melhor que print); screenshot da página vem no próprio payload PSI (`final-screenshot`) | não | não | 🟢 |
| Prints GSC (CWV report) | Page Exp. History | imagem | screenshot manual | GSC API (OAuth) ou **CrUX History API** (pública, 25 semanas, sem OAuth) | não | não | 🟡 |
| Pass LCP/INP/CLS assessment | Checklist | Pass/Fail | PSI (dados de campo) | **`loadingExperience` já vem no payload PSI que a ferramenta baixa e descarta** | não | não | 🟢 |
| Mobile-friendly | Checklist | Pass/Fail | avaliação manual | audit `viewport` + heurísticas (font-size, tap targets no Lighthouse) | parcial | recomendado | 🟡 |
| Safe browsing | Checklist | Pass/Fail | manual | Google Safe Browsing API (key própria) | não | não | 🟡 |
| Práticas básicas de segurança | Checklist | Pass/Fail | análise humana | checagem de headers (HSTS, CSP, X-Frame-Options) via request próprio | parcial | recomendado | 🟡 |
| Servido em HTTPS | Checklist | Pass/Fail | manual | audit `is-on-https` do Lighthouse (coletar categoria `best-practices`) ou request próprio | não | não | 🟢 |
| Problemas de SSL | Checklist | Pass/Fail | manual | handshake TLS próprio (validade, cadeia, expiração) | não | não | 🟡 |
| Mixed content | Checklist | Pass/Fail | manual | audit `is-on-https` (itens http) / parse de recursos do `network-requests` | não | não | 🟢 |
| Redirect HTTP→HTTPS 301 | Checklist | Pass/Fail | manual | request próprio a `http://` e seguir cadeia | não | não | 🟢 |
| Pop-ups/interstitiais/ads intrusivos | Checklist | Pass/Fail | análise visual humana | screenshot (payload PSI) + LLM multimodal | **sim** | sim | 🔴 |
| Status Before por audit (36×) | Checklist | Pass/Fail | copiar do PSI | **já existe** (audits falhos do parse PSI) | não | não | 🟢 |
| Status After por audit | Checklist | Pass/Fail | re-audit manual | re-execução + diff (endpoint `/comparacao` já existe; falta amarrar a "campanha") | não | não | 🟡 |
| Metric Impact | Checklist | enum | VLOOKUP | já existe (`metricas_afetadas` na KB) | não | não | 🟢 |
| Client Implementation Status | Checklist | dropdown | **cliente preenche** | campo editável na UI (workflow colaborativo) — não é automatizável por natureza | não | é do cliente | 🟡 |
| Client Note / SEO Note | Checklist | texto livre | humano | SEO Note pode ser gerada por LLM com evidências; Client Note é do cliente | sim/não | sim | 🟡 |
| Priority (sequencial) | Checklist | fórmula | `IFS(Fail → n+1)` | já existe (priorizador determinístico, melhor que o da planilha) | não | não | 🟢 |
| Health Score % antes/depois | Checklist | fórmula | `H2/G2*100` | trivial a partir dos Pass/Fail | não | não | 🟢 |
| Descrição do audit | Checklist | texto | Checklist base | já existe (KB + descrição do Lighthouse) | não | não | 🟢 |
| Prioridade por template (matriz) | AUDITORIA | dropdown | julgamento humano | agregação por `template_tipo` (dado já persistido) + LLM para ajuste fino | sim | recomendado | 🟡 |
| "O que significa" por problema | abas ocultas | texto | template | já existe (KB `descricao`) | não | não | 🟢 |
| Tabela de evidências (recursos, ms, KB) | abas ocultas | tabela | copiar do PSI | **já existe** (`contexto_especifico.items`), subaproveitado no relatório | não | não | 🟢 |
| Strategies (ação por recurso) | abas ocultas | texto | humano | LLM sobre os items (recurso → estratégia) | **sim** | recomendado | 🟡 |
| Detail of the problem / guia | abas ocultas | texto | template | já existe (KB `solucoes` por plataforma + pesquisador) | não | não | 🟢 |
| **Actions needed** (redação caso a caso) | abas ocultas | texto | **humano (valor da consultoria)** | LLM: KB + evidências específicas → recomendação nomeando os recursos reais | **sim** | recomendado | 🟡 |
| Benchmarks de concorrentes | abas ocultas | tabela | rodar PSI nos concorrentes manualmente | rodar PSI em URLs de benchmark e comparar | não | não | 🟡 |
| Critérios de aprovação | Checklist/Control | regra | Pass/Fail binário, score = soma | portar regra (health score) para o backend | não | não | 🟢 |

**Regras de negócio da planilha (resumo):**
- Health Score = nº de Pass / nº total de itens (antes e depois, em %).
- Priority = ordem sequencial apenas dos itens Fail (Pass = 0).
- Metric Impact via mapa audit→métrica (idêntico em espírito ao `AUDIT_METRICAS` da ferramenta).
- Ciclo de vida: auditoria BEFORE → cliente implementa (status por item) → re-auditoria AFTER → recalcula score.
- Evidência sempre com threshold explícito no cabeçalho (ex.: TBT < 200ms, task < 100ms).

---

## Etapa 2 — Ferramenta atual (arquitetura)

### 2.1 Fluxo

```
POST /core-web-vitals/analisar (créditos reservados, rate limit 3/5min)
  → arq (Redis) → executar_workflow_cwv (timeout 1200s)
     LangGraph: coletar_psi → detectar_plataformas → analisar_seo
              → documentar → pesquisar_outros → priorizar → persistir
  → confirma débito, resultado_json, eventos SSE de progresso
```

- **coletar_psi** (`cwv_psi_client.py`): PSI v5, `category=performance`, mobile+desktop por URL (max 50 URLs), 2 API keys com rotação em 429/403, retry exponencial em 5xx, semáforo 5, webhook de alerta. Parse: score de performance, LCP/CLS/INP/FCP/TTFB/TBT, audits falhos (score < 0.9, exclui informativos), nº requests, tamanho do documento. **Descarta o restante do payload (`raw_psi_json={}`), inclusive `loadingExperience` (dados de campo CrUX) e screenshots.**
- **detectar_plataformas** (`cwv_plataforma.py`): 5 camadas (stackPacks → headers → assets → meta generator → sinais fracos), 12 plataformas.
- **analisar_seo** (`cwv/analisador.py`): mapeamento determinístico audit→KB (57 entradas + aliases) e LLM estruturado (gpt-4o-mini, temp 0.1) só para residuais, com validação de códigos e fallback (`kb_codigo=null` + métrica `cwv_kb_miss_total`).
- **documentar** (`cwv/documentador.py`): 100% determinístico — monta markdown da KB (descrição + solução por plataforma + solução geral + links). Severidade por savings quando não há KB.
- **pesquisar_outros** (`cwv/pesquisador.py`): ReAct (gpt-4.1) com `buscar_web`/`fetch_url`/`buscar_docs_lib` (Context7) para audits sem KB, máx 5 por análise, formato de saída fixo.
- **priorizar** (`cwv/priorizador.py`): score = severidade × Σ peso das métricas (LCP 5, CLS 4, INP 4, TBT 3, FCP 2, TTFB 2).
- **persistir** (`cwv_persistencia.py`): `CwvAnalise` (métricas, plataforma, stats LLM) + `CwvProblema` (kb_codigo, severidade, prioridade, contexto, doc). Histórico por URL canônica, comparação com análise anterior (resolvidos/novos/persistentes), análise irmã mobile↔desktop.
- **API**: analisar, reanalisar, execução, análise, histórico, histórico-url, comparação, irmã, override de plataforma (regenera docs), export DOCX (problema e relatório por análise).
- **Frontend**: dashboard, form por template (home/categoria/produto/blog/blogpost/outros), barra de progresso real (SSE), plano de ação em accordion com severidade/prioridade/export, comparador, gráfico de evolução, override de plataforma.

### 2.2 Pontos fortes

1. **Pipeline de coleta e persistência sólido** — retry/rotação de keys, mobile+desktop, cobrança justa (não cobra o que falhou), cancelamento, timeout, eventos de progresso.
2. **KB curada com soluções por plataforma** — 57 entradas × até 5 plataformas é um diferencial real sobre a planilha (que tem texto genérico).
3. **LLM usado com parcimônia** — determinístico onde dá, LLM só em residuais, com validação e fallback. Custo previsível.
4. **Histórico e comparação já modelados** — a planilha faz isso na mão com prints; a ferramenta tem dados estruturados.
5. **Detecção de plataforma** em 5 camadas com override manual.

### 2.3 Pontos fracos / limitações

1. **Só lab data.** `loadingExperience` (CrUX field data) chega no payload e é jogado fora — e é exatamente o critério "passa no assessment de LCP/INP/CLS?" da planilha (as 3 primeiras linhas do Checklist).
2. **Só categoria performance.** Sem `best-practices`/`accessibility`/`seo`, perde `is-on-https`, `viewport` (mobile-friendly) e afins.
3. **Sem conceito de "auditoria/campanha".** Cada execução é isolada; a planilha é um documento vivo before→implementação→after com estado por item.
4. **Análise por URL isolada.** Sem consolidação cross-URL (o mesmo `render-blocking` em 8 URLs vira 16 problemas repetidos, não "1 problema, escopo: todas as páginas" como a planilha organiza).
5. **Recomendação genérica.** `documentacao_md` vem da KB; os recursos reais (`contexto_especifico.items`) aparecem como tabela mas o texto da solução não os nomeia (o "Actions needed" da planilha nomeia o script exato).
6. **Sem health score agregado** do cliente (a planilha resume tudo em um %).
7. **Sem Page Experience** (HTTPS/SSL/mixed/redirect/safe browsing/popups) — 13 dos 49 itens do checklist.
8. **Export DOCX por análise única** — não existe o "documento do cliente" consolidado multi-URL/multi-estratégia.
9. **Sem esforço estimado** por problema (só severidade/prioridade).
10. **Sem benchmarks de concorrentes** e sem GSC/GA.

---

## Etapa 3 — Gap Analysis (cobertura da planilha)

Status: ✅ já existe · 🟨 parcial · ❌ não existe.
Prioridade: P0 (bloqueia paridade) > P1 > P2. Impacto: alto/médio/baixo sobre "substituir a planilha".

| # | Capacidade da planilha | Status | Complexidade | Prior. | Impacto | Observação |
|---|---|---|---|---|---|---|
| 1 | 36 audits PSI com Pass/Fail + descrição | ✅ | — | — | — | Ferramenta cobre mais audits que a planilha |
| 2 | Metric Impact por audit | ✅ | — | — | — | `metricas_afetadas` |
| 3 | Prioridade de correção | ✅ | — | — | — | Algoritmo superior ao da planilha |
| 4 | Guia de correção por problema | ✅ | — | — | — | KB por plataforma + pesquisador |
| 5 | Tabela de evidências (recursos/ms/KB) | 🟨 | baixa | P0 | alto | Dados existem (`items`); falta destacá-los no texto/relatório |
| 6 | Assessment CrUX LCP/INP/CLS (field data) | ❌ | **baixa** | **P0** | **alto** | `loadingExperience` já vem no payload — hoje descartado |
| 7 | Health Score % (antes/depois) | ❌ | baixa | P0 | alto | Agregação simples sobre dados existentes |
| 8 | Relatório consolidado multi-URL (documento do cliente) | 🟨 | média | P0 | alto | Export DOCX existe só por análise |
| 9 | Ciclo before/after com status de implementação por item | ❌ | média | P1 | alto | Nova entidade "Auditoria" + UI colaborativa |
| 10 | Consolidação cross-URL / dedup / escopo | ❌ | média | P1 | alto | LLM juiz (padrão já usado em Inlinks) |
| 11 | "Actions needed" nomeando recursos reais | 🟨 | média | P1 | alto | LLM: KB + `items` → recomendação específica |
| 12 | HTTPS / SSL / mixed content / redirect | ❌ | média | P1 | médio | Checagens HTTP próprias + audits best-practices |
| 13 | Safe Browsing | ❌ | baixa | P1 | médio | API Google (key) |
| 14 | Mobile-friendly | 🟨 | baixa | P1 | médio | `viewport` já coletado; agregar heurísticas |
| 15 | Práticas de segurança (headers) | ❌ | baixa | P2 | baixo | Request próprio; projeto já tem skill de segurança |
| 16 | Histórico GSC / evolução mensal CWV | ❌ | média | P2 | médio | CrUX History API cobre sem OAuth (25 semanas) |
| 17 | Participação mobile/desktop | ❌ | média | P2 | baixo | Aproximação CrUX `form_factors`; GA4 em V3 |
| 18 | Prioridade por template (matriz AUDITORIA) | 🟨 | baixa | P2 | médio | `template_tipo` já persistido; falta visão agregada |
| 19 | Benchmarks de concorrentes | ❌ | média | P2 | médio | PSI nas URLs dos concorrentes + comparação |
| 20 | Pop-ups/interstitiais intrusivos | ❌ | alta | P3 | baixo | Screenshot + LLM vision; validação humana |
| 21 | Estimativa de esforço de implementação | ❌ | baixa | P1 | médio | Heurística por kb_codigo + LLM |
| 22 | Prints/gráficos de evolução | 🟨 | baixa | P2 | médio | Chart existe; falta série temporal por métrica no relatório |
| 23 | GTmetrix | ❌ | média | — | baixo | **Recomendação: não integrar.** PSI+CrUX+checks próprios cobrem os itens exclusivos (CDN/HTTP2/Keep-Alive dá para checar via headers) |
| 24 | Diagnóstico executivo + plano de ação | 🟨 | média | P1 | alto | Accordion é técnico; falta narrativa executiva gerada |

**Cobertura estimada hoje: ~55% dos entregáveis da planilha** (forte no núcleo técnico dos audits, ausente no ciclo de vida da auditoria, field data, Page Experience e no documento executivo).

---

## Etapa 4 — Arquitetura: avaliação e proposta

### 4.1 Avaliação crítica

- **Manter LangGraph + arq + nós atuais.** A separação coleta → detecção → análise → documentação → pesquisa → priorização → persistência é limpa, testada e barata. **Não é necessária uma arquitetura nova** — é necessária uma *extensão em camadas*.
- Gargalos reais: (a) o parse joga fora dados que a paridade exige (field data, screenshots, audits de outras categorias); (b) o pipeline termina na análise por URL — falta a camada de *auditoria do cliente* (agregação, consolidação, narrativa); (c) o documentador não usa as evidências no texto.
- O padrão "determinístico primeiro, LLM nos residuais" deve ser preservado nas novas camadas (agregação de health score e matriz por template são determinísticas; dedup/causa raiz/narrativa são LLM).

### 4.2 Arquitetura proposta (extensão)

```
                       ┌──────────────── por URL×estratégia (existente) ───────────────┐
coletar_psi ──► detectar_plataformas ──► analisar_seo ──► documentar ──► pesquisar_outros ──► priorizar
   │ (novo: reter loadingExperience, screenshot, audits best-practices)                    │
   ▼                                                                                       ▼
coletar_page_experience (novo, por origem)                                          persistir (por URL)
   • HTTPS/SSL/mixed/redirect (checks HTTP próprios)                                       │
   • Safe Browsing API                                                                     ▼
   • headers de segurança                                        ┌────── por auditoria (novo) ──────┐
   • CrUX History (origem)                                       │ consolidar_cross_url (LLM juiz)  │
                                                                 │ estimar_esforco                  │
                                                                 │ health_score (determinístico)    │
                                                                 │ redigir_relatorio (LLM)          │
                                                                 │ persistir_auditoria              │
                                                                 └──────────────────────────────────┘
```

**Novo modelo de dados:**
- `CwvAuditoria` (campanha): cliente, URLs×template, fase (`before`/`aguardando_implementacao`/`after`/`concluida`), health_score_before/after, relatorio_json, execucao_before_id, execucao_after_id.
- `CwvChecklistItem`: auditoria_id, item (kb_codigo ou check de page experience), status_before, status_after, status_implementacao (cliente), nota_cliente, nota_seo, prioridade, esforco, escopo (URLs afetadas).
- `CwvProblemaConsolidado`: causa raiz, problemas_origem (N `CwvProblema`), evidências agregadas, recomendação redigida.

**Decisões recomendadas:**
1. **Não integrar GTmetrix** — duplicaria coleta com pouco ganho; os 3-4 checks exclusivos (CDN, HTTP/2, Keep-Alive, cache) são deriváveis de headers/network do próprio Lighthouse ou de um request próprio.
2. **CrUX History API no lugar de GSC** para a fase inicial do histórico (pública, sem OAuth, 25 semanas por origem/URL). GSC/GA4 ficam para V3 (exigem OAuth por cliente).
3. **Guardar um resumo do payload PSI** (loadingExperience, final-screenshot, audits com score, entities) em vez de `raw_psi_json={}` — ~50-200KB por análise, viabiliza reprocessamento e evidências visuais.

### 4.3 Qualidade de prompts / reutilização
- Reaproveitar o padrão do juiz de Inlinks (julgamento único estruturado, kill-switch, funil observável) no consolidador cross-URL.
- Prompts novos devem seguir o padrão pt-BR + saída estruturada + validação contra listas fechadas (mesmo padrão do analisador atual).
- Reutilizar `html_para_docx_bytes`/export existente para o relatório consolidado.

---

## Etapa 5 — Agentes: suficiência e proposta

**Dos 16 agentes sugeridos no briefing, a maioria já está coberta** pela dupla "coleta PSI + KB determinística": PSI Agent, Lighthouse Agent, Network Agent, Image Optimization Agent, JS/CSS Agent, Resource Loading Agent e Core Web Vitals Agent **não precisam ser agentes LLM** — são o coletor + o mapeamento audit→KB que já existem (agentes LLM aqui só adicionariam custo e variância). DevTools Agent (trace real) e Accessibility/Structured Data Agents são de outras ferramentas/escopo.

Conjunto final proposto (novos em negrito):

| Agente/Nó | Tipo | Responsabilidade |
|---|---|---|
| Coletor PSI | determinístico (existente, estendido) | PSI mobile+desktop; passa a reter field data, screenshot e categoria best-practices |
| Detector de Plataforma | determinístico (existente) | 5 camadas + override |
| Analisador | híbrido (existente) | audit→KB direto; LLM só nos residuais |
| Documentador | determinístico (existente, estendido) | KB por plataforma; passa a injetar evidências reais no texto |
| Pesquisador | ReAct LLM (existente) | audits fora da KB (web + Context7) |
| Priorizador | determinístico (existente, estendido) | severidade×métrica; passa a incorporar esforço e escopo |
| **Auditor de Page Experience** | determinístico | HTTPS, SSL, mixed content, redirects 301, headers de segurança, Safe Browsing, mobile-friendly |
| **Coletor de Campo (CrUX)** | determinístico | assessments LCP/INP/CLS (field), histórico 25 semanas, form factors |
| **Consolidador Cross-URL** | LLM juiz | dedup entre URLs/estratégias, agrupamento por causa raiz, definição de escopo ("Desktop e Mobile", "todas as páginas de produto") |
| **Estimador de Esforço** | híbrido | heurística por kb_codigo (ex.: `imagens-formato-moderno`=baixo, `js-bundle-grande`=alto) + ajuste LLM pelo contexto da plataforma |
| **Redator de Relatório** | LLM | diagnóstico executivo + diagnóstico técnico + plano de ação faseado, nomeando evidências; espelha a estrutura da planilha (reutilizar padrão do documentador do Parecer) |
| **Benchmark Agent** (V2) | determinístico | PSI nos concorrentes, tabela comparativa "benchmarks closest to the ideal time" |
| **Inspetor Visual** (V3) | LLM vision | pop-ups/interstitiais/ads intrusivos a partir do screenshot; sempre com revisão humana |

---

## Etapas 6-8 — Automação, recomendações e inteligência

**Contrato de cada problema consolidado (paridade + superação da planilha):**
descrição · evidências reais (recursos, ms, KB, seletores) · impacto técnico · impacto em SEO · CWV afetados · impacto para o usuário · solução detalhada por plataforma · exemplo de código quando aplicável · links oficiais (web.dev/MDN/docs da plataforma) · prioridade · estimativa de ganho (savings do Lighthouse) · esforço de implementação · escopo (URLs/estratégias afetadas) · status de implementação (cliente).

Tudo automático exceto: status de implementação (é do cliente, por definição) e vereditos visuais de pop-up/interstitial (IA propõe, humano confirma).

**Inteligência (Consolidador + Redator):**
- correlacionar (mesmo audit em N URLs → 1 item com escopo);
- eliminar duplicidades mobile/desktop quando idênticas (padrão "Observação: os problemas ocorrem de forma idêntica em Desktop e Mobile" — já usado no Parecer);
- causa raiz (ex.: "os 5 problemas de TBT derivam do bundle X de 900KB");
- priorizar globalmente (severidade × métrica × nº de URLs × esforço);
- gerar diagnóstico executivo (para o dono do negócio) e técnico (para o dev), + plano de ação em fases.

---

## Etapa 9 — Roadmap e plano de implementação

### MVP — "paridade de dados" (1-2 semanas de esforço focado)
| # | Tarefa | Dep. | Esforço | Risco |
|---|---|---|---|---|
| M1 | Reter `loadingExperience`, `final-screenshot` e resumo do payload no parse (novo campo `raw_resumo_json`) | — | S | baixo — cuidado com tamanho de linha no Postgres |
| M2 | Assessments de campo LCP/INP/CLS na `CwvAnalise` + tiles na UI | M1 | S | CrUX pode não ter dados p/ sites pequenos → fallback lab com aviso |
| M3 | Health Score agregado por execução (% pass) + card no dashboard | — | S | baixo |
| M4 | Export DOCX consolidado da execução (todas as URLs, sumário + capítulos) | M3 | M | volume de páginas; reusar `cwv_export` |
| M5 | Evidências (`items`) renderizadas com destaque no problema e no DOCX | M1 | S | baixo |

### V1 — "ciclo de auditoria + inteligência" (3-5 semanas)
| # | Tarefa | Dep. | Esforço | Risco |
|---|---|---|---|---|
| V1.1 | Entidade `CwvAuditoria` + checklist com status de implementação/notas (migração Alembic + CRUD + UI) | MVP | L | modelagem do ciclo before/after |
| V1.2 | Nó `coletar_page_experience` (HTTPS/SSL/mixed/redirect/headers/Safe Browsing/mobile-friendly) | — | M | falsos positivos SSL; sites atrás de WAF |
| V1.3 | Consolidador Cross-URL (LLM juiz estruturado + kill-switch, padrão Inlinks) | V1.1 | M | custo LLM — limitar a 1 chamada por auditoria com contexto compacto |
| V1.4 | Estimador de esforço (heurística por kb_codigo + campo `esforco`) | — | S | baixo |
| V1.5 | Redator de Relatório (executivo + técnico + plano faseado) + export | V1.3 | M | qualidade da narrativa — validar com golden set |
| V1.6 | Re-auditoria "AFTER" amarrada à campanha (reusa `/comparacao`) + health score after | V1.1 | M | baixo |

### V2 — "história e contexto" (3-4 semanas)
- CrUX History API: evolução 25 semanas por origem/URL (substitui prints do GSC) + gráfico por métrica.
- Benchmark Agent: PSI em até 3 concorrentes, tabela comparativa no relatório.
- Matriz por template (visão AUDITORIA): agregação por `template_tipo` com prioridade por tipo de página.
- Recomendação personalizada: documentador injeta recursos reais no texto ("reduza `app.bundle.js` (412KB, 1.2s)").
- Aproximação de device split via CrUX `form_factors`.

### V3 — "integração e monitoramento" (4-6 semanas)
- OAuth Google: GSC (Page Experience real) e GA4 (visitas reais mobile/desktop).
- Monitoramento agendado (cron re-audit mensal) + alertas de regressão (webhook/email).
- Inspetor Visual (pop-ups/interstitiais) com revisão humana.
- Export Google Sheets no layout NPBR (para clientes que exigem o formato planilha).

### Riscos transversais
1. **Quota PSI** — auditorias multi-URL × concorrentes × re-audits multiplicam chamadas; mitigar com cache por URL canônica (janela de 24h) e rotação de keys já existente.
2. **Custo LLM na consolidação** — 1 chamada estruturada por auditoria com contexto compactado (só títulos+métricas+savings), não o payload inteiro.
3. **CrUX sem dados** (sites de baixo tráfego) — degradar para lab data com aviso explícito na UI/relatório.
4. **Tamanho do relatório** — DOCX multi-URL pode ficar enorme; sumário executivo + apêndices por URL.
5. **OAuth (V3)** — consentimento por cliente, tokens, renovação; isolar em serviço próprio.

---

## Conclusão

A ferramenta já supera a planilha no núcleo técnico (coleta, KB por plataforma, priorização, histórico estruturado). O que falta para *substituí-la* não é refazer a arquitetura, e sim três camadas: **(1) dados que já chegam e são descartados** (field data, screenshots, best-practices), **(2) o ciclo de vida da auditoria** (before → implementação do cliente → after → health score), e **(3) a camada editorial** (consolidação cross-URL, esforço, narrativa executiva) — exatamente o trabalho manual de maior valor na planilha, e o mais adequado para os novos agentes LLM.
