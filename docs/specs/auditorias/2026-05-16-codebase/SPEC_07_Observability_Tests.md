# SPEC 07 — Observability, structured logging, testes

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** `core/logging`, novo `tests/`, integrações externas · **Severidade:** Média
**Cobre issues:** #36 (no tests), #37 (logger ad-hoc), #44 (sem tracing LLM)

**Depende de:** SPEC_05 e SPEC_06 (alguns logs estruturados dependem do worker ctx).

---

## 7.1 — Structured logging com JSON output

### Problema
`logger.info("text %s", arg)` misturado com `logger.info("event", extra={...})`. Sem padronização → grep frágil em prod.

### Fix
```python
# core/logging.py (novo)
import json
import logging
import sys
from datetime import datetime, UTC

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Capturar extras (sem reservados do logging)
        for key, val in record.__dict__.items():
            if key in ("name", "msg", "args", "levelname", "levelno", "pathname",
                      "filename", "module", "exc_info", "exc_text", "stack_info",
                      "lineno", "funcName", "created", "msecs", "relativeCreated",
                      "thread", "threadName", "processName", "process", "getMessage"):
                continue
            try:
                json.dumps(val)
                log[key] = val
            except (TypeError, ValueError):
                log[key] = str(val)

        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)

        return json.dumps(log, ensure_ascii=False)


def setup_logging(level: str = "INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Suprimir spam de bibliotecas
    logging.getLogger("sqlalchemy.engine").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("httpcore").setLevel("WARNING")
```

`main.py` lifespan + `worker.py` ctx_startup chamam `setup_logging(settings.log_level)`.

### Convenções
- `logger.info("event_name", extra={"key": value, ...})`
- Eventos importantes têm campo `event_type`:
  - `auth.login.success`
  - `auth.login.fail`
  - `auth.password_changed`
  - `credito.reservado`
  - `credito.debitado`
  - `credito.liberado`
  - `workflow.start`
  - `workflow.completed`
  - `workflow.failed`
  - `workflow.cancelled`
  - `rate_limit.exceeded`
- Sempre incluir `usuario_id`, `execucao_id` quando aplicável.

```python
logger.info(
    "workflow.completed",
    extra={
        "event_type": "workflow.completed",
        "execucao_id": eid,
        "usuario_id": uid,
        "duration_s": dur,
        "ferramenta": "distribuir_inlinks",
        "n_aplicadas": n,
    },
)
```

---

## 7.2 — LangSmith para tracing de agentes

### Por quê
Sem isso, debug de "por que o Reranker rejeitou X" é cego. Com LangSmith, vê-se prompt, output e intermediários por execução.

### Fix
```python
# config.py
langsmith_api_key: str = ""
langsmith_project: str = "seo-saas"
langsmith_endpoint: str = "https://api.smith.langchain.com"

# main.py lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    if settings.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
        logger.info("langsmith.enabled", extra={"project": settings.langsmith_project})
    yield
```

Mesmo bloco no `worker.py:ctx_startup`.

Tag por usuário:
```python
# em cada agente
from langsmith import traceable

@traceable(name="reranker", tags=["distribuir_inlinks"])
async def rerank_candidatos(...):
    ...
```

Plus: adicionar `metadata` por request com `usuario_id` e `execucao_id` para filtros.

### Alternativa
Self-hosted Langfuse — gratuito, igualmente integrado via OpenTelemetry. Documentar como alternativa no `docs/observability.md`.

---

## 7.3 — Tests structure

### Problema (#36)
`pyproject.toml` referencia `testpaths = ["tests"]` mas dir não existe.

