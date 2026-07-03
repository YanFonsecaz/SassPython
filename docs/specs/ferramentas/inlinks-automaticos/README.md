# Inlinks Automáticos (internal linking via RAG)

**Estado:** ✅ implementado · **Rota:** `/ferramentas/inlinks` · **Slug:** `inlinks`
**Créditos:** `15 + 1·N_urls` processadas (teto 60) — `calcular_custo_inlinks()`
**Código:** `backend/app/agents/workflow_inlinks.py` + `agents/inlinks/*` · `routers/ferramentas_inlinks.py` · `models/inlink_sugerido.py`, `conteudo_vetor.py`

Segunda ferramenta do SaaS. Dado um **conteúdo pilar** (URL ou markdown) e uma **lista de URLs
candidatas**, escolhe semanticamente quais candidatas viram inlinks no pilar e injeta âncoras naturais
no texto — **autônomo, sem aprovação humana**. Devolve o markdown do pilar com os links inseridos.

## Arquitetura (mapa → código)

Workflow LangGraph autônomo (worker ARQ + SSE), com curto-circuito quando o pilar não pode ser
extraído. Nós em `agents/workflow_inlinks.py`, subagentes em `agents/inlinks/`:

```
validar_urls → extrair_pilar → [pilar ok?] não → falha_pilar → END
                                        sim ↓
extrair_candidatos → enriquecer → match_rerank → inserir → revisar → formatar → persistir → END
```

| Nó | Subagente | Arquivo |
|---|---|---|
| extrair_pilar / candidatos | Extrator + scraper | `inlinks/extrator.py`, `core/scraper.py`, `core/cleaner` (`inlinks/cleaner.py`) |
| enriquecer | Metadados (título, keywords, headings) | `inlinks/enriquecedor_metadados.py` |
| match_rerank | Embeddings pgvector + re-ranking (cosine) | `inlinks/reranker.py`, `core/embeddings.py`, `models/conteudo_vetor.py` |
| inserir | Inseridor (boost de keyword, `min_distance_words`) | `inlinks/inseridor.py`, `inlinks/ancorador.py`, `inlinks/injector.py` |
| revisar | Revisor automático | `inlinks/revisor.py` |
| formatar / persistir | Saída + `inlink_sugerido` | `inlinks/formatador.py` |

## Decisões travadas

| Tema | Decisão |
|---|---|
| Autonomia | 100% IA, sem aprovação humana (≠ Gerar Artigo) |
| **Julgamento (2026-07)** | **Cosine NÃO decide** — LLM juiz único decide `aplicar/sugerir/descartar` com contexto completo; cosine é pré-ranking + sinal registrado. Portões duros só determinísticos (trecho literal, heading/lista, link duplicado, densidade c/ retry) |
| Qualidade da âncora | ~~Validação de palavra-chave + threshold relaxado~~ → substituída pelo juiz único ([SPEC_Inlinks_Julgamento_Unico](SPEC_Inlinks_Julgamento_Unico.md)) |
| Pilar inviável | **Curto-circuito** (`falha_pilar`) — não cobra/não segue |
| Cobrança | `15 + 1·N` (teto 60); reserva pelo custo real; falha refund |
| Reuso | O inseridor é genérico → reaproveitado pelos **inlinks reversos** ([[../inlinks-reversos]]) |

## Não-objetivos

- Aprovação humana · Aprendizado/feedback persistente entre execuções (removido) · Crawl automático de sitemap.

## Specs

### Julgamento único + verdade na UX (2026-07 — arquitetura vigente)
| Spec | Conteúdo |
|---|---|
| [SPEC_Inlinks_Julgamento_Unico](SPEC_Inlinks_Julgamento_Unico.md) | LLM juiz único decide; portões de cosine viram sinais; paridade âncoras/CTA/objetivo no Receber; revisor vira lint |
| [SPEC_Inlinks_UX_Verdade](SPEC_Inlinks_UX_Verdade.md) | Barra de progresso real (2 ferramentas); soft-fail âmbar com motivo; estado vazio alcançável |
| [SPEC_Inlinks_Funil_Transparente](SPEC_Inlinks_Funil_Transparente.md) | Contadores de funil em `resultado_json` + strip na UI; `etapa_atual` persistida |
| [SPEC_Inlinks_Eval_Golden_Set](SPEC_Inlinks_Eval_Golden_Set.md) | Harness offline com golden set rotulado — gate de merge de mudanças de prompt/portão |

