# SPEC — CWV Correções Pós-Validação (2026-05-27)

**Status:** fixes já aplicados · documentação para code review e referência
**Escopo:** registrar as 9 correções em testes unitários pré-existentes que falhavam; registrar implementação da SPEC #15 (modelos LLM dedicados)
**Audiência:** code review, manutenção, rastreabilidade

## 1. Contexto

Após implementação completa de todas as specs V1.2 (#11-#15), a suite de testes unitários apresentava **9 falhas** e **4 erros** que impediam um build limpo (`130/130` target). Todas eram preexistentes (não introduzidas pelas specs V1.2), mas bloqueavam o critério de qualidade.

Este documento registra cada correção com causa raiz, fix aplicado e como prevenir recorrência.

## 2. Resumo das correções

| # | Tipo | Teste | Sintoma | Causa raiz |
|---|---|---|---|---|
| 1 | FAIL | `test_liberar_reserva_clamps_negative` | `TypeError: object MagicMock can't be used in 'await'` | `mock_db.flush()` não era `AsyncMock` |
| 2 | FAIL | `test_rate_limit_passes_under_limit` | `AttributeError: module has no attribute 'get_redis_commands'` | Patch em módulo errado (função importa localmente) |
| 3 | FAIL | `test_rate_limit_blocks_at_limit` | Idem #2 | Idem #2 |
| 4 | FAIL | `test_rate_limit_fail_open_on_redis_error` | Idem #2 | Idem #2 |
| 5 | FAIL | `test_get_client_ip_v4` | `ImportError: cannot import name 'ASGIReceive'` | `ASGIReceive` removido em starlette >= 0.40 |
| 6 | ERROR | `test_buscar_analise_anterior_encontrada` | `fixture 'db_session' not found` | Teste de integração classificado como unitário |
| 7 | ERROR | `test_buscar_analise_anterior_nao_encontrada` | Idem #6 | Idem #6 |
| 8 | ERROR | `test_comparar_com_anterior_sucesso` | `fixture 'mock_user' not found` + `usuario_id` mismatch | Idem #6 + IDs aleatórios distintos |
| 9 | ERROR | `test_comparar_com_anterior_sem_anterior` | Idem #8 | Idem #6 |

## 3. Detalhamento

### 3.1 Bug #1 — `mock_db.flush()` síncrono em teste async

**Arquivo:** `backend/tests/unit/test_credito_service.py:48`

**Sintoma:**
```
TypeError: object MagicMock can't be used in 'await' expression
```

**Causa raiz:** `liberar_reserva()` faz `await db.flush()`. O mock criava `MagicMock()` para `db`, que gera um `MagicMock` síncrono para `.flush()`.

**Fix:**
```python
mock_db = MagicMock()
mock_db.flush = AsyncMock()  # <-- adicionado
```

**Prevenção:** Ao mockar objetos com métodos async, sempre usar `AsyncMock` para cada método awaitable. Alternativa: usar `spec=AsyncSession` para que o mock saiba quais métodos são async.

---

### 3.2 Bugs #2-4 — Patch em módulo errado para import local

**Arquivo:** `backend/tests/unit/test_rate_limit.py:9,18,26`

**Sintoma:**
```
AttributeError: <module 'app.core.rate_limit'> does not have the attribute 'get_redis_commands'
```

**Causa raiz:** `check_rate_limit_redis()` importa `get_redis_commands` localmente dentro do corpo da função:
```python
async def check_rate_limit_redis(...):
    from app.core.redis_pool import get_redis_commands  # import local
```

O teste fazia `patch("app.core.rate_limit.get_redis_commands", ...)` — o atributo não existe no módulo `rate_limit` porque a importação é lazy/diferida.

**Fix:** Patch na fonte:
```python
# Antes (quebrado):
patch("app.core.rate_limit.get_redis_commands", return_value=mock_redis)

# Depois (funcional):
patch("app.core.redis_pool.get_redis_commands", new_callable=AsyncMock, return_value=mock_redis)
```

Também adicionado `new_callable=AsyncMock` (a função é um `async def`) e `mock_redis.eval = AsyncMock(return_value=1)` no teste de "passes under limit" (antes dependia do default `MagicMock` que não é awaitable).

**Prevenção:** Quando a função-alvo faz `from X import Y` no corpo, patch em `X.Y`, não em `modulo_que_chama.Y`. Regra geral: patch sempre no **último módulo que define o nome**.

---

### 3.3 Bug #5 — `ASGIReceive` removido do starlette

**Arquivo:** `backend/tests/unit/test_seguranca.py:87`

**Sintoma:**
```
ImportError: cannot import name 'ASGIReceive' from 'starlette.types'
```

**Causa raiz:** Starlette >= 0.40 moveu `ASGIReceive` para `starlette.types` com reexportação condicional. Em versões mais novas (>= 0.46), o nome não está mais disponível.

**Fix:** Remover import não utilizado:
```python
# Antes:
from starlette.types import ASGIReceive, Scope

# Depois:
# (removido — nem ASGIReceive nem Scope eram usados no teste)
```

**Prevenção:** Pinar versões de deps principais (starlette, fastapi) no `pyproject.toml` ou revisar imports após upgrades.

---

### 3.4 Bugs #6-7 — Fixtures `db_session` inexistentes

**Arquivo:** `backend/tests/unit/test_comparador_cwv.py:12,94`

**Sintoma:**
```
ERROR fixture 'db_session' not found
```

**Causa raiz:** Os testes `test_buscar_analise_anterior_*` faziam queries SQL reais via `db_session.execute("INSERT INTO ...")`. A fixture `db_session` só existe no `conftest.py` quando `enable_db_access` está ativo (que por sua vez requer PostgreSQL rodando em `localhost:5433`).

Esses testes são de **integração** classificados incorretamente como **unitários**.

**Fix:** Reescritos como testes unitários puros com mocks:
```python
mock_session = MagicMock()
mock_result = MagicMock()
mock_result.scalar_one_or_none.return_value = mock_analise
mock_session.execute = AsyncMock(return_value=mock_result)

resultado = await buscar_analise_anterior(mock_session, url, cliente_id, antes_de)
```

**Prevenção:** Testes que usam `db_session`, `test_session`, `test_db` devem ficar em `tests/integration/`, não em `tests/unit/`. Revisar `conftest.py` para documentar quais fixtures requerem DB.

---

### 3.5 Bugs #8-9 — Fixtures inexistentes + `usuario_id` mismatch

**Arquivo:** `backend/tests/unit/test_comparador_cwv.py:111,223`

**Sintoma:**
```
ERROR fixture 'mock_user' not found
HTTPException: 404: Analise nao encontrada (mesmo com mock configurado)
```

**Causa raiz (dupla):**

1. **Fixtures:** `test_comparar_com_anterior_*` usavam `db_session` e `mock_user` que não existem. Mesma raiz dos bugs #6-7.

2. **usuario_id mismatch:** Mesmo após corrigir os mocks, `_make_mock_analise()` gerava `usuario_id` aleatório via `str(uuid4())` e `mock_user.id = uuid4()` gerava outro UUID diferente. A checagem `str(analise_atual.usuario_id) != str(usuario.id)` sempre falhava, causando HTTP 404.

3. **dias_decorridos off-by-one:** `datetime.now(timezone.utc) - timedelta(days=7)` vs `datetime.now(timezone.utc)` pode resultar em 6.99 dias → `int()` arredonda para 6.

**Fix completo:**
```python
user_id = uuid4()  # ID compartilhado

mock_analise_atual = _make_mock_analise(
    id=UUID(analise_atual_id),
    usuario_id=str(user_id),       # <-- mesmo ID
    criado_em=datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc),  # fixo
    ...
)
mock_analise_anterior = _make_mock_analise(
    id=UUID(analise_anterior_id),
    usuario_id=str(user_id),       # <-- mesmo ID
    criado_em=datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),  # 7 dias exatos
    ...
)

mock_user = MagicMock()
mock_user.id = user_id             # <-- mesmo ID
```

Patch target corrigido de `app.routers.ferramentas_cwv.*` para `app.services.cwv_persistencia.*` (mesma causa do bug #2 — import local no corpo da função).

**Prevenção:**
- Em testes com mock de usuário e dados relacionados, usar um ID fixo compartilhado.
- Para assertions de tempo, usar timestamps fixos (não `datetime.now()`).
- Documentar que `comparar_com_anterior` faz imports locais no corpo da função.

---

## 4. Implementação da SPEC #15 (Modelos LLM Dedicados)

Implementada em paralelo às correções. Resumo:

| Arquivo | Mudança |
|---|---|
| `backend/app/config.py` | +4 campos: `cwv_analisador_llm_model`, `cwv_analisador_llm_temperature`, `cwv_pesquisador_llm_model`, `cwv_pesquisador_llm_temperature` |
| `backend/app/agents/cwv/analisador.py` | `__init__` override `self.llm` → `gpt-4o-mini` temp=0.1 |
| `backend/app/agents/cwv/pesquisador.py` | `__init__` override `self.llm` → `gpt-4.1` temp=0.4, reaplica `bind_tools` |
| `backend/.env.example` | +6 linhas documentando as 4 chaves |
| `backend/tests/unit/test_cwv_analisador.py` | +3 testes (override, defaults, no-override) |
| `backend/tests/unit/test_cwv_pesquisador.py` | +3 testes (override, defaults, no-override) |

## 5. Resultado final

| Métrica | Antes | Depois |
|---|---|---|
| Unit tests passing | 121/130 (9 falhas) | **130/130** |
| CWV tests | 60/60 | **60/60** (sem regressão) |
| Erros de fixture | 4 | **0** |
| Specs V1.2 implementadas | 4/5 (#11-#14) | **5/5 (#11-#15)** |

## 6. Lições aprendidas

1. **`await` em mocks:** Sempre usar `AsyncMock` para métodos que são awaitados. `MagicMock().flush()` não é awaitable.
2. **Patch targets:** Patch no módulo que **define** o nome, não no módulo que **importa**. Quando há import local (`from X import Y` dentro de função), patch em `X.Y`.
3. **Separação unit/integration:** Testes com queries SQL reais não são unitários. Colocar em `tests/integration/` e usar `enable_db_access`.
4. **IDs em testes mockados:** Usar UUID fixos/compartilhados quando mock_user precisa bater com mock_data. Nunca gerar IDs aleatórios independentes para objetos que serão comparados.
5. **Timestamps em assertions:** Usar `datetime()` fixo para assertions de `dias_decorridos` — `datetime.now()` gera diferenças de milissegundos que afetam `int(total_seconds() / 86400)`.
6. **Imports não utilizados:** Remover imports de tipos que não são usados (especialmente reexports que mudam entre versões de deps).
