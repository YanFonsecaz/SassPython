# Core Web Vitals

**Estado:** ✅ implementado · **Rota:** `/ferramentas/core-web-vitals` · **Slug:** `core_web_vitals`
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
| Cobrança | `15 + 1·N` (teto 100); mede mobile+desktop | Flat por URL |

## Não-objetivos

Crawl via sitemap · URLs autenticadas · re-análise agendada · integração CMS · alertas por e-mail ·
benchmark entre clientes · field data CrUX · UI admin para editar KB (PR no git basta) · export PDF ·
compartilhamento por link público.

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

### Histórico
- [SPEC_CWV_Bugs_Postmortem](SPEC_CWV_Bugs_Postmortem.md) · [POSTMORTEM_E2E_Sites_Reais_2026-05](POSTMORTEM_E2E_Sites_Reais_2026-05.md) — 🗄️ postmortems.
- [`_historico/PLANO_Correcoes_CWV.md`](_historico/PLANO_Correcoes_CWV.md) — 🗄️ plano de correções (aplicado).
