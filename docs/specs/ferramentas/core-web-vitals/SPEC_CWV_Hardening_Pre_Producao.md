# SPEC #18 — Hardening Pré-Produção

**Status:** ✅ implementado
**Data:** 2026-05-28
**Esforço:** ~4 dias (paralelizável front + back)
**Depende de:** SPECs #11–#17 implementadas (já estão)

---

## 1. Resumo executivo

A ferramenta CWV está funcional em "beta operacional" mas tem 4 gaps que bloqueiam liberação para self-service público. Esta SPEC ataca os 4 em paralelo:

1. **Testes automatizados** — zero cobertura hoje; E2E manual de 2026-05-28 encontrou 4 bugs em ~1h
2. **Validação com sites reais** — só rodado contra web.dev e wikipedia.org (sites "lab clean"); nunca em VTEX/WordPress/customizado
3. **Observabilidade & alertas** — sem alarme de cota PSI, sem métrica de custo LLM
4. **Polimento UX** — duplicação no detalhe, títulos repetidos, "Recurso —" sem URL, cache busting em rebuild

Saída esperada: ferramenta cleared para self-service público com SLA básico.

---

## 2. Problema (diagnóstico do E2E 2026-05-28)

### 2.1 Bugs reincidentes não cobertos por teste

Em 1 análise de validação (`https://web.dev/`) foram encontrados e corrigidos:

| # | Bug | Arquivo | Tipo | Pegável por |
|---|---|---|---|---|
| 1 | `NameError: name 'outros' is not defined` | `workflow.py:183` | Variável renomeada esqueceu referência | unit test trivial |
| 2 | `ProblemaComparado.kb_codigo: str` quebrava com `None` | `schemas/cwv.py:157` | Schema desatualizado pós SPEC #17 | unit test do schema |
| 3 | Diff de problemas colapsava todos `kb_codigo=None` em um único item | `routers/ferramentas_cwv.py:312` | Lógica de set por chave fraca | unit test do comparador |
| 4 | `metricSavings`, `numericValue`, `warnings` perdidos antes de chegar no analisador | `services/cwv_psi_client.py:88` | Dict reduzido descartando campos | snapshot test do parser PSI |

**Padrão:** todos triviais. Nenhum tem cobertura. Próximo refactor cria mais.

### 2.2 Cobertura de cenários — só "lab clean"

Sites testados desde V1:
- ✅ `web.dev` (otimizado, Google) — testado várias vezes
- ✅ `wikipedia.org` (estático, leve) — testado hoje
- ❌ **VTEX (loja real)** — nunca exercitado
- ❌ **WordPress (com plugins)** — nunca exercitado
- ❌ **Customizado (Next/Vue/Angular pesado)** — nunca exercitado

Audits que dependem de site "sujo" para disparar e nunca foram vistos em UI real:
- `legacy-javascript` (sub-items aninhados estilo "Facebook → Array.from, Object.create")
- `cls-culprits-insight` (formato item próprio com layoutShifts)
- `forced-reflow-insight` em escala
- `lcp-breakdown-insight` com `nodeLabel` + `boundingRect`
- `third-parties-insight` com `mainThreadTime` por entity

### 2.3 Observabilidade insuficiente

- Sem métrica de quota PSI consumida → você descobre que estourou pelo log de erro
- Sem alerta quando key #2 cai (fica sem fallback silencioso)
- Sem custo LLM rastreado por análise (gpt-4.1 do pesquisador é ~5× mais caro que gpt-4o-mini)
- LangSmith configurado mas não validado em produção
- Endpoint `/api/admin/cwv/kb/reload` existe; falta `/health` simétrico

### 2.4 UX visível ao cliente final

- **Duplicação banner amber × "Como corrigir"** — `documentacao_md` ainda inclui "Valor medido: X" e "Elementos afetados: [urls]" que já estão renderizados acima
- **Títulos duplicados no plano** — "Bundle JavaScript excessivamente grande" #8 e #9, "Event handlers consumindo muito tempo" #5 e #6 (dois audits diferentes mapeiam pro mesmo KB). Defensível pelo design "1 audit = 1 problema" mas confuso
- **`mainthread-work-breakdown` mostra "—" na coluna Recurso** — esse audit não retorna URL, só `group_label`. Hoje fica feio
- **MIME error de cache** — quando rebuild muda hash do chunk, HTML cacheado pede `.css` velho que retorna 404+JSON; console mostra "Refused to apply style"

