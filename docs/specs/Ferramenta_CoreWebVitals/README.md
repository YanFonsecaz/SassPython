# Ferramenta Core Web Vitals — Índice das SPECs

Análise técnica de Core Web Vitals (LCP, CLS, INP, FCP, TTFB) com:
- Coleta automatizada via **PageSpeed Insights API**
- Diagnóstico por agente LangChain + plano de ação documentado
- **Base de conhecimento curada** com soluções adaptadas por plataforma (VTEX, WordPress, Next.js, Shopify)
- Dashboard histórico por URL com chart de evolução + accordion de problemas priorizados + comparador entre análises

---

## 📦 SPECs originais (V1 — implementadas)

Implementação base concluída e validada via e2e em **2026-05-26**. Funcionalmente operacional, com 9 bugs corrigidos durante o teste.

| Ordem | SPEC | Escopo | Status |
|---|---|---|---|
| 1 | [SPEC principal — Ferramenta Core Web Vitals](SPEC_Ferramenta_Core_Web_Vitals.md) | Backend (workflow LangGraph + 3 agentes + 2 tabelas + rota + worker + cobrança) + frontend (formulário + polling) | ✅ implementada |
| 2 | [SPEC Base de Conhecimento](SPEC_CWV_Base_Conhecimento.md) | Estrutura YAML + loader + 34 entradas iniciais + processo de manutenção | ✅ implementada |
| 3 | [SPEC Dashboard Histórico](SPEC_CWV_Dashboard_Historico.md) | UI por URL: chart + accordion + comparador + re-análise | ⚠️ parcial (comparador a fazer — vide SPEC 5) |

---

## 🔧 SPECs pós-e2e (V1.1 — backlog de correções e cobertura)

Geradas após o e2e identificar bugs reais + gaps de cobertura.

| # | SPEC | Tipo | Esforço |
|---|---|---|---|
| 4 | [Bugs Postmortem](SPEC_CWV_Bugs_Postmortem.md) | 📝 Documentação dos 9 bugs encontrados + lições aprendidas | 0 (já feito) |
| 5 | [Testes Automatizados](SPEC_CWV_Testes_Automatizados.md) | 🧪 Pytest unit + integration cobrindo backend novo | ~2 dias |
| 6 | [Re-analisar + Comparador + Chart](SPEC_CWV_Reanalisar_Comparador_Chart.md) | ✨ Validar reanalise + implementar comparador entre análises (backend novo + frontend) | ~2 dias |
| 7 | [Detecção de Plataforma V2](SPEC_CWV_Deteccao_Plataforma_V2.md) | 🔍 Detector mais robusto + override manual (backend + frontend) | ~1.5 dias |
| 8 | [LLM Fallback do Analisador](SPEC_CWV_LLM_Fallback_Analisador.md) | 🤖 Validar/robustecer LLM path + observabilidade (backend + frontend badge) | ~1.5 dias |
| 9 | [UX Empty State + Site Perfeito + Análise Rasa](SPEC_CWV_UX_Empty_State_Site_Perfeito.md) | 🎨 Diferenciar 4 estados de análise (backend metadata + frontend banner) | ~1 dia |
| 10 | [Cenários de Erro](SPEC_CWV_Cenarios_Erro.md) | 🚨 Validar branches de erro + motivo_falha estruturado (backend + frontend) | ~1.5 dias |

**Esforço total V1.1:** ~10 dias de engenharia (paralelizável entre back e front).

---

## 🚀 Novas funcionalidades (V2)

| # | SPEC | Tipo | Esforço |
|---|---|---|---|
| 11 | [Análise Mobile **e** Desktop](SPEC_CWV_Mobile_e_Desktop.md) | ✨ Toda análise roda Mobile+Desktop (2 análises/URL) + toggle no dashboard. **Sem migration** (schema já suporta). Custo passa a `15 + N×2`. | ~1–1,5 dia |
| 12 | [Exportar documentação em `.docx`](SPEC_CWV_Export_Docx.md) | 📄 Baixar `.docx` **por problema** e **relatório completo** da URL — reaproveita o motor de `.docx` do Parecer. Sem migration, sem créditos. | ~0,5–1 dia |

---

## 🗺️ Ordem de execução recomendada V1.1

