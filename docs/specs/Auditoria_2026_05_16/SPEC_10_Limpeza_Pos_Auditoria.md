# SPEC 10 — Limpeza pós-auditoria

**Status:** a aplicar · **Escopo:** múltiplos arquivos (refactor seguro) · **Severidade:** Baixa (dívida técnica)
**Cobre:** órfãs deixadas pelos SPECs 09, 44 violações ruff residuais, `.env.example` defasado, code morto. Sem mudança de comportamento esperada.

**Depende de:** SPECs 01-09 aplicadas.

Tudo aqui é mecânico e reversível. Pode ser 1 PR único ou 5 commits temáticos.

---

## 10.1 — Remover config órfãs do `_llm_semaphore`

SPEC 09 §9.8 removeu o semáforo process-local mas os 3 settings ficaram em config.py sem uso.

**Arquivo:** `backend/app/config.py:87-89`

```python
# REMOVER as 3 linhas:
llm_global_concurrency: int = 3
llm_per_user_concurrency: int = 1
llm_rate_limit_delay: float = 2.0
```

Buscar referências antes de remover:
```bash
grep -rn "llm_global_concurrency\|llm_per_user_concurrency\|llm_rate_limit_delay" backend/
```
Esperado: nenhuma após SPEC 09.

---

## 10.2 — Remover funções não-retry redundantes em `llm_guard.py`

`chamada_llm_segura` e `chamada_llm_mensagem_segura` (linhas 93-99 e 132-138) são chamadas **apenas** pelas variantes `_com_retry` do mesmo arquivo. Não há caller externo.

**Arquivo:** `backend/app/core/llm_guard.py`

**Fix:** inline as funções no caller (ou marcar como `_privadas` com underscore). Simplifica leitura:

```python
# Antes:
async def chamada_llm_segura(chain, input_data, usuario_id: str):
    model = getattr(getattr(chain, "llm", chain), "model_name", "default")
    await _aguardar_token_llm(usuario_id, model)
    return await chain.ainvoke(input_data)

async def chamada_llm_com_retry(chain, input_data, usuario_id: str):
    for tentativa in range(MAX_RETRIES + 1):
        try:
            return await chamada_llm_segura(chain, input_data, usuario_id)
        ...

# Depois:
async def chamada_llm_com_retry(chain, input_data, usuario_id: str):
    model = getattr(getattr(chain, "llm", chain), "model_name", "default")
    for tentativa in range(MAX_RETRIES + 1):
        try:
            await _aguardar_token_llm(usuario_id, model)
            return await chain.ainvoke(input_data)
        except ...
```

Mesma simplificação em `chamada_llm_mensagem_com_retry`.

Mantém o `_aguardar_token_llm` helper (usado por ambos).

---

## 10.3 — Atualizar `.env.example`

Arquivo tem **17 vars** mas `Settings` define **55+ campos**. Falta documentar todas as novas:

- LLM provider/model (multi-model)
- LangSmith, Sentry, metrics_allowlist
- HIBP, CORS
- Pesquisa web, Imagem (Pollinations/OpenAI)
- ZhipuAI key
- Various LLM model overrides

**Fix:** reescrever `backend/.env.example` cobrindo TODOS os campos com defaults + comentários:

```bash
# ============= AMBIENTE =============
AMBIENTE=desenvolvimento  # desenvolvimento | producao | teste
LOG_LEVEL=INFO

# ============= DATABASE =============
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/seo_saas
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/seo_saas_test

# ============= SECRETS (gerar com `openssl rand -base64 32`) =============
SECRET_KEY=
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=604800
ENCRYPTION_KEY=  # 32 bytes; usado p/ Fernet (criptografia TOTP)

# ============= URLs =============
FRONTEND_URL=http://localhost:3000
APP_URL=http://localhost:8000
CORS_ORIGINS=["http://localhost:3000"]

# ============= REDIS =============
REDIS_URL=redis://localhost:6379/0

# ============= LLM PROVIDER =============
LLM_PROVIDER=openai  # openai | zhipuai
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096
OPENAI_API_KEY=
ZHIPUAI_API_KEY=

# Override de modelo por agente (default: usa LLM_MODEL)
INSERIDOR_LLM_MODEL=gpt-4.1
RERANKER_LLM_MODEL=gpt-4.1
REVISOR_LLM_MODEL=gpt-4.1
ENRIQUECEDOR_LLM_MODEL=gpt-4.1

# Embeddings
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1024

# ============= PESQUISA WEB =============
SERPAPI_KEY=
GOOGLE_TRENDS_ENABLED=false

# ============= GERACAO DE IMAGEM =============
IMAGEM_MODEL=glm-image

# ============= WORKFLOW =============
WORKFLOW_TIMEOUT_SEGUNDOS=600
WORKFLOW_MAX_REVISOES=3
WORKFLOW_MAX_FEEDBACK=3
WORKFLOW_DISTRIBUIR_INLINKS_TIMEOUT=1800

# ============= ARQ WORKERS =============
ARQ_MAX_JOBS=20
ARQ_JOB_TIMEOUT=2400

# ============= RATE LIMITS =============
RATE_LIMIT_LOGIN_MAX=5
RATE_LIMIT_LOGIN_WINDOW=900
RATE_LIMIT_GERAL_MAX=100
RATE_LIMIT_GERAL_WINDOW=60
RATE_LIMIT_FORGOT_MAX=3
RATE_LIMIT_FORGOT_WINDOW=3600
RATE_LIMIT_RESET_MAX=5
RATE_LIMIT_RESET_WINDOW=60
RATE_LIMIT_MFA_MAX=10
RATE_LIMIT_MFA_WINDOW=900
LOGIN_RESPONSE_TIME=1.5

# ============= SEGURANCA =============
HIBP_FAIL_MODE=open  # open | closed | queue
PESQUISA_CACHE_TTL_DAYS=7

# ============= OBSERVABILITY =============
# LangSmith (free tier 5k traces/mes)
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=seo-saas
LANGSMITH_ENDPOINT=https://api.smith.langchain.com

# Sentry (free tier 5k erros/mes)
SENTRY_DSN=

# Prometheus /metrics endpoint (vazio = aberto; preencha p/ allowlist)
METRICS_ALLOWLIST=[]
```