---

## 3. Solução

### Frente 1 — Testes automatizados (~2 dias) [BLOQUEADOR]

**Escopo:** cobertura mínima 70% do código CWV novo.

**Estrutura:**
```
backend/tests/
├── unit/cwv/
│   ├── test_analisador.py          # _extrair_contexto, _resumir_items, _formatar_audit_para_prompt
│   ├── test_cwv_psi_client.py      # parse de PSI JSON real (fixtures)
│   ├── test_cwv_kb.py              # AUDIT_ALIASES, buscar_por_audit_id
│   ├── test_documentador.py        # _severidade_por_savings, _metricas_por_audit, _gerar_doc
│   ├── test_pesquisador.py         # mock LLM, validar prompt e estrutura
│   ├── test_priorizador.py         # ordem por severidade × savings
│   └── test_schemas_cwv.py         # ProblemaComparado/Resposta com kb_codigo=None
├── integration/cwv/
│   ├── test_workflow_e2e.py        # workflow completo com PSI mockado
│   ├── test_persistencia.py        # roundtrip persistir→buscar
│   ├── test_comparador_endpoint.py # /comparacao/{id} com 2 análises (fix bug #3)
│   └── test_router_listagem.py     # endpoints CRUD
└── fixtures/cwv/
    ├── psi_web_dev.json            # snapshot real
    ├── psi_wikipedia.json          # snapshot real
    ├── psi_vtex_loja.json          # snapshot real (capturar nesta SPEC)
    └── psi_wordpress_plugins.json  # snapshot real
```

**Casos obrigatórios (regressão dos bugs de hoje):**

| Bug | Test |
|---|---|
| 1. `outros` undefined | `test_workflow_e2e::test_node_pesquisar_emite_progress_com_contagem_correta` |
| 2. `ProblemaComparado` quebra com `None` | `test_schemas_cwv::test_problema_comparado_aceita_kb_codigo_nulo` |
| 3. Diff colapsa Nones | `test_comparador_endpoint::test_diff_distingue_problemas_pesquisados_diferentes` |
| 4. `metricSavings` perdido | `test_cwv_psi_client::test_audits_falhos_preserva_metric_savings_e_numeric_value` |

**Casos de cobertura nova:**
- Cada `AUDIT_ALIASES` mapeia para KB existente
- `_resumir_items` preserva `wastedPercent`, `group_label`, `sub_items`, `cacheLifetimeMs`, `bounding_rect`
- Pesquisador retorna fallback skeleton quando LLM falha
- Severidade calculada de `savings_ms`/`savings_bytes`
- Priorização ordena críticos antes de não-críticos
- Cota: análise com 0 URLs ok libera créditos

**Critérios:**
- [ ] `pytest backend/tests --cov=backend/app/services/cwv_psi_client --cov=backend/app/services/cwv_persistencia --cov=backend/app/services/cwv_kb --cov=backend/app/agents/cwv --cov-fail-under=70`
- [ ] Os 4 bugs do E2E 2026-05-28 têm test que falha sem o fix correspondente
- [ ] CI roda em < 60s
- [ ] Pré-commit hook executa subset rápido (unit only)

### Frente 2 — Validação com sites reais (~0,5 dia)

**Escopo:** rodar análise contra 3 URLs reais e documentar achados.

**URLs sugeridas:**
1. **VTEX:** loja escolhida pelo usuário (idealmente cliente existente) — exercita plataforma VTEX detectada + KB VTEX-específica
2. **WordPress + plugins:** site WP com Elementor/WooCommerce — exercita scripts pesados de plugins, `legacy-javascript`
3. **Customizado:** site Next.js/Vue/React de cliente — exercita bundle moderno + bootup-time alto

**Validar:**
- [ ] Plataforma detectada correta (não cair em "desconhecida")
- [ ] Pelo menos 1 análise dispara `legacy-javascript` com sub-items aninhados visíveis na UI
- [ ] Pelo menos 1 análise dispara `cls-culprits-insight` com layoutShifts
- [ ] `metric_savings` aparece com valor não-zero em pelo menos 3 audits diferentes
- [ ] Pesquisador é chamado e produz doc útil para audit não-KB
- [ ] Score < 50 dispara o caminho "site ruim" sem regressão
- [ ] Tempo total da análise < 3min por URL (sem timeout)

