# SEO SaaS IA

Plataforma multi-tenant de SEO assistida por IA. Gera artigos otimizados,
cria inlinks automáticos entre páginas de um blog, e distribui inlinks
reversos (encontra páginas que devem linkar para uma URL alvo).

## Stack

| Camada | Tecnologia |
|---|---|
| API | FastAPI 0.115+ (async) |
| Worker | arq + Redis 7 |
| Banco | PostgreSQL 16 + pgvector |
| Orquestração de agentes | LangGraph 0.4+ (checkpointer Postgres) |
| LLM | OpenAI / ZhipuAI (configurável; suporta OpenAI-compatible APIs) |
| Auth | JWT (acesso) + refresh token + MFA TOTP + Argon2id |
| Cache / rate limit | Redis (sliding window Lua, token bucket) |
| Frontend | Next.js 14 (estático, servido por nginx em prod) |
| Observabilidade | LangSmith (opcional), Sentry (opcional), Prometheus `/metrics`, JSON structured logs |

## Estrutura

```
backend/
├── app/
│   ├── agents/          # LangGraph workflows + agentes (pesquisador, redator, revisor, etc.)
│   │   ├── workflow.py              # gerar_artigo
│   │   ├── workflow_inlinks.py      # inlinks automaticos (pilar + candidatas)
│   │   ├── workflow_inlinks_reversos.py  # distribuir inlinks
│   │   ├── checkpointer.py          # AsyncConnectionPool singleton
│   │   └── inlinks/                 # subagentes (cleaner, enriquecedor, injector, etc.)
│   ├── core/            # cross-cutting (rate_limit, llm_guard, logging, scraper, embeddings)
│   ├── routers/         # FastAPI endpoints
│   ├── services/        # business logic (credito_service, auth_service, etc.)
│   ├── models/          # SQLAlchemy ORM
│   ├── schemas/         # Pydantic request/response
│   ├── main.py          # FastAPI app
│   └── worker.py        # arq WorkerSettings
├── tests/               # unit/, integration/, e2e/
├── pyproject.toml
└── .env.example         # template de variaveis (copie p/ .env)

frontend/
└── ...                  # Next.js 14

docs/
├── deploy.md            # como subir em producao
├── observability.md     # LangSmith, Sentry, /metrics, logs
├── Security/            # SDDs de seguranca
└── specs/               # SPECs de features e auditorias
```

## Rodar localmente

### Pré-requisitos

- Python 3.12+
- PostgreSQL 16+ (com extensão `vector`/pgvector)
- Redis 7+
- Node 18+ (para frontend)

### Setup backend

```bash
cd backend

# Dependencias
python3 -m pip install -e ".[dev]"

# Variaveis de ambiente
cp .env.example .env
# edite .env: gere SECRET_KEY/JWT_SECRET_KEY com `openssl rand -base64 32`
#             configure OPENAI_API_KEY (ou ZHIPUAI_API_KEY)

# Migrations
alembic upgrade head

# Seed de usuario de teste (opcional)
python3 scripts/seed_user.py
# user: teste@seosaas.com / senha: Teste@12345678

# Subir API
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Em outro terminal, subir worker
python3 -m arq app.worker.WorkerSettings
```

### Setup frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

## Comandos comuns

```bash
# Lint
python3 -m ruff check app/ --fix

# Types (gradual)
python3 -m mypy app/

# Tests
pytest -v
pytest --cov=app --cov-report=term-missing

# Build frontend p/ servir via backend (dev)
cd frontend && npm run build && cp -r out/* ../backend/static/

# Health probe
curl http://localhost:8000/health
curl http://localhost:8000/health/worker

# Métricas Prometheus
curl http://localhost:8000/metrics
```

## Documentação

- **[docs/deploy.md](docs/deploy.md)** — provisionar prod (Postgres, Redis, secrets, workers)
- **[docs/observability.md](docs/observability.md)** — LangSmith, Sentry, /metrics, logs JSON
- **[docs/Security/](docs/Security/)** — design docs de segurança (autenticação, threat modeling, etc.)
- **[docs/specs/](docs/specs/)** — registry SDD: specs vivas por capacidade (`ferramentas/`, `plataforma/`) + `auditorias/` (histórico). Comece por [docs/specs/README.md](docs/specs/README.md)
- **[backend/MYPY_BASELINE.md](backend/MYPY_BASELINE.md)** — baseline de tipos (gradual)

## Contribuição

1. Branch a partir de `main`.
2. Aplicar `ruff check --fix` antes do commit.
3. Garantir que `pytest` passa.
4. PR descrevendo: o que muda, por que, como testar.
5. Em mudanças de arquitetura, criar SPEC em `docs/specs/`.

## Ambiente: ferramentas pagas (API keys)

Você fornece suas próprias chaves no `.env`:

| Serviço | Var | Free tier |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | sem free tier permanente |
| ZhipuAI | `ZHIPUAI_API_KEY` | trial inicial |
| SerpAPI | `SERPAPI_KEY` | 100 buscas/mês |
| Google Trends | (sem chave; `pytrends` scraping) | livre, sem garantia |
| LangSmith | `LANGSMITH_API_KEY` | 5k traces/mês free |
| Sentry | `SENTRY_DSN` | 5k erros/mês free |

Se rodar 100% local sem custo, configure:
- `LLM_PROVIDER=openai` + `OPENAI_BASE_URL=http://localhost:11434/v1` (Ollama)
- Não setar `SERPAPI_KEY`, `LANGSMITH_API_KEY`, `SENTRY_DSN`

## Licença

Privado.
