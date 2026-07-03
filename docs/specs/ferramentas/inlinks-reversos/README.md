# Distribuir Inlinks (inlinks reversos)

**Estado:** ✅ implementado · **Rota:** `/ferramentas/distribuir-inlinks` · **Slug:** `distribuir_inlinks`
**Créditos:** `15 + 1·N_candidatas` (teto 115) — `calcular_custo_distribuir_inlinks()`
**Código:** `backend/app/agents/workflow_inlinks_reversos.py` · `routers/ferramentas_inlinks_reversos.py` · `schemas/inlinks_reversos.py`

A **inversa** dos Inlinks Automáticos. Dado **1 URL alvo** + **N candidatas**, descobre, para cada
candidata, onde inserir um link **apontando para o alvo**. Caso de uso: acabei de publicar uma landing/
página comercial e quero plantar links internos para ela a partir de outros artigos do site.

| Inlinks Automáticos | Distribuir Inlinks |
|---|---|
| 1 pilar + N candidatas | 1 URL **alvo** + N candidatas |
| Modifica o pilar, linkando **para** as candidatas | Para cada candidata, linka **para** o alvo |
| Resultado: 1 markdown | Resultado: até N markdowns (1 por candidata viável) |

## Arquitetura (mapa → código)

Reaproveita quase tudo dos Inlinks Automáticos: invertendo a semântica, cada candidata é o "pilar
local" e o alvo é o único "candidato" — `inserir_inlinks(candidata_md, [alvo], ...)`. Toda a
inteligência (boost de keyword, validação, threshold, `min_distance_words`) é herdada. Nós em
`agents/workflow_inlinks_reversos.py`:

```
validar_urls → extrair_alvo → [alvo ok?] não → persistir_falha_alvo → END
                                      sim ↓
extrair_candidatas → enriquecer → filtrar_similaridade → inserir_em_cada → persistir → END
```

Reusos diretos de `agents/inlinks/*`: extrator, scraper/cleaner, enriquecedor, inseridor (Fix A/B/C),
revisor, formatador, cache de vetores (`conteudo_vetor`). **Não cria tabelas novas.**

## Decisões travadas

| Tema | Decisão |
|---|---|
| Reuso | Inseridor genérico dos inlinks automáticos ([[../inlinks-automaticos]]) — zero duplicação de lógica |
| **Julgamento (2026-07)** | Herda o **juiz único** do inseridor ([SPEC_Inlinks_Julgamento_Unico](../inlinks-automaticos/SPEC_Inlinks_Julgamento_Unico.md)); rollback via `inlinks_pisos_legado_distribuir=True`. Upstream (filtro cosine alvo↔candidata, slug_only, keyword override) inalterado |
| Alvo inviável | Curto-circuito `persistir_falha_alvo` (não processa candidatas) |
| Priorização | Slug/categoria/produto como sinais; filtro adaptativo slug-only quando aplicável |
| Cobrança | `15 + 1·N_candidatas` (teto 115); proteção do alvo; reserva pelo custo real |

## Não-objetivos

- Modificar o alvo · Aprovação humana · Publicar as candidatas modificadas automaticamente.

## Specs

### Implementadas
| Spec | Conteúdo |
|---|---|
| [SPEC_Distribuir_Viabilidade_Pelo_Juiz](SPEC_Distribuir_Viabilidade_Pelo_Juiz.md) | ✅ 2026-07: threshold de cosine no upstream vira piso de ruído 0.25; keyword override vira sinal; juiz decide (teto `distribuir_max_julgamentos=30`; rollback `inlinks_pisos_legado_distribuir=True`) |
| [SPEC_Inlinks_Descoberta_Automatica_Candidatas](../inlinks-automaticos/SPEC_Inlinks_Descoberta_Automatica_Candidatas.md) | ✅ 2026-07: índice do site por cliente + "Descobrir candidatas do site" também neste formulário |
| [SPEC_Ferramenta_Distribuir_Inlinks](SPEC_Ferramenta_Distribuir_Inlinks.md) | Spec-mãe: visão, reuso, modelo de dados, fluxo |
| [SPEC_Distribuir_Inlinks_Prioridade_Estrategica](SPEC_Distribuir_Inlinks_Prioridade_Estrategica.md) | Priorização estratégica das candidatas |
| [SPEC_Distribuir_Inlinks_Ancoras_Preferidas](SPEC_Distribuir_Inlinks_Ancoras_Preferidas.md) | Âncoras preferidas |
| [SPEC_Distribuir_Inlinks_Slug_Fallback_Categoria_Produto](SPEC_Distribuir_Inlinks_Slug_Fallback_Categoria_Produto.md) | Fallback por slug → categoria → produto |
| [SPEC_Distribuir_Inlinks_Filtro_Adaptativo_Slug_Only](SPEC_Distribuir_Inlinks_Filtro_Adaptativo_Slug_Only.md) | Filtro adaptativo slug-only |
| [SPEC_Distribuir_Inlinks_Visibilidade_Protecao_Alvo_Cobranca](SPEC_Distribuir_Inlinks_Visibilidade_Protecao_Alvo_Cobranca.md) | Visibilidade + proteção do alvo + cobrança |
| [SPEC_Distribuir_Inlinks_UI_Resultado](SPEC_Distribuir_Inlinks_UI_Resultado.md) | UI do resultado (N markdowns) |