**Entregável:**
`docs/specs/Ferramenta_CoreWebVitals/POSTMORTEM_E2E_Sites_Reais_2026-05.md` com:
- Screenshots de cada análise
- Lista de gaps encontrados (severidade alta/média/baixa)
- Recomendações para KB (audits que apareceram e não tinham entrada curada)
- Snapshots dos 3 PSI JSON salvos como fixtures para Frente 1

### Frente 3 — Observabilidade & alertas (~1 dia)

**Escopo:** instrumentar pontos críticos.

**3.1 Métricas Prometheus (já tem infra `metrics_allowlist`):**

```python
# backend/app/observability/cwv_metrics.py
cwv_psi_request_total = Counter("cwv_psi_request_total", ["key_index", "status"])
cwv_psi_quota_exhausted = Counter("cwv_psi_quota_exhausted_total", ["key_index"])
cwv_analise_duracao_seconds = Histogram("cwv_analise_duracao_seconds", buckets=[10, 30, 60, 120, 300, 600])
cwv_llm_tokens_total = Counter("cwv_llm_tokens_total", ["agente", "modelo", "tipo"])  # tipo=input/output
cwv_llm_custo_usd = Counter("cwv_llm_custo_usd_total", ["agente", "modelo"])
cwv_problemas_por_analise = Histogram("cwv_problemas_por_analise", buckets=[0, 5, 10, 15, 20, 30, 50])
cwv_pesquisador_invocacoes = Counter("cwv_pesquisador_invocacoes_total")
cwv_kb_miss_total = Counter("cwv_kb_miss_total", ["audit_id"])
```

**3.2 Endpoint `/api/admin/cwv/health`** (paralelo ao `/kb/reload`):

```json
{
  "status": "ok|degraded|down",
  "psi": {
    "key1_available": true,
    "key2_available": true,
    "quota_remaining_estimate": "unknown|N",
    "last_error": null
  },
  "llm": {
    "openai_configured": true,
    "ultima_chamada_ok": "2026-05-28T13:30:00Z"
  },
  "redis": {"ok": true},
  "kb": {"entries_loaded": 52, "aliases": 12},
  "ultimas_24h": {
    "analises_total": 47,
    "analises_falhas": 2,
    "taxa_sucesso": 0.957,
    "duracao_p50_s": 87,
    "duracao_p95_s": 178
  }
}
```

Gateado por `X-Admin-Token` (igual ao `kb/reload`).

**3.3 Alerta de cota PSI:**
- Quando key #2 também falhar em uma análise → log estruturado `event_type=cwv.psi.both_keys_failed`
- Adicionar handler no `cwv_psi_client` que dispara webhook Slack/Discord (configurável via `cwv_alerta_webhook_url` em settings)
- Não bloqueante se webhook não configurado — só loga

**3.4 LangSmith tracing:**
- Validar que análise atual aparece em projeto `seo-saas` no LangSmith
- Tag `ferramenta=cwv` em cada chain
- Documentar como acessar (link no `/health`)

**Critérios:**
- [ ] `GET /api/admin/cwv/health` retorna JSON estruturado
- [ ] Métricas Prometheus expostas em `/metrics` (já existe)
- [ ] Análise nova aparece no LangSmith tagged
- [ ] Documento `docs/operacao/CWV_RUNBOOK.md` com: o que olhar quando cliente reclama, como rotar key PSI, como bloquear análises se cota acabou

### Frente 4 — Polimento UX (~0,5 dia)

**4.1 Remover duplicação banner × "Como corrigir"** (`documentador.py`):
- Template `_gerar_doc` para de incluir `**Valor medido:**` e `**Elementos afetados:**`
- Mantém só `## Problema` (descrição PT-BR), `## Solução geral`, `## Solução por plataforma`
- KB YAML não muda — só o template de montagem

**4.2 Tratar títulos repetidos no plano:**
- Quando 2+ problemas têm o mesmo título, sufixar com audit_id em badge cinza pequeno: "Bundle JavaScript excessivamente grande `unused-javascript`" vs "`total-byte-weight`"
- Implementação: no `cwv-plano-acao.tsx`, detectar duplicatas e adicionar `<Badge variant="outline">{audit_id}</Badge>` apenas nos casos colidindo

**4.3 `mainthread-work-breakdown` sem URL:**
- No `cwv-problema-detalhes.tsx`, se `item.url` for vazio mas houver `group_label`, promover para coluna "Recurso"
- Coluna "Detalhe" some quando todos os items já mostram tudo no Recurso

