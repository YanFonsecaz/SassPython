# Core Web Vitals

**Estado:** ✅ implementado (núcleo) · 📋 programa de paridade com a planilha NPBR em andamento (ver seção "Paridade NPBR") · **Rota:** `/ferramentas/core-web-vitals` · **Slug:** `core_web_vitals`
**Créditos:** `15 + 1·N_urls` (teto 100; cada URL mede **mobile + desktop**) — `calcular_custo_cwv()`
**Código:** `backend/app/agents/cwv/*` · `routers/ferramentas_cwv.py`, `admin_cwv.py` · `services/cwv_*` · `models/cwv_analise.py`, `cwv_problema.py`

Análise técnica de Core Web Vitals (LCP, CLS, INP, FCP, TTFB) que coleta métricas reais via
**PageSpeed Insights API**, diagnostica cada problema com um agente, e entrega um **plano de ação
documentado** usando uma **base de conhecimento curada** com soluções por plataforma (VTEX, WordPress,
Next.js, Shopify…). Dashboard histórico por URL com chart de evolução, accordion de problemas
priorizados e comparador entre análises. Exporta `.docx`.

## Arquitetura (mapa → código)

Workflow LangGraph linear (worker ARQ + SSE), nós em `agents/cwv/workflow.py`:

```
coletar_psi → detectar_plataformas → analisar_seo → documentar → pesquisar_outros → priorizar → persistir → END
```

| Nó | Função | Arquivo |
|---|---|---|
| coletar_psi | PSI API (2 keys, fallback 429, retry 5xx) | `services/cwv_psi_client.py` |
| detectar_plataformas | stackPacks → headers → network → meta | `services/cwv_plataforma.py` |
| analisar_seo / documentar | Casa audit ↔ KB; fallback LLM enriquecido | `agents/cwv/analisador.py`, `documentador.py`, `services/cwv_kb.py` |
| pesquisar_outros | Cauda longa (SerpAPI + fetch), paralelo | `agents/cwv/pesquisador.py` |
| priorizar / persistir | Severidade + grava `cwv_analise`/`cwv_problema` | `agents/cwv/priorizador.py`, `services/cwv_persistencia.py` |
| export `.docx` | Por problema e relatório completo | `services/cwv_export.py` |

Admin/manutenção da KB e reprocessamento: `routers/admin_cwv.py`. Modelos LLM dedicados por agente
(`observability/cwv_llm.py`).

## Decisões arquiteturais (mantidas)

| Tema | Decisão | Descartado |
|---|---|---|
| Coleta | PageSpeed Insights API + fallback de 2 keys | Lighthouse local (~500MB); GTMetrix pago |
| Documentação | Base curada YAML + fallback LLM | Web search ao vivo; RAG sobre docs |
| Detecção de plataforma | Multi-camada (stackPacks→headers→network→meta) | Wappalyzer-py |
| Orquestração | LangGraph `ainvoke` (não `astream v2`) | Celery/Temporal |
| Persistência | 2 tabelas (`cwv_analise`, `cwv_problema`) | Tudo em `resultado_json` |
| Chart | shadcn chart (recharts) | Tremor; chart.js |
| Cobrança | `15 + 1·N` (teto 100); mede mobile+desktop; novas capacidades do programa NPBR **não cobram extra** | Flat por URL; produto pago à parte |
| Field data | Colunas `crux_*` materializadas + `raw_resumo_json` compacto (≤64KB, sem screenshot) — o payload bruto continua FORA do DB/estado (compatível com `SPEC_Payload_PSI_Bruto`) | Guardar payload inteiro; screenshot no Postgres |
| Page Experience | Checks HTTP próprios por origem + payload PSI | GTmetrix (integração paga; checks exclusivos deriváveis de headers/Lighthouse) |
| Consolidação cross-URL | Dedup determinístico + 1 LLM juiz por auditoria (kill-switch) | LLM por problema |

## Não-objetivos

Crawl via sitemap · URLs autenticadas · integração CMS · benchmark entre clientes · UI admin para
editar KB (PR no git basta) · export PDF · compartilhamento por link público · **GTmetrix** (decisão
travada 2026-07) · **screenshot persistido no Postgres** (se V3 Inspetor Visual precisar, será object
storage) · **OAuth GSC/GA4** (roadmap V3).

## Specs

