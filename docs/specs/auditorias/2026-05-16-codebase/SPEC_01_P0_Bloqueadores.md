# SPEC 01 — P0 Bloqueadores de produção

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** backend (vários arquivos) · **Severidade:** CRÍTICA
**Cobre issues:** #1 (SyntaxError workflow.py), #2 (CSRF bypass), #3 (sleep síncrono), #4 (race créditos), #5 (default secrets), #6 (hash refresh fraco), #7 (max_jobs=3)

Tudo aqui precisa ser corrigido **antes** de qualquer cliente real. Cada item está reproduzível e tem fix bem-definido. Aplique nesta ordem.

---

## 1.1 — SyntaxError em `workflow.py` (gerar_artigo desligado)

### Problema
`backend/app/agents/workflow.py:1` começa com `2import asyncio` (literal). `python3 -c "import app.agents.workflow"` lança `SyntaxError`. Worker `executar_workflow` falha silenciosamente (try/except amplo). **A ferramenta "Gerar Artigo" está morta em produção.**

### Fix
Edit `workflow.py` linha 1: remover o `2`.
```python
# Antes:
2import asyncio
# Depois:
import asyncio
```

### Verificação
```bash
python3 -c "from app.agents.workflow import executar_workflow_completo; print('OK')"
```

---

## 1.2 — CSRF bypassado para cookie-based auth

### Problema
`core/middleware.py:165-179` — se `refresh_token` cookie está presente, a verificação CSRF é **pulada**. Isso inverte a finalidade do CSRF (proteger cookie-based auth). Combinado com `samesite=lax` (auth.py:34), permite ataques de top-level navigation.

### Fix
Reescrever `CSRFMiddleware.__call__`:

```python
if request.method in STATE_CHANGING_METHODS:
    # Bypass apenas para Bearer JWT (já é unforgeable; CSRF não se aplica)
    if request.headers.get("authorization", "").startswith("Bearer "):
        await self.app(scope, receive, send)
        return

    # Cookie-based auth: exigir CSRF token (header + double-submit)
    csrf_token = request.headers.get("x-csrf-token", "")
    csrf_cookie = request.cookies.get("csrf_token", "")
    if not csrf_token or csrf_token != csrf_cookie:
        response = JSONResponse(status_code=403, content={"detail": "CSRF token invalido"})
        await response(scope, receive, send)
        return

await self.app(scope, receive, send)
```

Adicionar set de cookie `csrf_token` (não-httponly, secure) no login junto com `refresh_token`. Frontend lê e envia no header `X-CSRF-Token`.

### Files
- `backend/app/core/middleware.py`
- `backend/app/routers/auth.py` (set csrf_token cookie no login/refresh)
- `frontend/src/lib/api.ts` (anexar X-CSRF-Token em requests)

### Verificação
```bash
# Sem CSRF token → 403
curl -X POST http://localhost:8000/api/ferramentas/gerar-artigo \
  -H "Cookie: refresh_token=valid_token" \
  -H "Content-Type: application/json" -d '{}'
# → {"detail":"CSRF token invalido"}
```

---

## 1.3 — `time.sleep()` e `httpx.get()` síncronos em handlers async

### Problema
- `services/auth_service.py:409-413` `_garantir_tempo` chama `time.sleep()` → bloqueia event loop ~1.5s por login.
- `core/seguranca.py:159` `_verificar_hibp` chama `httpx.get()` (sync) → bloqueia ~5s em cadastro/alterar senha.

Com 10 logins concorrentes, server fica congelado 15s. DoS trivial.

### Fix
Trocar para await:

```python
# auth_service.py
async def _garantir_tempo(inicio: float) -> None:
    import asyncio
    decorrido = time.time() - inicio
    if decorrido < settings.login_response_time:
        await asyncio.sleep(settings.login_response_time - decorrido)
```

Atualizar todos os callers (`login`, `recuperar_senha`, `login_mfa_verificar`) para `await _garantir_tempo(inicio)`.

