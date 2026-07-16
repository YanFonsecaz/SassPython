# SPEC — Auditoria: endpoint comparativo URL×estratégia + prioridade editável

**Status:** 📋 planejado
**Capacidade:** `core-web-vitals`
**Escopo:** `backend` — router da auditoria, schema do PATCH de item
**Código:** `backend/app/routers/ferramentas_cwv_auditoria.py`, `backend/app/schemas/cwv_auditoria.py`, `backend/app/services/cwv_auditoria_service.py`
**Créditos:** não cobra (só leitura/edição de dados já pagos)
**Depende de:** [[SPEC_CWV_Auditoria_Ciclo_De_Vida]] (S5) · [[SPEC_CWV_Reauditoria_After]] (S10)
**Commit/Data:** — · 2026-07-15
**Consumidor:** [[SPEC_CWV_Auditoria_UI_V2]]

---

## 1. Contexto (por quê)

A UI V2 da auditoria (spec irmã) precisa de duas coisas que a API não dá:

1. **Visão before/after por URL.** Hoje só existe `GET /comparacao/{analise_id}` (compara uma
   análise com a anterior da mesma URL). Para a aba Before/After da auditoria, o front teria que
   buscar as análises das duas execuções e fazer N+1 chamadas de comparação. Com 8 URLs × 2
   estratégias seriam ~33 requests.
2. **Prioridade editável.** Decisão do brainstorming (2026-07-15): usuário edita status de
   implementação, notas **e prioridade** dos itens do checklist. `ChecklistItemPatch`
   (`schemas/cwv_auditoria.py:73-76`) só aceita `status_implementacao`, `nota_cliente`, `nota_seo`.

## 2. Requisitos / Critérios de aceite

- [ ] Dado `GET /api/ferramentas/core-web-vitals/auditorias/{id}/comparativo` numa auditoria com
      `execucao_before_id` e `execucao_after_id`, então a resposta traz 1 par por URL
      canônica×estratégia com métricas before/after e contadores
      `{resolvidos, persistentes, novos}`.
- [ ] Dado auditoria em fase `before` (sem execução after), então cada par tem `after: null` e
      `problemas: null` (baseline apenas) — HTTP 200, não erro.
- [ ] Dada URL presente no before cuja análise after falhou (status != sucesso), então o par vem
      com `after: null` (não explode, não omite a URL).
- [ ] Dado `PATCH /auditorias/{id}/itens/{item_id}` com `{"prioridade": 3}`, então o item é
      atualizado; `prioridade < 0` → 422.
- [ ] Dado auditoria/item de outro usuário, então 404 (padrão `_validar_cliente`/ownership).

## 3. Design (mapeado ao código)

### 3.1 `GET /auditorias/{auditoria_id}/comparativo`

Novo endpoint em `ferramentas_cwv_auditoria.py` (junto dos demais de auditoria):

```json
{
  "fase": "after",
  "pares": [
    {
      "url_canonica": "https://www.kumon.com.br/",
      "estrategia": "mobile",
      "template_tipo": "home",
      "before": {"analise_id": "…", "score_performance": 23, "lcp_ms": 4200.0,
                 "cls": 0.57, "inp_ms": 348.0, "tbt_ms": 890.0, "n_problemas": 22},
      "after":  {"analise_id": "…", "score_performance": 61, "…": "…"},
      "problemas": {"resolvidos": 12, "persistentes": 8, "novos": 2,
                    "titulos_resolvidos": ["…"], "titulos_novos": ["…"]}
    }
  ]
}
```

Implementação (função de serviço `montar_comparativo` em `cwv_auditoria_service.py`, router fino):

1. Carrega análises das duas execuções (`cwv_persistencia.buscar_analises_da_execucao`, já usado
   pelo export em `ferramentas_cwv.py:656`).
2. Indexa por `(url_canonica, estrategia)`; par sem after → `after: null`.
3. Diff de problemas por `chave_problema` (`cwv_auditoria_service.py:37-49` — **contrato, não
   reimplementar**): resolvidos = chaves só no before; novos = só no after; persistentes = nas duas.
4. Campos de métricas direto das colunas de `CwvAnalise` (`models/cwv_analise.py:28-34`:
   `score_performance`, `lcp_ms`, `cls`, `inp_ms`, `tbt_ms`).
5. Só análises `status == "sucesso"` entram; ordena por `template_tipo` e URL.

Schemas Pydantic novos em `schemas/cwv_auditoria.py`: `ComparativoMetricas`, `ComparativoPar`,
`ComparativoResposta` (listas de títulos limitadas aos 20 primeiros por categoria — resposta enxuta).

### 3.2 `prioridade` no PATCH de item

`ChecklistItemPatch` (`schemas/cwv_auditoria.py:73-76`) ganha
`prioridade: int | None = Field(default=None, ge=0)`. Handler do PATCH
(`ferramentas_cwv_auditoria.py:215+`) aplica se não-nulo, mesmo padrão dos campos atuais.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Onde comparar | Endpoint agregado no backend | Compor no front com `/comparacao/{analise_id}` — N+1 (~33 requests com 8 URLs) e a lógica de diff duplicada em TS |
| Regra de diff | Reusar `chave_problema` (mesma do checklist S5 e do comparador) | Diff por `audit_id` puro — divergiria do checklist (kb_codigo agrupa audits irmãos) |
| Payload | Métricas das colunas + contadores + títulos (cap 20) | Devolver problemas completos — resposta enorme; a UI só lista títulos nos chips |
| Prioridade editável | `ge=0` simples, sem reordenação automática dos demais | Reordenar cascata (drag-and-drop server-side) — YAGNI; usuário digita o número como na planilha |

## 5. Verificação

```bash
cd backend && uv run pytest tests/unit/test_cwv_auditoria_api.py -q
```

- Comparativo com before+after (2 URLs × 2 estratégias) → 4 pares, contadores corretos num
  cenário montado com chaves conhecidas (resolvido/persistente/novo).
- Fase before → `after: null`, `problemas: null`.
- Análise after com `status="falhou"` → par com `after: null`.
- PATCH prioridade: 200 com valor aplicado; -1 → 422; item de outro usuário → 404.
- Ownership do comparativo: auditoria de outro usuário → 404.

## 6. Não-objetivos

- Override manual de Pass/Fail (decisão do brainstorming: before/after é sempre da análise).
- Comparativo entre auditorias diferentes (só before/after da mesma auditoria).
- Reordenação automática/drag-and-drop de prioridades.
- Mudanças no `GET /comparacao/{analise_id}` existente (continua para a página de análise).

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-15 | Spec criada (brainstorming UI V2 da auditoria) | — |