### Fix — estrutura mínima
```
backend/tests/
├── __init__.py
├── conftest.py          # fixtures comuns
├── unit/
│   ├── test_credito_service.py
│   ├── test_auth_service.py
│   ├── test_rate_limit.py
│   ├── test_seguranca.py
│   ├── test_scraper_normalize.py
│   └── test_embeddings.py
├── integration/
│   ├── test_distribuir_inlinks_workflow.py
│   ├── test_gerar_artigo_workflow.py
│   ├── test_credito_race.py     # SPEC 03 verificação
│   └── test_cancelamento.py     # SPEC 05 verificação
└── e2e/
    └── test_full_user_flow.py
```

### `conftest.py` essencial
```python
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.config import settings

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session():
    """Sessão isolada por teste; rollback ao final."""
    engine = create_async_engine(settings.test_database_url)
    async with engine.connect() as conn:
        async with conn.begin() as trans:
            session = AsyncSession(conn)
            yield session
            await trans.rollback()

@pytest.fixture
async def cliente_teste(db_session):
    """Cria usuário + conta com saldo padrão."""
    ...

@pytest.fixture
def llm_mock(monkeypatch):
    """Mock que retorna respostas determinísticas para testes."""
    ...
```

### Tests críticos de regressão (priorizar)
1. **`test_credito_race.py`** — verifica fix SPEC 03 §3.2 (race over-spend).
2. **`test_workflow_syntaxerror.py`** — garante que workflow.py importa (regressão do bug #1).
3. **`test_csrf_required.py`** — verifica fix SPEC 01 §1.2.
4. **`test_async_no_blocking_sleep.py`** — garante async-only em paths quentes.
5. **`test_rate_limit_redis.py`** — verifica fix SPEC 04 §4.2 funciona cross-process.

```python
# test_workflow_syntaxerror.py
def test_workflow_imports():
    """Regressão #1: workflow.py começou com '2import' uma vez."""
    import app.agents.workflow
    assert hasattr(app.agents.workflow, "executar_workflow_completo")
```

### CI
`.github/workflows/test.yml`:
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres: { image: postgres:16, env: { POSTGRES_PASSWORD: pw }, ports: ['5432:5432'] }
      redis: { image: redis:7, ports: ['6379:6379'] }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e ".[dev]"
      - run: pytest -v --cov=app --cov-report=term-missing
      - run: ruff check app/
      - run: mypy app/
```

---

## 7.4 — Métricas (Prometheus)

```python
# core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

llm_calls_total = Counter("llm_calls_total", "Total LLM calls", ["model", "usuario_id"])
llm_call_duration = Histogram("llm_call_duration_seconds", "LLM call duration", ["model"])
workflow_duration = Histogram("workflow_duration_seconds", "Workflow duration", ["ferramenta", "status"])
credits_reserved = Gauge("credits_reserved_total", "Total credits reserved")
rate_limit_blocks = Counter("rate_limit_blocks_total", "Rate limit blocks", ["endpoint", "scope"])
```

Expor endpoint `/metrics` (FastAPI):
```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

Proteger via IP allowlist ou basic auth.

### Dashboards (Grafana)
- Workflow throughput / duration percentiles
- LLM cost (estimar por modelo × token count)
- Credits reserved vs available
- Rate limit blocks por endpoint
- Worker job count / queue depth

---

## 7.5 — Sentry (errors)

```python
# config.py
sentry_dsn: str = ""

# main.py lifespan
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
        environment=settings.ambiente,
    )
```

Mesmo em worker.py.

---

## Critério de pronto

- [ ] JSON logging ativo em api + worker
- [ ] Eventos críticos têm `event_type` field
- [ ] LangSmith opcional, ativável via env
- [ ] `tests/conftest.py` + ≥5 tests críticos
- [ ] CI rodando pytest + ruff + mypy
- [ ] `/metrics` Prometheus disponível
- [ ] Sentry opcional, ativável via env
- [ ] `docs/observability.md` documenta tudo

## Riscos
- LangSmith vendor lock-in — Langfuse self-hosted como alternativa.
- Métricas detalhadas (por usuário) podem explodir cardinality. Restringir labels.
- CI lento? cachear `uv sync` / `pip install`.