```python
# seguranca.py
async def _verificar_hibp(senha: str) -> bool:
    import httpx
    sha1 = hashlib.sha1(senha.encode()).hexdigest().upper()
    prefixo, sufixo = sha1[:5], sha1[5:]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"https://api.pwnedpasswords.com/range/{prefixo}")
            resp.raise_for_status()
    except Exception:
        logger.warning("HIBP lookup falhou, pulando verificacao")
        return False
    for linha in resp.text.splitlines():
        hash_parte, _ = linha.split(":")
        if hash_parte == sufixo:
            return True
    return False
```

Atualizar `validar_forca_senha` para ser `async`. Atualizar callers (`cadastro`, `alterar_senha`).

### Files
- `backend/app/services/auth_service.py`
- `backend/app/core/seguranca.py`

### Verificação
```bash
# Concorrência: 10 logins paralelos com senha errada devem terminar em ~1.5s, não ~15s
ab -n 10 -c 10 -p /tmp/login.json -T application/json http://localhost:8000/api/auth/login
```

---

## 1.4 — Race condition de créditos (over-spend)

### Problema
- `routers/ferramentas.py:60` chama `verificar_saldo_suficiente` (read-only).
- `services/credito_service.py:52-75` `debitar_creditos` lê saldo em memória, decrementa, faz flush — sem `SELECT FOR UPDATE`.
- Múltiplos jobs paralelos do mesmo user passam o check, todos rodam, debitam ao final.

Usuário com 30 créditos enviando 20 requests paralelos → todos passam → saldo final = -370.

### Fix — pattern de reserva atômica

1. **No endpoint (`POST gerar-artigo` / `distribuir-inlinks`):** reservar créditos imediatamente via UPDATE atômico.

```python
# services/credito_service.py
async def reservar_creditos(db, usuario_id: str, quantidade: int) -> bool:
    """Reserva atomicamente. Retorna True se OK, False se saldo insuficiente."""
    stmt = (
        update(ContaCredito)
        .where(
            ContaCredito.usuario_id == usuario_id,
            (ContaCredito.saldo_plano + ContaCredito.saldo_extras) >= quantidade,
        )
        .values(saldo_reservado=ContaCredito.saldo_reservado + quantidade)
        .returning(ContaCredito.id)
    )
    r = await db.execute(stmt)
    return r.scalar_one_or_none() is not None
```

2. **No `finalizar_sucesso`:** confirmar reserva (mover de reservado para débito).

```python
async def confirmar_debito(db, usuario_id: str, quantidade_reservada: int, quantidade_final: int, ...):
    # liberta o que foi reservado a mais (se custo final < reservado)
    # debita o custo final
    ...
```

3. **No `finalizar_falha`:** liberar reserva (sem debitar).

```python
async def liberar_reserva(db, usuario_id: str, quantidade: int):
    await db.execute(
        update(ContaCredito)
        .where(ContaCredito.usuario_id == usuario_id)
        .values(saldo_reservado=ContaCredito.saldo_reservado - quantidade)
    )
```

4. **Adicionar coluna** `saldo_reservado INT NOT NULL DEFAULT 0` em `contas_creditos`. Property `saldo_disponivel = saldo_plano + saldo_extras - saldo_reservado`.

