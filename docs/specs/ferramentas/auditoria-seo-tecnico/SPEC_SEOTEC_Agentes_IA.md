# SPEC — Agentes IA: diagnóstico e recomendação por item

**Status:** 🚧 parcial
**Capacidade:** `auditoria-seo-tecnico`
**Escopo:** backend — `backend/app/agents/seotec/analisador.py`, `recomendador.py`, `backend/app/data/seotec_solucoes/*.yaml`, `backend/app/services/seotec_kb.py`
**Créditos:** incluído no custo da auditoria (sem cobrança extra por item)
**Depende de:** [SPEC_SEOTEC_Checklist_Motor_Regras](SPEC_SEOTEC_Checklist_Motor_Regras.md)

---

## 1. Contexto (por quê)

Na planilha, o consultor escreve à mão o "Diagnóstico SEO" e a "Recomendação" de cada aba de
evidência. Aqui, agentes LangGraph geram esses textos a partir do resultado do motor de regras —
seguindo o desenho comprovado do CWV: **KB curada primeiro, LLM como fallback/contextualizador**,
custo controlado por lote.

## 2. Requisitos / Critérios de aceite

- [x] Todo item `Reprovado`/`Atenção` recebe `diagnostico` (o que está errado NESTE site, com
      números reais: "X de Y páginas sem title…") e `recomendacao` (como corrigir, acionável).
- [x] Itens `Aprovado` recebem texto curto padrão da KB (sem LLM).
- [ ] KB por item (`seotec_solucoes/*.yaml`): recomendação canônica (base = textos das abas da
      planilha) + variações por plataforma quando fizer sentido (WordPress/Yoast, VTEX, Shopify,
      Next.js — reusa detecção de plataforma do CWV quando disponível).
      _Cobertura parcial: 4 categorias seedadas (headings, title, meta-description, imagens-seo);
      miss cai no fallback LLM do recomendador (fail-open, padrão CWV)._
- [x] LLM entra para: contextualizar diagnóstico com as evidências (lote), cobrir item sem entrada
      na KB (fallback, padrão `SPEC_CWV_LLM_Fallback_Analisador`), e avaliar itens `sf` subjetivos
      marcados `avaliacao_ia: true` (ex.: "palavras-chave na URL" com amostra de URLs).
- [x] `recomendada_ia: true` na evidência (ex.: Title Recomendado) gera sugestões para **no máximo
      N=20 URLs de amostra** por item — nunca o site inteiro.
- [x] Chamadas em lote (vários itens por prompt), com `llm_guard` (retry/semáforo/backoff) e modelos
      dedicados (padrão `SPEC_CWV_Modelos_LLM_Dedicados`).
- [x] LLM indisponível → item fica sem diagnóstico/recomendação (pendente) com retry posterior;
      auditoria não falha (fail-open em todos os nós de IA).

## 3. Design (mapeado ao código)

```
analisar_ia (analisador.py)
  entrada: [ResultadoItem reprovados/atenção] + contexto do site (domínio, plataforma, contadores)
  lotes de ~8 itens/prompt → diagnóstico por item (JSON estruturado, contrato tipado)
recomendar_ia (recomendador.py)
  para cada item: seotec_kb.buscar(slug, plataforma) → hit: renderiza recomendação canônica
                                                     → miss: fallback LLM enriquecido
  itens com recomendada_ia: gera sugestões p/ amostra (ex.: titles novos p/ 20 URLs piores)
```

- Saídas validadas por schema Pydantic (mesmo padrão dos contratos JSONB do CWV).
- Prompts citam descrição/importância do item (do YAML do checklist) para manter o tom didático da
  planilha.
- Observabilidade: LangSmith + métricas existentes (`docs/observability.md`).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Ordem KB→LLM | KB primeiro; LLM contextualiza/fallback | LLM para tudo (custo/variância); só KB (genérico demais) |
| Lote | ~8 itens por chamada | 1 chamada por item (125 calls) |
| Sugestões por URL | Amostra ≤20 URLs nos itens marcados | Massa completa (explode custo; vira outra ferramenta) |
| Seed da KB | Textos de Recomendação/Diagnóstico extraídos das abas da planilha | Escrever do zero |

## 5. Verificação

```bash
rtk pytest backend/tests/unit/test_seotec_analisador.py   # LLM mockado; contrato de saída
rtk pytest backend/tests/unit/test_seotec_kb.py           # schema + cobertura de slugs
```

## 6. Não-objetivos

Geração em massa de titles/metas (ferramenta própria futura) · avaliação visual de páginas
(screenshots) · pesquisa web ao vivo por item (KB resolve; revisão via PR).

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-17 | Spec inicial | — |
| 2026-07-24 | Implementação parcial (núcleo end-to-end): analisador + recomendador + nós de workflow + persistência; KB com 4 categorias seed | — |