### Base
| Spec | Conteúdo |
|---|---|
| [SPEC_Ferramenta_Core_Web_Vitals](SPEC_Ferramenta_Core_Web_Vitals.md) | Spec-mãe: workflow + agentes + tabelas + rota + worker + cobrança + front |
| [SPEC_CWV_Base_Conhecimento](SPEC_CWV_Base_Conhecimento.md) | KB YAML (estrutura + loader + entradas + manutenção) |
| [SPEC_CWV_Dashboard_Historico](SPEC_CWV_Dashboard_Historico.md) | Dashboard por URL: chart + accordion + comparador + re-análise |

### Análise residual e qualidade
| Spec | Conteúdo |
|---|---|
| [SPEC_CWV_Analisador_Prompt_Enriquecido](SPEC_CWV_Analisador_Prompt_Enriquecido.md) · [SPEC_CWV_KB_Expansao_Gaps](SPEC_CWV_KB_Expansao_Gaps.md) | Fallback enriquecido + expansão da KB |
| [SPEC_CWV_Analisador_Tools_Pesquisa](SPEC_CWV_Analisador_Tools_Pesquisa.md) · [SPEC_CWV_Analisador_Context7](SPEC_CWV_Analisador_Context7.md) | Tools de pesquisa (SerpAPI/fetch) + context7 |
| [SPEC_CWV_Modelos_LLM_Dedicados](SPEC_CWV_Modelos_LLM_Dedicados.md) · [SPEC_CWV_LLM_Fallback_Analisador](SPEC_CWV_LLM_Fallback_Analisador.md) | Modelos dedicados + fallback do analisador |
| [SPEC_CWV_Paridade_Total_PSI](SPEC_CWV_Paridade_Total_PSI.md) · [SPEC_CWV_Deteccao_Plataforma_V2](SPEC_CWV_Deteccao_Plataforma_V2.md) | Paridade 1 audit = 1 problema + detecção robusta |

### UX, dados e export
| Spec | Conteúdo |
|---|---|
| [SPEC_CWV_Mobile_e_Desktop](SPEC_CWV_Mobile_e_Desktop.md) · [SPEC_CWV_Reanalisar_Comparador_Chart](SPEC_CWV_Reanalisar_Comparador_Chart.md) | Mobile+desktop + reanalisar/comparador |
| [SPEC_CWV_UX_Empty_State_Site_Perfeito](SPEC_CWV_UX_Empty_State_Site_Perfeito.md) · [SPEC_CWV_Cenarios_Erro](SPEC_CWV_Cenarios_Erro.md) | Estados (vazio/perfeito/raso) + cenários de erro |
| [SPEC_CWV_Fix_Tiles_Classificacao_e_Chart_Comparativo](SPEC_CWV_Fix_Tiles_Classificacao_e_Chart_Comparativo.md) · [SPEC_CWV_Export_Docx](SPEC_CWV_Export_Docx.md) | Tiles/classificação + export `.docx` |

### Robustez e cobrança (correções aplicadas)
| Spec | Conteúdo | Commit |
|---|---|---|
| [SPEC_Billing_CWV](SPEC_Billing_CWV.md) | Corrige vazamento de reserva (custo real) | `e50a3e6` |
| [SPEC_Payload_PSI_Bruto](SPEC_Payload_PSI_Bruto.md) | Payload bruto fora do DB/estado | `e50a3e6` |
| [SPEC_Performance_PSI_Pesquisador](SPEC_Performance_PSI_Pesquisador.md) | Pesquisador paralelo + PSI com pool/retry | `e50a3e6` |
| [SPEC_Robustez_Limpeza_CWV](SPEC_Robustez_Limpeza_CWV.md) | Checkpointer, cache de LLM, cancelamento, export async | `e50a3e6` |
| [SPEC_CWV_Testes_Automatizados](SPEC_CWV_Testes_Automatizados.md) · [SPEC_CWV_Hardening_Pre_Producao](SPEC_CWV_Hardening_Pre_Producao.md) · [SPEC_CWV_Correcoes_Pos_Validacao](SPEC_CWV_Correcoes_Pos_Validacao.md) | Testes + hardening + correções pós-validação | aplicado |

### Paridade NPBR (programa 2026-07 — ✅ Ondas 1–2 implementadas)