---

## 10.4 — Resolver 44 violações ruff

Quebrar por categoria:

### 10.4.1 — Auto-fixáveis (7 itens, 20 com `--unsafe-fixes`)

```bash
cd backend && python3 -m ruff check app/ --fix
```

Resolve:
- 3 F401 (unused imports) — `InlinkInserido`, `_categoria_match`, `settings` em workflow_events
- 4 I001 (unsorted imports)

### 10.4.2 — RUF001 unicode ambíguo (3 itens)

Caracteres LONG-S `ſ`, EN-DASH `–` parecem `f` e `-`. Provavelmente cole errado.

**Arquivos:**
- `workflow_inlinks_reversos.py:94` — `r"[^a-zA-ZÀ-ſ]"` → `r"[^a-zA-ZÀ-ÿ]"`
- `scraper.py:315` — buscar `–` e trocar por `-` ou `–` explícito

Verificar caso a caso (alguns podem ser intencionais; UTF-8 acentos português).

### 10.4.3 — F841 unused variables (3 itens)

- `workflow_inlinks_reversos.py:756` — `rel_attr = estado.get("rel_attr", ...)` mas nunca usado (deveria ser passado adiante)
- Verificar contexto antes de remover; pode ser bug (esquecemos de propagar `rel_attr`).

### 10.4.4 — N818 exceções sem suffix "Error"

`app/core/excecoes.py:100,104`:
- `ErroTransitorio` → `ErroTransitorio` (PT-BR consistente; **ignorar via config**) OR renomear para `ErroTransitorioError`

Decisão: convenção PT-BR atual usa `Erro*`. Manter e adicionar `N818` ao `ignore` do ruff:

```toml
[tool.ruff.lint]
ignore = ["E501", "B008", "N818"]
```

### 10.4.5 — SIM/B simplificações (~12 itens)

- SIM105 (suppressible-exception): trocar try/except/pass por `contextlib.suppress`.
- SIM108: collapse if/else em expressão ternária.
- B905: `zip(..., strict=True)` para evitar truncate silencioso.
- E712: `== True/False` → `is True/False` ou inverter.

Aplicar caso a caso.

### 10.4.6 — Verificar resultado final

```bash
python3 -m ruff check app/
# esperado: All checks passed!
```

---

## 10.5 — Setup `mypy` strict + CI

`pyproject.toml` declara `mypy>=1.14.0` em dev mas:
1. Não está instalado no env atual (`No module named mypy`).
2. Nunca foi rodado ⇒ violações não conhecidas.

**Fix:**

```bash
pip install mypy
python3 -m mypy app/ --strict --install-types --non-interactive 2>&1 | tee /tmp/mypy.log
```

Esperado: muitas violações iniciais. Aplicar fixes incrementalmente:
- Adicionar type hints onde faltam
- `# type: ignore[<code>]` apenas com comentário justificando

CI (GitHub Actions):
```yaml
- run: pip install -e ".[dev]"
- run: ruff check app/
- run: mypy app/ --strict
- run: pytest -v
```

Se mypy strict for muito viral, começar com gradual:
```toml
[tool.mypy]
python_version = "3.12"
strict_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
# strict = true  # ativar quando todos os módulos passarem
```

---

