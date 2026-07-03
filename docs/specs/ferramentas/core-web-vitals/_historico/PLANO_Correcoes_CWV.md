# PLANO — Correções da ferramenta Core Web Vitals

**Status:** 🗄️ histórico — plano aplicado
**Origem:** análise crítica do pipeline CWV (LangGraph linear, sem interrupt):
`coletar_psi → detectar_plataformas → analisar_seo → documentar → pesquisar_outros → priorizar → persistir`
**Público:** outra IA / dev implementando as correções
**Esforço total estimado:** ~11–15h

## 0. Como usar

4 SPECs independentes, cada uma é um PR. Ordem recomendada abaixo. SPEC-A (billing) primeiro por impacto financeiro e por tocar `_obter_reserva_estimada` (compartilhado).

| Ordem | SPEC | Severidade | Impacto | Esforço | Arquivo |
|---|---|---|---|---|---|
| 1 | Billing CWV (vazamento de reserva) | 🔴 Crítico | Créditos presos / saldo do usuário | ~3h | [`SPEC_Billing_CWV.md`](./SPEC_Billing_CWV.md) |
| 2 | Payload bruto do PSI (DB bloat + memória) | 🟠 Alto | Storage + RAM | ~3h | [`SPEC_Payload_PSI_Bruto.md`](./SPEC_Payload_PSI_Bruto.md) |
| 3 | Performance (pesquisador paralelo + PSI) | 🟡 Médio | Latência + robustez | ~4h | [`SPEC_Performance_PSI_Pesquisador.md`](./SPEC_Performance_PSI_Pesquisador.md) |
| 4 | Robustez/limpeza | 🔵 Baixo | Consistência / fault-tolerance | ~3h | [`SPEC_Robustez_Limpeza_CWV.md`](./SPEC_Robustez_Limpeza_CWV.md) |

> SPEC-A, B e D tocam `workflow.py`/`cwv_persistencia.py` — coordenar merge. SPEC-C é mais isolada.

## 1. Diagnóstico

| # | Problema | Causa raiz | SPEC |
|---|---|---|---|
| 1 | **Vazamento de reserva**: router reserva o custo total, mas finalizes liberam/confirmam só `CUSTO_BASE_CWV=15` → `(reserva−15)` créditos presos em `saldo_reservado` por execução | `_obter_reserva_estimada("core_web_vitals")` retorna 15; `_run_workflow_cwv` usa `reservado=custo_base` (`workflow.py:471,450,478`; `:337,392`) | A |
| 2 | `raw_psi_json` (payload Lighthouse, MBs) gravado e **nunca lido** | `cwv_persistencia.py:65` `raw_psi_json=psi_resultado.get("payload", {})` | B |
| 3 | Payload bruto trafega por todo o estado (memória); só `detectar_plataforma` o usa | `node_coletar_psi` guarda `payload` em `psi_resultados` (`workflow.py:58,94`) | B |
| 4 | `node_pesquisar_outros` sequencial (LLM+web por problema, em série) | loop aninhado sem `gather` (`workflow.py:199-231`) | C |
| 5 | PSI sem retry em 5xx e sem pool de conexão | `httpx.AsyncClient` por request; retry só em 429/403 (`cwv_psi_client.py:29,50`) | C |
| 6 | `compile()` sem checkpointer + `thread_id` morto (sem resume on crash) | `construir_workflow` (`workflow.py:310`) vs `config` com thread_id (`:382`) | D |
| 7 | Agentes recriam `ChatOpenAI` sem cache | `analisador.py:23-32`, `pesquisador.py:52-59` | D |
| 8 | `except CancelledError` usa `execucao` do try → `UnboundLocalError` se cancelado cedo | `workflow.py:389-392` | D |
| 9 | `override_plataforma` não regenera docs de problemas pesquisados (sem kb_codigo) | `ferramentas_cwv.py:399-406` | D |
| 10 | Export .docx síncrono (python-docx) bloqueia o event loop | `ferramentas_cwv.py:465,502` | D |

## 2. Referências

- Código: `app/agents/cwv/*.py`, `app/routers/ferramentas_cwv.py`, `app/services/cwv_*.py`, `app/services/ferramenta_service.py`.
- Doc LangGraph (via MCP): `thread_id` serve para uso **com** checkpointer (continuidade/tolerância a falha); sem checkpointer é inerte — fundamenta #6.
- Precedentes no repo: `SPEC_Billing_Inlinks.md` (mesma classe de bug de reserva, mesma técnica de fix) e `SPEC_Qualidade_Agentes_Inlinks.md` (temperatura/modelo por agente via `BaseAgent`, já disponível).

## 3. Princípios

1. **Reserva = liberação = `reservado=`** no débito. Fonte única: `_obter_reserva_estimada`.
2. **Não persistir nem trafegar dados grandes que não são lidos** (payload bruto).
3. **Não quebrar** parecer/inlinks/gerar-artigo ao mexer em `_obter_reserva_estimada` (compartilhado).
4. Reusar infra existente (`BaseAgent` com temperature/model; `ctx["http"]`; semáforos do módulo CWV).
