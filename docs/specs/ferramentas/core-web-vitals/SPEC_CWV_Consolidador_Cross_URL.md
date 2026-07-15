# SPEC — Consolidador Cross-URL (dedup, causa raiz e escopo via LLM juiz)

**Status:** ✅ implementado
**Capacidade:** `core-web-vitals`
**Escopo:** backend (agente novo, job arq, tabela, endpoint) + frontend (aba de consolidados na auditoria)
**Código:** `backend/app/agents/cwv/consolidador.py` (novo), `backend/app/models/cwv_problema_consolidado.py` (novo), `backend/app/routers/ferramentas_cwv_auditoria.py`, `backend/app/schemas/cwv_auditoria.py`, `backend/app/config.py`, `backend/app/worker.py`, `backend/migrations/versions/0028_cwv_problema_consolidado.py`, `frontend/src/components/cwv/cwv-auditoria-client.tsx`  ·  **Rota:** `core-web-vitals/auditoria/[auditoriaId]`
**Créditos:** não cobra (decisão travada; custo LLM = 1 chamada por auditoria)
**Depende de:** `[[SPEC_CWV_Auditoria_Ciclo_De_Vida]]`, `[[SPEC_CWV_Estimador_Esforco]]`
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gaps #10, #24); padrão do juiz LLM de Inlinks (`docs/specs/ferramentas/inlinks-reversos/SPEC_Distribuir_Viabilidade_Pelo_Juiz.md`)

---

## 1. Contexto (por quê)

Uma execução de 8 URLs × 2 estratégias com `render-blocking-resources` em todas gera 16 problemas idênticos — a planilha (e qualquer consultor) trata isso como **1 problema com escopo** ("todas as páginas, Desktop e Mobile"). Além do dedup, o consultor identifica **causa raiz** ("os 5 problemas de TBT vêm do bundle X de 900KB"). Esta spec cria essa camada: agrupamento determinístico primeiro, e **uma única chamada LLM por auditoria** para mesclar grupos correlatos, redigir causa raiz e escopo — seguindo o padrão do juiz de Inlinks (saída estruturada, validação em lista fechada, fail-open, kill-switch).

## 2. Requisitos / Critérios de aceite

- [ ] Dado uma auditoria cuja execução tem o mesmo `kb_codigo` em 8 URLs × 2 estratégias, quando `POST /core-web-vitals/auditorias/{id}/consolidar` conclui, então existe exatamente 1 `cwv_problema_consolidado` com `escopo_json.urls` de tamanho 8 e `escopo_json.estrategias == ["mobile","desktop"]`.
- [ ] Dado que o LLM mescla os grupos 1 e 2 num só, então o consolidado resultante tem `problemas_origem_ids` cobrindo os problemas dos dois grupos.
- [ ] Dado que o LLM retorna `grupo_id` inexistente ou repetido em mais de um consolidado, então a resposta do LLM é descartada e a consolidação degrada para 100% determinística — `consolidacao_status='concluida'` mesmo assim (fail-open).
- [ ] Dado `settings.cwv_consolidador_llm_habilitado=False`, então ZERO chamadas LLM e os consolidados são gerados deterministicamente (título do problema, escopo por template).
- [ ] Dado consolidação concluída, então todo `cwv_checklist_item` com `status_before='fail'` e `origem='psi_audit'` tem `problema_consolidado_id` preenchido.
- [ ] Dado `POST .../consolidar` repetido, então os consolidados anteriores são apagados e recriados (idempotência), sem duplicar.
- [ ] Dado auditoria de outro usuário → 404; auditoria sem `execucao_before_id` → 409.

## 3. Design (mapeado ao código)

### 3.1 Tabela — migração `0028_cwv_problema_consolidado.py`

`cwv_problema_consolidado` (`models/cwv_problema_consolidado.py`):

