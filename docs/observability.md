# Observabilidade

## Structured Logging

Logs em JSON via `core/logging.py:JsonFormatter`. Ativado automaticamente em `main.py` e `worker.py`.

### Eventos criticos (com campo `event_type`)

| Evento | Onde |
|--------|------|
| `auth.login.success` | `services/auth_service.py` |
| `auth.login.fail` | `services/auth_service.py` |
| `auth.register.success` | `services/auth_service.py` |
| `auth.password_changed` | `services/auth_service.py` |
| `auth.password_reset.requested` | `services/auth_service.py` |
| `auth.password_reset.completed` | `services/auth_service.py` |
| `credito.reservado` | `services/credito_service.py` |
| `credito.debitado` | `services/credito_service.py` |
| `credito.liberado` | `services/credito_service.py` |
| `workflow.start` | `worker.py` |
| `workflow.completed` | `worker.py` |
| `workflow.failed` | `worker.py` |
| `workflow.cancelled` | `worker.py` |
| `workflow.retry` | `worker.py` |
| `rate_limit.exceeded` | `core/rate_limit.py` |

Convencao: sempre incluir `usuario_id` e `execucao_id` quando aplicavel.

## LangSmith (tracing de agentes)

Opcional. Ativar via env vars:

```
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=seo-saas
```

Ou via `config.py`:

- `langsmith_api_key`
- `langsmith_project`
- `langsmith_endpoint` (default: `https://api.smith.langchain.com`)

Agentes decorados com `@traceable`:
- `rerank_candidatos` (tag: `inlinks`)
- `revisor_inlinks` (tag: `inlinks`)

Alternativa self-hosted: **Langfuse** — compativel com OpenTelemetry.

## Prometheus (metricas)

Endpoint: `GET /metrics` (fora do schema OpenAPI).

Proteger via IP allowlist:

```
METRICS_ALLOWLIST=["10.0.0.1","10.0.0.2"]
```

Métricas disponíveis:

| Metrica | Tipo | Labels |
|---------|------|--------|
| `llm_calls_total` | Counter | `model`, `usuario_id` |
| `llm_call_duration_seconds` | Histogram | `model` |
| `workflow_duration_seconds` | Histogram | `ferramenta`, `status` |
| `credits_reserved_total` | Gauge | — |
| `rate_limit_blocks_total` | Counter | `endpoint`, `scope` |

Dashboards Grafana recomendados:
- Workflow throughput / duration percentiles
- LLM cost estimado (modelo x tokens)
- Credits reserved vs available
- Rate limit blocks por endpoint

## Sentry (erros)

Opcional. Ativar via env:

```
SENTRY_DSN=https://...
```

Integracao automatica com FastAPI. No worker, sem integracao FastAPI (somente SDK puro).

## Tests

```
cd backend && python -m pytest tests/ -v
```

CI: `.github/workflows/test.yml` — roda pytest + ruff em cada push/PR.