**4.4 Cache busting na build:**
- Configurar `next.config.ts` para incluir hash determinístico nos chunks
- Ou: adicionar `Cache-Control: no-cache` para HTML, `max-age=31536000, immutable` para `_next/static/*` (já tem hash no path, então é seguro)
- Backend `app/main.py` pode setar esses headers no StaticFiles mount

**Critérios:**
- [ ] Análise nova: detalhe expandido sem repetição de "Valor medido"
- [ ] Plano: títulos duplicados visualmente distinguíveis
- [ ] `mainthread-work-breakdown` mostra "Script Evaluation" na coluna Recurso, não "—"
- [ ] Hard reload pós-rebuild: 0 errors no console (sem MIME error de chunk antigo)

---

## 4. Critérios globais de aceitação

A ferramenta sai de "beta operacional" para "produção" quando:

- [ ] **F1:** cobertura ≥ 70%, 4 bugs do E2E têm regression test, CI verde
- [ ] **F2:** 3 análises reais (VTEX + WordPress + customizado) documentadas em postmortem
- [ ] **F3:** `/api/admin/cwv/health` operacional, métricas em `/metrics`, RUNBOOK escrito
- [ ] **F4:** console 0 errors, sem títulos colidindo silenciosamente, sem duplicação no detalhe
- [ ] **Carga:** 5 URLs em uma execução completam em < 5min sem timeout (validar)
- [ ] **Rotação de chave PSI:** processo documentado e testado uma vez
- [ ] Alerta dispara quando ambas as keys PSI falham (teste forçado)

---

## 5. Não-objetivos

- Reescrever workflow ou agentes
- Adicionar features novas (re-análise agendada, crawl automático, etc.)
- Migrar de PSI API para Lighthouse local
- Suporte multi-idioma na KB
- Field data CrUX além de lab data
- UI admin para editar KB (PR no git continua sendo o canal)

---

## 6. Estrutura de execução

```
Frente 1 (Testes) ─┐
                   ├─→ exige PSI fixtures
Frente 2 (E2E real) ─→ gera fixtures
                                       
Frente 3 (Observabilidade) — paralelo, não bloqueia
Frente 4 (UX) — paralelo, não bloqueia
```

**Ordem recomendada:**
1. **Dia 1 manhã:** F2 (rodar 3 análises reais, salvar PSI JSONs como fixtures)
2. **Dia 1 tarde + Dia 2:** F1 (testes usando fixtures de F2)
3. **Dia 3:** F3 (observabilidade + RUNBOOK)
4. **Dia 4 manhã:** F4 (polimentos)
5. **Dia 4 tarde:** validação dos critérios globais + merge

Paralelizável entre 2 devs (back na F1+F3, front na F4, ambos na F2).

---

## 7. Riscos & mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| PSI cota esgotada durante F2 | média | Usar key dedicada pra dev; subir análise no horário de menor uso |
| Fixtures de PSI ficam stale (Google muda audits) | baixa | Refrescar fixtures a cada 6 meses; teste de schema valida estrutura |
| Pesquisador (gpt-4.1) custo explode em produção | média | F3 inclui métrica de custo; alerta quando custo/análise > $0.10 |
| Sites VTEX/WP do cliente ficam fora do ar durante F2 | baixa | Usar sites públicos de exemplo (lojaa.com.br conhecida, blog WP popular) |

---

## 8. Custo estimado

| Frente | Esforço | Custo PSI (cota) | Custo LLM |
|---|---|---|---|
| F1 Testes | 2 dias | 0 (mocks) | 0 (mocks) |
| F2 E2E real | 0,5 dia | ~6 chamadas | ~$0.50 (3 análises × ~$0.15) |
| F3 Observabilidade | 1 dia | ~3 chamadas (validação alertas) | ~$0.45 |
| F4 UX | 0,5 dia | 0 (visual) | 0 |

**Total:** ~4 dias eng, < $2 em LLM, < 10 chamadas PSI.

---

## 9. Pós-SPEC

Após merge desta SPEC:
- Atualizar README com checkbox "Critério de pronto para produção" completo
- Anunciar internamente que ferramenta está pronta pra self-service
- Definir SLA: análise individual < 3min, taxa de sucesso > 95%
- Setup do monitoramento: dashboard básico + alerta Slack ativo