5. **Adicionar UNIQUE constraint em (usuario_id) em conta_creditos** + `INSERT ... ON CONFLICT DO NOTHING` em `criar_conta_credito` para evitar duplicação na criação concorrente (issue #34).

### Files
- `backend/app/models/conta_credito.py` (nova coluna)
- `backend/app/services/credito_service.py`
- `backend/app/routers/ferramentas.py`, `ferramentas_inlinks.py`, `ferramentas_inlinks_reversos.py`
- `backend/app/services/ferramenta_service.py` (`finalizar_sucesso`, `finalizar_falha`)
- Migration alembic

### Verificação
- Teste: usuário com 30 créditos envia 5 jobs paralelos custando 25 cada. **Esperado:** 1 job passa, 4 retornam 402 imediatamente.
- Teste: usuário com 30 créditos envia 1 job que falha — saldo volta a 30.

---

## 1.5 — Default secrets que permitem login se .env faltar

### Problema
`config.py:21-27` — `secret_key`, `jwt_secret_key`, `encryption_key` têm defaults conhecidos. Se `.env` ausente em produção (deploy mal configurado), app inicia com secrets de domínio público.

### Fix
Validar no `Settings.__init__` / pydantic validator:

```python
from pydantic import field_validator

class Settings(BaseSettings):
    # ... campos existentes ...

    @field_validator("secret_key", "jwt_secret_key", "encryption_key")
    @classmethod
    def _impedir_default_em_prod(cls, v: str, info) -> str:
        defaults_proibidos = {
            "chave-secreta-padrao-mudar-em-producao",
            "jwt-secreto-padrao-mudar-em-producao",
            "chave-encriptacao-padrao-32bytes!!",
        }
        if v in defaults_proibidos:
            ambiente = info.data.get("ambiente", "desenvolvimento")
            if ambiente != "desenvolvimento":
                raise ValueError(
                    f"Secret '{info.field_name}' usa valor default. "
                    f"Defina via .env antes de subir em ambiente={ambiente}."
                )
        return v
```

Plus: adicionar validação de tamanho (`jwt_secret_key` ≥ 32 bytes, `encryption_key` ≥ 32 bytes para Fernet).

### Verificação
```bash
# .env vazio + ambiente=producao:
AMBIENTE=producao python3 -c "from app.config import settings"
# Esperado: pydantic.ValidationError
```

---

## 1.6 — Refresh token hash = SHA256 sem salt

### Problema
`core/seguranca.py:79-83` — `hash_refresh_token = sha256(token)`. Tokens são unguessable (`secrets.token_urlsafe(48)`), mas qualquer compromisso de DB (read-only injection, backup leak) expõe diretamente. Sem HMAC ou Argon2.

### Fix
HMAC-SHA256 com `secret_key`:

```python
import hmac
def hash_refresh_token(token: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()
```

Plus: migration de tokens existentes — emitir novo refresh no próximo `/refresh` para cada usuário ativo (lazy migration sem ruptura).

### Verificação
- Hash anterior `sha256("token")` → 64 hex chars
- Hash novo `hmac("token", secret)` → 64 hex chars; valores diferentes.
- Login normal funciona.

---

## 1.7 — `arq max_jobs=3` muito baixo

### Problema
`config.py:76` — só 3 workflows simultâneos no processo todo. Saas multi-tenant trava com >3 usuários ativos.

### Fix
- Subir para `arq_max_jobs=20` (config.py).
- Documentar escalabilidade: rodar N workers (`arq app.worker.WorkerSettings` × N) para `N × 20` concorrência total.
- Adicionar variável `ARQ_MAX_JOBS` no `.env` para tunar sem code change.

### Files
- `backend/app/config.py`
- `.env.example` (criar com `ARQ_MAX_JOBS=20`)
- `docs/deploy.md` (criar com instruções)

### Verificação
Após restart: `ps aux | grep arq` → confirmar startup ok. Submeter 10 jobs paralelos, todos rodam.

---

## Ordem de aplicação

1. **1.1** (SyntaxError) — 1 min, desbloqueia testes
2. **1.7** (max_jobs) — 1 min, libera concorrência mínima
3. **1.5** (default secrets) — 5 min
4. **1.3** (sleep async) — 10 min
5. **1.6** (refresh HMAC) — 10 min + lazy migration
6. **1.2** (CSRF) — 30 min (backend + frontend)
7. **1.4** (race créditos) — 60 min (migration + refactor)

Total: ~2h de trabalho.

## Não-objetivos
- Multi-tenant rate limit Redis-backed → SPEC 04
- Cancel real no ARQ → SPEC 05
- Observability → SPEC 07

## Critério de pronto
- [ ] `python3 -c "import app.agents.workflow"` sem erro
- [ ] 10 logins paralelos terminam em <2s
- [ ] CSRF token exigido em cookie-auth state-changing
- [ ] Reserva atômica testada com saldo limite
- [ ] App falha se secrets default em prod
- [ ] Refresh tokens novos usam HMAC
- [ ] `arq_max_jobs=20`