```
                          ┌────────────────────────────┐
                          │ 4. Bugs Postmortem         │
                          │ (já feito — referência)    │
                          └─────────────┬──────────────┘
                                        │
                                        ▼
                          ┌────────────────────────────┐
                          │ 5. Testes Automatizados    │ ← prioridade máxima
                          │ Bloqueia: 6, 7, 8, 9, 10   │
                          └─────────────┬──────────────┘
                                        │
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
       ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
       │ 6. Reanalisar+   │   │ 9. UX Empty/     │   │ 10. Cenários     │
       │    Comparador    │   │    Perfeito      │   │     Erro         │
       └──────────────────┘   └──────────────────┘   └──────────────────┘
                                        │
                                        ▼
                          ┌────────────────────────────┐
                          │ 7. Detecção Plataforma V2  │
                          │ 8. LLM Fallback            │
                          │ (independentes, paralelos) │
                          └────────────────────────────┘
```

**Caminho crítico:** 5 (testes) → 6 (comparador) → release V1.1.

---

## 🎯 Critério de pronto para "produção"

A ferramenta sai de "beta interno" para "produção" quando:

- [x] SPECs 1, 2, 3 implementadas
- [x] E2E manual com 1 URL real (web.dev) passou
- [ ] SPEC 5 (testes) com cobertura ≥70% — **bloqueador**
- [ ] SPEC 6 (comparador) implementada — diferencial vs PSI direto
- [ ] SPEC 10 (cenários erro) implementada — UX previsível em falhas
- [ ] SPEC 9 (empty states) implementada — credibilidade com analise rasa
- [ ] E2E com pelo menos 1 URL VTEX real, 1 WordPress, 1 site customizado
- [ ] Performance: 5+ URLs em uma execução completam em <5min (validar semáforos)
- [ ] Cota PSI: documentar processo de rotação de keys + monitoring

SPECs 7 (plataforma V2) e 8 (LLM fallback) são **importantes mas não bloqueadoras** — podem ir para V1.2.

---

## 🧠 V1.2 — Qualidade da análise residual + tools no agente

Foco: melhorar precisão e profundidade da documentação quando o audit não casa com a KB.