## 10.6 — Conferir SPEC 08 §8.7 (file split)

Arquivos ainda gigantes:
- `workflow_inlinks_reversos.py` — 1153 LOC
- `workflow_inlinks.py` — 891 LOC
- `inseridor.py` — 737 LOC

SPEC 08 §8.7 propôs split em subdiretório `agents/distribuir_inlinks/`. **Não foi aplicado.** Não é bloqueante mas:
- Time de revisão de PRs sofre
- Mypy demora mais por arquivo grande
- Difícil navegar

**Recomendação:** deixar para sprint dedicado de refactor. Não bloquear esta SPEC.

---

## 10.7 — Documentação: README e deploy.md

Atualizar:

### `README.md` (raiz do repo)

Adicionar seções:
- Arquitetura (backend FastAPI + worker ARQ + checkpointer LangGraph)
- Como rodar localmente (PostgreSQL + Redis + uvicorn + arq)
- Stack de dependências externas (OpenAI/ZhipuAI/SerpAPI/Supabase)
- Como contribuir

### `docs/deploy.md` (criar se não existir)

Cobrir:
- Provisionamento Supabase + Redis Render
- Vars de ambiente obrigatórias em prod (referenciar `.env.example`)
- Validação de secrets (não-default em prod)
- Configuração nginx para servir frontend
- Escalabilidade: N workers ARQ + max_jobs

### `docs/observability.md` (criar)

- Como ativar LangSmith (`LANGSMITH_API_KEY`)
- Como ativar Sentry (`SENTRY_DSN`)
- Endpoint `/metrics` (Prometheus)
- Endpoint `/health/worker` (heartbeat)
- Estrutura dos logs JSON (event_type, etc.)

---

## 10.8 — Limpar tasks órfãs de teste em `tests/`

`tests/` tem:
- `test_auth.py`, `test_e2e_*.py`, `test_inlinks_injector.py`, `test_scraper.py` no nível raiz
- `unit/`, `integration/`, `e2e/` directories

Sem padrão claro. Reorganizar:
```
tests/
├── conftest.py
├── unit/
│   ├── test_auth_service.py
│   ├── test_credito_service.py
│   ├── test_seguranca.py
│   ├── test_rate_limit.py
│   └── test_embeddings.py
├── integration/
│   ├── test_workflow_gerar_artigo.py
│   ├── test_workflow_inlinks.py
│   ├── test_workflow_distribuir.py
│   ├── test_credito_race.py
│   └── test_cancelamento.py
└── e2e/
    └── test_full_user_flow.py
```

Mover ou deletar testes obsoletos. Rodar coverage:
```bash
pytest --cov=app --cov-report=term-missing
```

Target: 70%+ em `services/`, 60%+ em `core/`, 50%+ em `agents/`.

---

## Ordem de aplicação (~3-4h total)

| Etapa | Item | Tempo |
|---|---|---|
| 1 | 10.1 — Remover config órfãs | 5 min |
| 2 | 10.4.1 — `ruff --fix` auto | 5 min |
| 3 | 10.4.2-10.4.5 — Manuais ruff | 30 min |
| 4 | 10.2 — Simplificar llm_guard | 15 min |
| 5 | 10.3 — Reescrever .env.example | 20 min |
| 6 | 10.5 — Setup mypy gradual | 30 min |
| 7 | 10.8 — Reorganizar tests + coverage | 60 min |
| 8 | 10.7 — Docs (README, deploy, observability) | 60-90 min |
| — | 10.6 — File split (defer) | — |

---

## Critério de pronto

- [ ] `ruff check app/` → 0 erros
- [ ] `mypy app/` → 0 erros (modo gradual) ou < 50 (modo strict)
- [ ] `.env.example` reflete todos os 55+ campos de `Settings`
- [ ] `llm_global_concurrency` etc. removidos de config.py
- [ ] `chamada_llm_segura` simplificada (inline ou prefixo `_`)
- [ ] `tests/` reorganizado, coverage > 50% global
- [ ] `README.md` + `docs/deploy.md` + `docs/observability.md` atualizados
- [ ] CI rodando `ruff` + `mypy` + `pytest` em cada PR

---

## Riscos

- Remover `chamada_llm_segura` quebra se houver caller externo (ex: scripts em `scripts/`). Buscar antes.
- `mypy strict` pode expor centenas de erros — começar gradual.
- Reorganizar tests pode quebrar referências em `conftest.py`. Rodar suite após cada movimentação.
- Atualizar `.env.example` não toca `.env` ativo — sem risco runtime.

## Não-objetivos

- File split de workflow_*.py (deferido)
- Refatorar LCEL agents (SPEC 06 §6.6, deferido)
- Migração de hash legacy SHA256 (SPEC 02 §2.1, agendada para 2026-07-15)
