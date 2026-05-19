# Deploy

## Requisitos

- Python 3.12+
- PostgreSQL 14+
- Redis 7+
- Node.js 20+ (build do frontend)

## Variaveis de ambiente

Copie `backend/.env.example` para `backend/.env` e preencha:

```bash
cp backend/.env.example backend/.env
```

Todos os secrets **devem** ser alterados para producao. Valores default sao bloqueados via pydantic validator quando `AMBIENTE != desenvolvimento`.

## Build

```bash
# Frontend (static export)
cd frontend
npm ci
npm run build

# Instalar deps do backend
cd ../backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Migrations

```bash
cd backend
alembic upgrade head
```

## Worker (ARQ)

```bash
cd backend
arq app.worker.WorkerSettings
```

### Escalabilidade

Cada worker processa ate `ARQ_MAX_JOBS` (default 20) jobs simultaneos. Para N workers:

```bash
# 3 workers → 60 jobs simultaneos
arq app.worker.WorkerSettings &
arq app.worker.WorkerSettings &
arq app.worker.WorkerSettings &
```

Recomendado: 1 worker por 2 CPUs disponiveis.

Em producao, use um process manager (systemd, supervisor) para manter workers ativos.

NOTA: rate limit, credits e LLM bucket sao globais (Redis), entao scaling eh seguro.

### Workers em producao

- `arq_max_jobs` controla concorrencia por worker (default 20)
- `arq_job_timeout` = 2400s (40min), cobre workflow_distribuir_inlinks (30min) + margem
- `max_tries` = 3 com retry exponencial para erros transitorios
- Checkpointer e Redis pool sao aquecidos no startup (sem overhead no primeiro job)
- Health check: heartbeat a cada 30s via Redis (`arq:health-check`)

## Server (uvicorn)

```bash
cd backend
uvicorn app.main:application --host 0.0.0.0 --port 8000 --workers 4
```

## Checklist pre-deploy

- [ ] Todos os secrets configurados (`.env` completo)
- [ ] `AMBIENTE=producao` definido
- [ ] `arq_max_jobs` ajustado conforme memoria disponivel
- [ ] Migrations aplicadas (`alembic upgrade head`)
- [ ] Frontend buildado (`npm run build` no `frontend/`)
- [ ] Worker ARQ rodando
- [ ] CORS: `CORS_ORIGINS` configurado com dominios reais
- [ ] Cookies: `samesite=strict` ativo (automatico em producao)
- [ ] CSP: nonce-based headers ativos em producao