### Base / arquitetura
| Spec | Conteúdo |
|---|---|
| [SPEC_Ferramenta_Inlinks_Automaticos](SPEC_Ferramenta_Inlinks_Automaticos.md) | Spec-mãe: contexto, fluxo, reuso de infra (~70%) |
| [SPEC_Inlinks_Arquitetura_IA](SPEC_Inlinks_Arquitetura_IA.md) | Arquitetura dos agentes de IA |

### Qualidade do match e da âncora
| Spec | Conteúdo |
|---|---|
| [SPEC_Inlinks_Qualidade_Match_e_Julgamento](SPEC_Inlinks_Qualidade_Match_e_Julgamento.md) | Match semântico + julgamento |
| [SPEC_Inlinks_Qualidade_Ancora_e_Densidade](SPEC_Inlinks_Qualidade_Ancora_e_Densidade.md) | Qualidade da âncora e densidade |
| [SPEC_Inlinks_Qualidade_e_Refresh](SPEC_Inlinks_Qualidade_e_Refresh.md) | Qualidade geral + refresh |
| [SPEC_Inlinks_Especificidade_Lexica](SPEC_Inlinks_Especificidade_Lexica.md) | Especificidade léxica da âncora |
| [SPEC_Inlinks_Sinonimos_via_Palavras_Chave](SPEC_Inlinks_Sinonimos_via_Palavras_Chave.md) | Sinônimos via palavras-chave |
| [SPEC_Inlinks_Reativacao_Vetores_e_Cosine_Permissivo](SPEC_Inlinks_Reativacao_Vetores_e_Cosine_Permissivo.md) | Reativação de vetores + cosine permissivo |
| [SPEC_Qualidade_Agentes_Inlinks](SPEC_Qualidade_Agentes_Inlinks.md) | Temperatura/modelo por agente (`0cbe741`) |

### Inseridor
| Spec | Conteúdo |
|---|---|
| [SPEC_Inlinks_Inseridor_Palavra_Chave_Destino_Ancorada](SPEC_Inlinks_Inseridor_Palavra_Chave_Destino_Ancorada.md) | Âncora na palavra-chave do destino |
| [SPEC_Inlinks_Selecao_Paragrafos_e_Visibilidade_Inseridor](SPEC_Inlinks_Selecao_Paragrafos_e_Visibilidade_Inseridor.md) | Seleção de parágrafos + visibilidade |
| [SPEC_Inseridor_Trecho_Contexto](SPEC_Inseridor_Trecho_Contexto.md) | Contexto do trecho ancorado |

### UX / saída
| Spec | Conteúdo |
|---|---|
| [SPEC_Inlinks_AntiAlucinacao_UI](SPEC_Inlinks_AntiAlucinacao_UI.md) | Anti-alucinação na UI |
| [SPEC_Inlinks_Headings_Comparador_Sidebar](SPEC_Inlinks_Headings_Comparador_Sidebar.md) | Headings + comparador + sidebar |
| [SPEC_Inlinks_UX_Enriquecedor_e_Tolerancia_Semantica](SPEC_Inlinks_UX_Enriquecedor_e_Tolerancia_Semantica.md) | Enriquecedor + tolerância semântica |
| [SPEC_Inlinks_Refinamentos_UX](SPEC_Inlinks_Refinamentos_UX.md) · [SPEC_Inlinks_Refinamentos_Finais](SPEC_Inlinks_Refinamentos_Finais.md) | Refinamentos de UX / finais |

### Robustez, cobrança e correções (aplicadas)
| Spec | Conteúdo | Commit |
|---|---|---|
| [SPEC_Billing_Inlinks](SPEC_Billing_Inlinks.md) | Reserva pelo custo real | `0cbe741` |
| [SPEC_Pilar_Falho_Curto_Circuito](SPEC_Pilar_Falho_Curto_Circuito.md) | Curto-circuito de pilar inviável | `0cbe741` |
| [SPEC_Inlinks_Robustez_e_Performance](SPEC_Inlinks_Robustez_e_Performance.md) | Robustez e performance | aplicado |
| [SPEC_Inlinks_Remover_Aprendizado](SPEC_Inlinks_Remover_Aprendizado.md) | Remoção do aprendizado persistente | aplicado |
| [SPEC_Inlinks_Bugs_Pos_Spec_Qualidade](SPEC_Inlinks_Bugs_Pos_Spec_Qualidade.md) · [SPEC_Inlinks_Correcoes_Titulo_e_Texto_Rejeitado](SPEC_Inlinks_Correcoes_Titulo_e_Texto_Rejeitado.md) | Bugs/correções pós-qualidade | aplicado |

### Histórico
- [`_historico/PLANO_Correcoes_Inlinks.md`](_historico/PLANO_Correcoes_Inlinks.md) — 🗄️ plano de correções (aplicado).