| Coluna | Tipo |
|---|---|
| `auditoria_id` | UUID FK `cwv_auditoria.id` ON DELETE CASCADE NOT NULL |
| `titulo` | Text NOT NULL |
| `causa_raiz` | Text NOT NULL default `''` |
| `kb_codigo` | String(80) NULL |
| `audit_ids` | JSONB NOT NULL default `'[]'` |
| `problemas_origem_ids` | JSONB NOT NULL default `'[]'` (UUIDs string — snapshot, sem FK) |
| `evidencias_json` | JSONB NOT NULL default `'{}'` (top recursos agregados, savings somados) |
| `severidade` | SmallInteger NOT NULL (CHECK 1-5) |
| `prioridade_ordem` | Integer NOT NULL |
| `esforco` | String(10) NULL (CHECK baixo/medio/alto) |
| `metricas_afetadas` | JSONB NOT NULL default `'[]'` |
| `escopo_json` | JSONB NOT NULL default `'{}'` — `{"urls": [...], "estrategias": [...], "descricao": "..."}` |
| `recomendacao_md` | Text NOT NULL default `''` |
| `criado_em` | timestamptz |

Índice `ix_cwv_consolidado_auditoria (auditoria_id, prioridade_ordem)`. **Nesta mesma migração**: adicionar a FK `cwv_checklist_item.problema_consolidado_id → cwv_problema_consolidado.id ON DELETE SET NULL` (a coluna já existe sem FK desde a migração 0026).

### 3.2 Agente — `agents/cwv/consolidador.py` (novo)

**Fase 1 — determinística** (`agrupar_problemas(problemas: list[dict]) -> list[dict]`): agrupa pela chave canônica `cwv_auditoria_service.chave_problema` (a mesma do checklist). Cada grupo: `grupo_id` sequencial (1..N), `kb_codigo`, `audit_ids`, `titulo` (do problema de maior severidade), `severidade` (max), `esforco` (max na ordem baixo<medio<alto), `metricas_afetadas` (união), `urls`/`estrategias` (das análises de origem), `savings_total_ms`/`savings_total_bytes` (soma de `contexto_especifico.savings_*`), `top_recursos` (até 3 items com maior `wastedMs|wastedBytes`, só `url` truncada a 80 chars + valor), `problemas_ids`.

**Fase 2 — LLM (1 chamada)**, apenas se `settings.cwv_consolidador_llm_habilitado` e há ≥ 2 grupos: prompt pt-BR com a lista compacta dos grupos (teto 50; excedentes ficam determinísticos) e instruções: mesclar apenas grupos com causa raiz comum, nunca inventar grupo_id, redigir causa raiz citando recursos reais dos `top_recursos`. Classe `BaseAgent` com `invoke_structured` (padrão `agents/cwv/analisador.py`), modelo por setting nova `cwv_consolidador_llm_model: str = "gpt-4o-mini"` e `cwv_consolidador_llm_temperature: float = 0.1` em `config.py`, registrados como os `cwv_*` existentes.

Schema de saída:

```python
class GrupoConsolidadoOut(BaseModel):
    grupos_origem: list[int]          # >= 1 grupo_id da fase 1
    titulo: str
    causa_raiz: str
    escopo_descricao: str             # ex.: "Todas as páginas de produto (mobile e desktop)"
    recomendacao_resumo: str          # 2-4 frases nomeando recursos reais

class ConsolidacaoOut(BaseModel):
    grupos: list[GrupoConsolidadoOut]
    observacoes_gerais: str | None = None
```

**Validação fail-open** (padrão juiz Inlinks): todo `grupo_id` referenciado deve existir e aparecer no máximo 1 vez no total; violação → descarta a resposta inteira e segue determinístico (log warning + métrica counter novo `cwv_consolidador_fallback_total` em `app/core/metrics.py`). Grupos não citados pelo LLM → consolidados determinísticos individuais. Campos numéricos do consolidado (severidade, prioridade, esforço, métricas, escopo urls/estratégias) são SEMPRE determinísticos — o LLM só contribui texto (título, causa raiz, escopo_descricao, recomendação) e a decisão de mescla.

Prioridade final: reusar `priorizador.py::priorizar_problemas` sobre os consolidados (score = severidade × Σ peso métrica; desempate por nº de URLs desc).

### 3.3 Job e endpoint