**Implementado (Ondas 1–2 — 2026-07):** S1, S2, S3, S4, S5, S6, S7. **Pendentes:** S8, S9, S10 (Ondas 3–4).

Objetivo: substituir a planilha `[OFFICIAL ENTERPRISE TEMPLATE - 2026] CWV and Loading Speed Audit`.
Análise-base: [AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07](AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md)
(inventário das 58 abas, gap analysis campo a campo, arquitetura proposta).

| # | Spec | Escopo | Migração |
|---|---|---|---|
| S1 | [SPEC_CWV_Field_Data_Retencao_Payload](SPEC_CWV_Field_Data_Retencao_Payload.md) | Field data CrUX + `raw_resumo_json` (assessments LCP/INP/CLS reais) | `0024` |
| S2 | [SPEC_CWV_Health_Score](SPEC_CWV_Health_Score.md) | Health score % da execução (regra da planilha) | — |
| S3 | [SPEC_CWV_Export_Consolidado_Execucao](SPEC_CWV_Export_Consolidado_Execucao.md) | DOCX consolidado multi-URL | — |
| S4 | [SPEC_CWV_Evidencias_Destacadas](SPEC_CWV_Evidencias_Destacadas.md) | Evidências com thresholds ("< 100 ms por tarefa") | — |
| S5 | [SPEC_CWV_Auditoria_Ciclo_De_Vida](SPEC_CWV_Auditoria_Ciclo_De_Vida.md) | Campanha before→implementação→after + checklist do cliente | `0026` |
| S6 | [SPEC_CWV_Page_Experience](SPEC_CWV_Page_Experience.md) | HTTPS/SSL/mixed/redirect/headers/Safe Browsing/mobile-friendly por origem | `0027` |
| S7 | [SPEC_CWV_Estimador_Esforco](SPEC_CWV_Estimador_Esforco.md) | Esforço baixo/médio/alto por problema | `0025` |
| S8 | [SPEC_CWV_Consolidador_Cross_URL](SPEC_CWV_Consolidador_Cross_URL.md) | Dedup + causa raiz + escopo (LLM juiz, kill-switch) | `0028` |
| S9 | [SPEC_CWV_Relatorio_Executivo](SPEC_CWV_Relatorio_Executivo.md) | Redator LLM + DOCX da auditoria (8 seções) | — |
| S10 | [SPEC_CWV_Reauditoria_After](SPEC_CWV_Reauditoria_After.md) | Fechar o ciclo: status after + health delta | — |

**Ordem de implementação (ondas — specs da mesma onda são independentes entre si):**
1. **Onda 1:** S1, S2, S4, S6, S7
2. **Onda 2:** S3 (usa S2) · S5 (usa S1+S2; integra S6 se pronta)
3. **Onda 3:** S8 (usa S5+S7) · S10 (usa S5)
4. **Onda 4:** S9 (usa S8; reusa S3/S4)

> Migrações: a série `0024–0028` está reservada acima, mas cada implementação DEVE conferir a última
> migração real em `backend/migrations/versions/` e encadear `down_revision` nela (ondas podem ser
> implementadas fora de ordem).

## Roadmap V2/V3 (sem spec ainda — não implementar sem spec)

- **V2:** CrUX History API (evolução 25 semanas por origem/URL — substitui prints do GSC, sem OAuth) ·
  Benchmark de concorrentes (PSI em até 3 URLs de referência + tabela comparativa) · matriz de
  prioridade por template (visão agregada da aba AUDITORIA da planilha) · recomendação personalizada
  (documentador nomeia recursos reais no texto da solução) · device split aproximado via CrUX
  `form_factors`.
- **V3:** OAuth Google (GSC Page Experience real + GA4 visitas) · monitoramento agendado (cron
  re-audit + alertas de regressão) · Inspetor Visual de pop-ups/interstitiais (screenshot + LLM
  vision, com revisão humana) · export Google Sheets no layout NPBR.

### Histórico
- [SPEC_CWV_Bugs_Postmortem](SPEC_CWV_Bugs_Postmortem.md) · [POSTMORTEM_E2E_Sites_Reais_2026-05](POSTMORTEM_E2E_Sites_Reais_2026-05.md) — 🗄️ postmortems.
- [`_historico/PLANO_Correcoes_CWV.md`](_historico/PLANO_Correcoes_CWV.md) — 🗄️ plano de correções (aplicado).
