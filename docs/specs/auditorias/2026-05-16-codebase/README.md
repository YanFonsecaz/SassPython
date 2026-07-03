# Auditoria 2026-05-16 — Índice das SPECs

Auditoria crítica da codebase (10k LOC backend + frontend) revelou **48 issues** distribuídos por severidade. Agrupados em 8 SPECs por tema. Cada SPEC referencia issues do diagnóstico original.

## Ordem recomendada de aplicação

| Ordem | SPEC | Tempo | Bloqueante p/ produção? |
|---|---|---|---|
| 1 | [01 — P0 Bloqueadores](SPEC_01_P0_Bloqueadores.md) | ~2h | ✅ SIM |
| 2 | [03 — Créditos transacional](SPEC_03_Creditos_Transacional.md) | ~3h | ✅ SIM (race over-spend) |
| 3 | [05 — ARQ Worker robustness](SPEC_05_ARQ_Worker_Robustness.md) | ~3h | ⚠️ Antes de 10+ usuários |
| 4 | [04 — Multi-tenant concorrência](SPEC_04_Multitenant_Concorrencia.md) | ~4h | ⚠️ Antes de 5+ usuários |
| 5 | [02 — Auth security hardening](SPEC_02_Auth_Security_Hardening.md) | ~4h | ⚠️ Antes de prod-público |
| 6 | [06 — LangGraph production](SPEC_06_LangGraph_Production.md) | ~6h | ❌ Refactor, não bloqueia |
| 7 | [07 — Observability + tests](SPEC_07_Observability_Tests.md) | ~6h | ❌ Sustainability |
| 8 | [08 — Code quality cleanup](SPEC_08_Code_Quality_Cleanup.md) | ~4-6h | ❌ Dívida técnica |
| 9 | [09 — Pós-auditoria: 17 bugs residuais](SPEC_09_Pos_Auditoria_Bugs_Residuais.md) | ~5-7h | ✅ SIM (5 P0 introduzidos pelos SPECs anteriores) |
| 10 | [10 — Limpeza pós-auditoria](SPEC_10_Limpeza_Pos_Auditoria.md) | ~3-4h | ❌ Dívida técnica (44 ruff + config órfãs + docs) |
| 11 | [11 — UX: unificar inlinks numa rota](SPEC_11_UX_Unificar_Inlinks.md) | ~1.5h | ⚠️ UX/discoverability (frontend only) |

**Total estimado:** 41-46h de engenharia.

## Mapa de issues → SPECs

| # | Issue | SPEC |
|---|---|---|
| 1 | SyntaxError workflow.py | 01 §1.1 |
| 2 | CSRF bypass | 01 §1.2 |
| 3 | sleep/httpx síncrono | 01 §1.3 |
| 4 | Race créditos | 01 §1.4, 03 |
| 5 | Default secrets | 01 §1.5 |
| 6 | Hash refresh fraco | 01 §1.6 |
| 7 | arq max_jobs=3 | 01 §1.7 |
| 8 | user cache process-local | 04 §4.1 |
| 9 | rate limit process-local | 04 §4.2 |
| 10 | LLM rate limit global | 04 §4.3 |
| 11 | Retry overly broad | 04 §4.4 |
| 12 | Worker swallow exceptions | 05 §5.1 |
| 13 | Cancel não cancela | 05 §5.3 |
| 14 | Checkpointer sem pool | 06 §6.1 |
| 15 | Pubsub conn única | 04 §4.5 |
| 16 | job_timeout < workflow_timeout | 05 §5.2 |
| 17 | Embeddings fallback sequencial | 04 §4.6 |
| 18 | gather sem lock | 08 §8.8 |
| 19 | Semaphore dict race | 04 §4.3 |
| 20 | SHA256 legacy | 02 §2.1 |
| 21 | HIBP fail-open | 02 §2.2 |
| 22 | CSP unsafe-* | 02 §2.3 |
| 23 | criar_execucao hardcoded | 08 §8.3 |
| 24 | datetime.utcnow | 08 §8.1 |
| 25 | dead code credito | 03 §3.8, 08 §8.10 |
| 26 | imports tardios | 08 §8.2 |
| 27 | CORS permissiva | 02 §2.6 |
| 28 | cookie secure dev | 02 §2.4 |
| 29 | SPA via FastAPI | 02 §2.7 |
| 30 | imports tardios cosine | 08 §8.2 |
| 31 | on_startup sem warmup | 05 §5.4 |
| 32 | INSERT loop persistir | 08 §8.4 |
| 33 | saida_json vs resultado_json | 08 §8.6 |
| 34 | race criar conta | 03 §3.6 |
| 35 | aprovar_reprovar status race | 08 §8.5 |
| 36 | sem tests | 07 §7.3 |
| 37 | logger ad-hoc | 07 §7.1 |
| 38 | file size workflow_reversos | 08 §8.7 |
| 39 | checkpointer pool (= #14) | 06 §6.1 |
| 40 | astream events não consumidos | 06 §6.2 |
| 41 | interrupt declarativo | 06 §6.3 |
| 42 | structured outputs | 06 §6.4 |
| 43 | publish_event datetime.utcnow | 08 §8.9 |
| 44 | sem LangSmith | 07 §7.2 |
| 45 | sem LCEL | 06 §6.6 |
| 46 | boilerplate nó | 06 §6.7 |
| 47 | BaseAgent achata return | 06 §6.5 |
| 48 | LangChain inconsistente | 02 §2.8 |

## Dependências entre SPECs

```
SPEC_01 (P0)
   ├─→ SPEC_02 (auth hardening — depende de secrets validados)
   ├─→ SPEC_03 (créditos — formaliza §1.4)
   │     └─→ SPEC_04 (multi-tenant — usa Redis ja configurado)
   │            └─→ SPEC_05 (worker — usa ctx pools)
   │                   └─→ SPEC_06 (langgraph — usa pool do worker)
   └─→ SPEC_07 (observability — independente)
SPEC_08 (cleanup — independente, mas best after 01-06)
```

## Status de produção após aplicação

| Aplicado | Pronto p/ |
|---|---|
| SPEC 01 | Demos/staging com 1 usuário |
| SPEC 01 + 03 | Beta privado (5 usuários) |
| SPEC 01 + 03 + 05 | Beta público (20 usuários) |
| SPEC 01-05 | Produção (100+ usuários) |
| SPEC 01-08 | SaaS maduro, sustentável |

## Verificação consolidada

Cada SPEC tem sua própria seção "Verificação". Tests críticos de regressão (SPEC 07 §7.3) cobrem:
- `test_workflow_syntaxerror.py` — Issue #1
- `test_csrf_required.py` — Issue #2
- `test_async_no_blocking.py` — Issue #3
- `test_credito_race.py` — Issue #4
- `test_secrets_validation.py` — Issue #5
- `test_refresh_token_hmac.py` — Issue #6

Suite CI executa todos a cada push.
