# SPEC — Health Score da execução (paridade com o % da planilha)

**Status:** ✅ implementado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (serviço puro + workflow + endpoint) e frontend (cards)
**Código:** `backend/app/services/cwv_health.py` (novo), `backend/app/agents/cwv/workflow.py::_run_workflow_cwv`, `backend/app/routers/ferramentas_cwv.py`, `backend/app/schemas/cwv.py`, `frontend/src/components/cwv/cwv-dashboard-client.tsx`, `frontend/src/components/cwv/cwv-execucao-client.tsx`  ·  **Rota:** `core-web-vitals`
**Créditos:** não cobra
**Depende de:** —
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gap #7)

---

## 1. Contexto (por quê)

A planilha NPBR resume toda a auditoria em um número: **Health Score %** = itens Pass ÷ itens totais (`Checklist!B2 = H2/G2*100`). É o indicador que o cliente acompanha antes/depois. A ferramenta tem `score_performance` por URL (Lighthouse), mas nenhum agregado da execução. Esta spec porta a regra: health = proporção de audits saudáveis sobre o total, agregada por execução, com breakdown mobile/desktop.

## 2. Requisitos / Critérios de aceite

- [ ] Dado uma execução com 2 análises de sucesso (100 audits/10 problemas e 100 audits/20 problemas), quando o workflow conclui, então `execucao.resultado_json["health_score"]["health_score"] == 85.0`.
- [ ] Dado uma execução onde TODAS as URLs falharam no PSI, então `resultado_json["health_score"]` é `null` (a execução já falha com `motivo_falha=psi_total` — não inventar score).
- [ ] Dado uma execução mista (1 sucesso + 1 falha PSI), então a falha fica fora do denominador e o health reflete só as análises de sucesso.
- [ ] Dado uma execução antiga sem o campo, quando `GET /core-web-vitals/execucao/{id}/health-score`, então o backend calcula on-the-fly a partir das análises persistidas e responde 200 com o mesmo shape.
- [ ] Dado o dashboard com execução concluída, então um card exibe o % com classificação de cor (≥90 verde, 50–89 âmbar, <50 vermelho — mesmos cortes do Lighthouse usados nos tiles existentes).

## 3. Design (mapeado ao código)

### 3.1 Serviço puro — `backend/app/services/cwv_health.py` (novo)

```python
def calcular_health_score(analises: list[dict]) -> dict | None
```

- Entrada: lista de dicts com ao menos `status`, `estrategia`, `audits_totais`, `n_problemas` (o chamador fornece; ver 3.2).
- Considera apenas `status == "sucesso"` e `audits_totais > 0`. Se nenhuma qualificar → `None`.
- `n_pass = audits_totais - n_problemas` (piso 0 por segurança), somado sobre as análises.
- Retorno:

```json
{"health_score": 85.0, "n_pass": 170, "n_total": 200,
 "por_estrategia": {"mobile": 84.0, "desktop": 86.0}}
```

- Arredondar a 1 casa (`round(x, 1)`). `por_estrategia` omite estratégia sem análises de sucesso.

Nota de semântica: desde a paridade total PSI (`SPEC_CWV_Paridade_Total_PSI`), problemas ≈ audits falhos 1:1, então `n_problemas` da análise é um proxy fiel de "audits Fail". Documentar no docstring.

### 3.2 Workflow — `workflow.py::_run_workflow_cwv`

Após calcular `custo` e antes de montar `resultado_json` final: buscar as análises persistidas da execução (reusar `cwv_persistencia`: para cada id em `estado_final["analises_persistidas"]`, `buscar_analise_por_id` + contagem de problemas — ou uma query única nova `contar_problemas_por_analise(session, ids) -> dict[str, int]` em `cwv_persistencia.py`, preferível para evitar N+1). Montar a lista de dicts e chamar `calcular_health_score`. Gravar em `resultado_json["health_score"]` (pode ser `None`).

### 3.3 Endpoint fallback — `routers/ferramentas_cwv.py`

`GET /core-web-vitals/execucao/{execucao_id}/health-score` → `HealthScoreResposta`:
- Ownership: mesma checagem de `buscar_execucao_cwv` (404 se não é do usuário).
- Se `resultado_json["health_score"]` existe → devolve direto.
- Senão → carrega análises da execução (query por `CwvAnalise.execucao_id`) + contagens e calcula on-the-fly (sem persistir).

`schemas/cwv.py`:

```python
class HealthScorePorEstrategia(BaseModel):
    mobile: float | None = None
    desktop: float | None = None

class HealthScoreResposta(BaseModel):
    health_score: float | None
    n_pass: int = 0
    n_total: int = 0
    por_estrategia: HealthScorePorEstrategia = HealthScorePorEstrategia()
```

### 3.4 Frontend

- `lib/api/cwv.ts`: `buscarHealthScoreCwv(execucaoId)` → GET do endpoint acima.
- `cwv-execucao-client.tsx`: card "Health Score" quando execução concluída (usa `resultado_json.health_score` se já veio no payload da execução; senão chama o endpoint).
- `cwv-dashboard-client.tsx`: exibir o health da execução mais recente do cliente, com breakdown mobile/desktop em texto secundário.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Persistência | Campo em `resultado_json` da execução | Coluna nova em `execucoes_ferramentas` (tabela compartilhada entre ferramentas — não poluir) |
| Denominador | Audits com score das análises de sucesso | Incluir falhas PSI como "fail" (distorce: falha de coleta ≠ página ruim) |
| Fórmula | Σpass/Σtotal global (pondera URLs com mais audits) | Média dos % por análise (daria peso igual a URLs com poucos audits aplicáveis) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_health.py -q
```

Novo `backend/tests/unit/test_cwv_health.py` (função pura, sem DB):
1. lista vazia → `None`; só falhas → `None`.
2. mix sucesso+falha → falha fora do denominador.
3. duas análises (90/100 e 80/100) → 85.0 com breakdown por estratégia correto.
4. `n_problemas > audits_totais` (edge defensivo) → pass clampado em 0, sem negativo.
5. arredondamento a 1 casa.

Teste de rota (padrão dos testes de router existentes): execução de outro usuário → 404; execução antiga sem campo → cálculo on-the-fly 200.

## 6. Não-objetivos

- Health score do **checklist da auditoria** (before/after com itens de page experience) — é responsabilidade de `[[SPEC_CWV_Auditoria_Ciclo_De_Vida]]`, que copia/recalcula este valor.
- Série histórica de health por cliente (dashboard de evolução) — V2.

## 7. Avisos ao implementador

1. Não alterar o shape existente de `resultado_json` (`n_urls_analisadas`, `n_urls_falharam`, `analise_ids`) — apenas adicionar a chave `health_score`.
2. O hook no `_run_workflow_cwv` roda dentro da mesma sessão/fluxo de billing existente — não adicionar commits extras nem mexer na ordem reserva→débito (bug histórico da `SPEC_Billing_CWV`).
3. Ownership 404 (nunca 403) em rota nova, padrão dos endpoints de `ferramentas_cwv.py`.
4. Evitar N+1 ao contar problemas: query agregada única (ver `buscar_historico_url` que já usa subquery de contagem como referência).

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