- `async def executar_consolidacao_cwv(ctx, auditoria_id: str)` no `consolidador.py`, registrada em `backend/app/worker.py::functions` (**obrigatório** — sem isso o job nunca roda). Fluxo: seta `consolidacao_status='executando'` → carrega problemas da `execucao_before_id` → fase 1 → fase 2 → apaga consolidados antigos da auditoria → insere novos → vincula `cwv_checklist_item.problema_consolidado_id` (match por `item_codigo` == chave do grupo de origem) → `consolidacao_status='concluida'`. Exceção → `'falhou'` + log (nunca re-raise não tratado).
- `POST /core-web-vitals/auditorias/{auditoria_id}/consolidar` (router da auditoria): ownership 404; sem `execucao_before_id` → 409; `consolidacao_status='executando'` → 409; enfileira via `redis.enqueue_job("executar_consolidacao_cwv", auditoria_id)` (padrão de `analisar_cwv`), responde 202 `{status: "executando"}`.
- `GET /core-web-vitals/auditorias/{auditoria_id}/consolidados` → `{consolidados: [ProblemaConsolidadoResposta]}` ordenado por prioridade (schema novo em `schemas/cwv_auditoria.py`).

### 3.4 Frontend

`cwv-auditoria-client.tsx`: botão "Consolidar problemas" (visível quando `consolidacao_status` ∈ nao_executada|falhou; polling leve do GET da auditoria enquanto `executando`); aba/seção "Plano consolidado" listando os consolidados (título, causa raiz, escopo descrição, badges severidade/esforço, recomendação) — reutilizar visual do accordion de `cwv-plano-acao.tsx`.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Nº de chamadas LLM | 1 por auditoria, contexto compacto (~100-200 tokens/grupo, teto 50 grupos) | 1 por problema/grupo (custo linear, sem visão de conjunto para causa raiz) |
| Papel do LLM | Só mescla + texto; números sempre determinísticos | LLM define severidade/prioridade (variância em dado auditável) |
| Execução | Job arq separado por auditoria | Dentro do workflow LangGraph da execução (consolidação é da campanha, não da coleta; permite re-rodar) |
| Robustez | Fail-open + kill-switch `cwv_consolidador_llm_habilitado` | Falhar a consolidação se o LLM falhar (bloquearia o relatório) |
| Vínculo com problemas | `problemas_origem_ids` snapshot JSONB | Tabela associativa N:N (excesso; consolidado é derivado recriável) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_consolidador.py -q
```

Novo `backend/tests/unit/test_cwv_consolidador.py` (LLM mockado via monkeypatch em `invoke_structured`, padrão dos testes do analisador):
1. Fase 1: 16 problemas (8 URLs × 2) da mesma chave → 1 grupo com urls=8, estratégias=2, savings somados.
2. Fase 1: chaves distintas → grupos distintos; `top_recursos` são os 3 maiores desperdícios.
3. Fase 2 válida: LLM mescla grupos [1,2] → 1 consolidado com origem de ambos; grupos não citados viram consolidados determinísticos.
4. Fase 2 inválida: grupo_id inexistente → resposta descartada, tudo determinístico, status `concluida`, métrica incrementada.
5. Kill-switch off → `invoke_structured` nunca chamado (assert no mock).
6. Idempotência: rodar 2× → mesma contagem de consolidados.
7. Vínculo: checklist items fail ganham `problema_consolidado_id`.

## 6. Não-objetivos

- Narrativa executiva e plano faseado — `[[SPEC_CWV_Relatorio_Executivo]]` (consome os consolidados).
- Consolidação entre execuções/auditorias diferentes.
- Cobrança de créditos pela consolidação (decisão travada).

## 7. Avisos ao implementador

1. **Registrar `executar_consolidacao_cwv` em `worker.py::functions`** — job não registrado falha silenciosamente.
2. Padrão LLM da casa: `invoke_structured` + validação em lista fechada + fail-open + kill-switch por setting; prompts pt-BR (referências: `agents/cwv/analisador.py`, `agents/inlinks/inseridor.py`).
3. NÃO enviar `documentacao_md` nem `details/items` completos ao LLM — só o contexto compacto da fase 1 (custo).
4. Migração `0028` adiciona a FK pendente de `cwv_checklist_item.problema_consolidado_id` (coluna criada sem FK na 0026); conferir a última migração real antes de encadear.
5. Ownership 404; enfileiramento com tratamento de falha (padrão dos endpoints 202 existentes em `ferramentas_cwv.py` — em falha de enqueue, reverter `consolidacao_status`).
6. Fail-open TOTAL no job: qualquer exceção → `consolidacao_status='falhou'`, sem quebrar nada mais.

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