| # | SPEC | Tipo | Esforço | Depende de |
|---|---|---|---|---|
| 11 | [Prompt enriquecido do fallback](SPEC_CWV_Analisador_Prompt_Enriquecido.md) | 🤖 Backend (analisador) | ~3 h | — |
| 12 | [Expansão de cobertura da KB](SPEC_CWV_KB_Expansao_Gaps.md) | 📚 Conteúdo + script auditoria | ~1 dia | beneficia-se de 11 |
| 13 | [Tools de pesquisa (SerpAPI + fetch)](SPEC_CWV_Analisador_Tools_Pesquisa.md) | 🤖 Backend (BaseAgent + Pesquisador) | ~2 dias | 11 e 12 |
| 14 | [Tool context7 (docs de framework)](SPEC_CWV_Analisador_Context7.md) | 🤖 Backend (tool adicional) | ~0,5 dia | 13 |
| 15 | [Modelos LLM dedicados CWV](SPEC_CWV_Modelos_LLM_Dedicados.md) | 🤖 Backend (config + agentes) | ~1 h (analisador) + 30 min (pesquisador, junto com 13) | independente; aplicar parte do analisador a qualquer momento |
| 16 | [Correções pós-validação (#11-#15)](SPEC_CWV_Correcoes_Pos_Validacao.md) | 🐛 Backend (migration + persistência + script + endpoint admin) | ~3 h | fecha gaps deixados por 12 e 13 |
| 17 | [Paridade total com PSI (1 audit = 1 problema)](SPEC_CWV_Paridade_Total_PSI.md) | 🧱 Backend (analisador/documentador/persistência) + frontend | ~1,5 dia | resolve perda observada no E2E de 2026-05-27 (UI mostrava 7, PSI mostrava 17) |

---

## 🛡️ V1.3 — Hardening pré-produção

Pós SPEC #17 a ferramenta está funcional mas em "beta operacional". Esta fase libera para self-service público.

| # | SPEC | Tipo | Esforço | Depende de |
|---|---|---|---|---|
| 18 | [Hardening pré-produção (testes + E2E real + observabilidade + UX)](SPEC_CWV_Hardening_Pre_Producao.md) | 🛡️ 4 frentes paralelas | ~4 dias | #11–#17 implementadas |

**Diagnóstico:** E2E de 2026-05-28 encontrou 4 bugs reais em ~1h de validação manual (analisador `outros` undefined, schema ProblemaComparado quebrava com null, diff colapsava Nones, metricSavings perdido no parser PSI). Todos triviais de pegar com teste, nenhum tem cobertura. Soma-se: nunca testado com URL real de cliente (só `web.dev`/`wikipedia.org`), sem alerta de cota PSI, sem métrica de custo LLM, redundância visível no detalhe de cada problema.

### Ordem recomendada V1.2

```
15 (modelos dedicados — parte analisador)  ← aplicar primeiro, ganho de determinismo
                  │
                  ▼
11 (prompt enriquecido) ─┐
                         ├── permite 12 melhor calibrado
12 (KB +15 entradas) ────┘
                         │
                         ▼
                  13 (tools básicas) + 15 parte pesquisador (junto)
                         │
                         ▼
                  14 (context7)
```

**Por que essa ordem:** começar pelo barato e seguro (SPEC #15 só muda config — temperature 0.1 dá determinismo de imediato, sem risco de regressão); depois mudança de prompt (#11); depois conteúdo (#12); depois tools (#13 + parte pesquisador do #15 com `gpt-4.1`); context7 (#14) por último porque tem custo de cota e só agrega valor quando o resto já está calibrado.

**Diagnóstico que justifica essa V1.2:** o E2E de 2026-05-27 mostrou audit #7 "Problema não catalogado" (`speed-index` caindo em `outros`). Análise no DB local: 2 problemas com `kb_codigo=outros` em ~30 análises — número baixo no laboratório, mas em produção com URLs reais a cauda longa de audits vai crescer. As 4 specs atacam essa cauda longa.

---

## 🧱 Decisões arquiteturais já tomadas (mantidas)

| Tema | Decisão | Alternativas descartadas |
|---|---|---|
| Coleta CWV | PageSpeed Insights API + fallback de 2 keys (key1 → key2 em 429) | Lighthouse local (~500MB Docker); GTMetrix pago |
| Documentação | Base curada YAML (34 entradas + expansão por SPEC 7) | Web search ao vivo; RAG sobre docs |
| Detecção plataforma | Multi-camada: stackPacks → headers → network URLs → meta generator → fallback (SPEC 7) | Wappalyzer-py |
| Orquestração | LangGraph com `ainvoke` (não `astream(version="v2")` — vide Bug #6) | Celery/Temporal/custom |
| Persistência | 2 tabelas (`cwv_analise`, `cwv_problema`) + 6 colunas adicionadas em SPECs 8, 9 (llm_*, audits_totais, etc) | Tudo em `resultado_json` |
| Chart | shadcn chart (recharts) | Tremor; chart.js |
| Cobrança | Base 15 créditos + 1 por URL, cap em 50 | Crédito fixo por URL flat (5) |

---

## ⚠️ Não-objetivos (transversais)

- Crawl automático via sitemap
- URLs autenticadas
- Re-análise agendada/recorrente
- Integração CMS para aplicar correções automaticamente
- Alertas por email/notificação push
- Comparativo entre clientes (benchmark setorial)
- Field data CrUX além de lab data
- Tradução multi-idioma da KB
- UI admin para editar KB (PR no git é suficiente)
- Exportação de dashboard em PDF
- Anotações do usuário no dashboard
- Compartilhamento de dashboard por link público

---

## 📚 Como ler

- **Arquiteto/tech lead avaliando viabilidade:** SPEC 1 §1-3 + README atual
- **Backend dev implementando V1:** SPECs 1 §3 + 2 completa
- **Backend dev corrigindo V1.1:** SPECs 4, 5, 6, 7, 8, 10 (na ordem)
- **Frontend dev implementando V1:** SPECs 1 §4 + 3 completa
- **Frontend dev implementando V1.1:** SPECs 6, 9, 10 (banners + componentes novos)
- **Redator de conteúdo da KB:** SPEC 2 + 7 §3.3 (novas plataformas) + 8 §5 (entrada `outros`)
- **Code review V1.1:** seção "Critério de pronto" da SPEC correspondente
- **PR a partir de bug em produção:** [Bugs Postmortem](SPEC_CWV_Bugs_Postmortem.md) §3 — checar se já documentado
