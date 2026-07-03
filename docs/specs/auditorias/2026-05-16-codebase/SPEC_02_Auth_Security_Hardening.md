# SPEC 02 — Hardening de Auth & Security headers

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** backend (auth, seguranca, middleware) + frontend (CSP nonces) · **Severidade:** Alta
**Cobre issues:** #20 (SHA256 legacy), #21 (HIBP fail-open), #22 (CSP unsafe-*), #28 (cookie secure dev), #38 (route catchall), #48 (consolidar LLM em LangChain)

**Depende de:** SPEC_01 aplicada (secrets validados, CSRF correto).

---

## 2.1 — Migration de hashes SHA256 legacy (com cutoff)

### Problema
`core/seguranca.py:41-43` aceita SHA256 puro de senha como fallback. SHA256(senha) é reversível por wordlist em segundos. Hoje qualquer leak de hashes legacy = leak de senhas.

### Fix
1. Logar telemetria de uso: cada login que cair em `verificar_hash_legado`, increment counter Prometheus/log.
2. Hard cutoff em 60 dias: após data X, recusar login e enviar email de reset forçado.
3. Frontend: tela "senha precisa ser atualizada por motivos de segurança, redefina via link enviado".

```python
# core/seguranca.py
import datetime
LEGACY_HASH_CUTOFF = datetime.datetime(2026, 7, 15, tzinfo=datetime.UTC)

def verificar_hash_legado(senha: str, senha_hash: str) -> bool:
    if datetime.datetime.now(datetime.UTC) >= LEGACY_HASH_CUTOFF:
        return False  # cutoff: força reset
    legacy_hash = hashlib.sha256(senha.encode()).hexdigest()
    return secrets.compare_digest(legacy_hash, senha_hash)
```

4. Job de background (scheduler.py): enviar email proativo para usuários com hash legacy 14 dias antes do cutoff.

### Files
- `backend/app/core/seguranca.py`
- `backend/app/scheduler.py` (job de notificação)
- `backend/app/services/auth_service.py` (mensagem específica no erro)

### Verificação
- Antes do cutoff: login com hash legacy funciona (e migra silenciosamente).
- Após cutoff: login retorna 401 com mensagem "redefina sua senha".

---

## 2.2 — HIBP fail-closed (configurable)

### Problema
`core/seguranca.py:158-173` — se HIBP API down, retorna `False` (senha não comprometida). Atacante com DNS hijack pode forçar aceitar senhas conhecidas.

### Fix
Política configurável:

```python
# config.py
hibp_fail_mode: str = "open"  # "open" | "closed" | "queue"

# seguranca.py
async def _verificar_hibp(senha: str) -> bool | None:
    """Retorna True (comprometida), False (OK), None (HIBP indisponível)."""
    ...
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(...)
            resp.raise_for_status()
    except Exception:
        logger.warning("HIBP indisponivel")
        return None  # incerto

    return any(linha.startswith(sufixo) for linha in resp.text.splitlines())

async def validar_forca_senha(senha: str) -> tuple[bool, str]:
    # ... validações basicas ...
    hibp = await _verificar_hibp(senha)
    if hibp is True:
        return False, "Senha comprometida em vazamentos conhecidos"
    if hibp is None:
        if settings.hibp_fail_mode == "closed":
            return False, "Servico de verificacao indisponivel, tente novamente"
        if settings.hibp_fail_mode == "queue":
            # marcar usuario para revalidacao em background
            ...
    return True, ""
```

Recomendado: prod usa `fail_mode="queue"` — aceita mas revalida em background e força reset se comprometida.

### Files
- `backend/app/config.py`
- `backend/app/core/seguranca.py`
- `backend/app/scheduler.py` (job de revalidação HIBP)

---

## 2.3 — CSP com nonces para Next.js (remover unsafe-*)

### Problema
`core/middleware.py:113` — CSP atual tem `script-src 'self' 'unsafe-inline' 'unsafe-eval'`. Abre XSS amplamente.

### Fix
1. Gerar nonce por request no middleware:

```python
async def __call__(self, scope, receive, send):
    if scope["type"] != "http":
        await self.app(scope, receive, send); return
    nonce = secrets.token_urlsafe(16)
    # injetar no scope para handlers usarem
    scope.setdefault("state", {})["csp_nonce"] = nonce

    async def send_with_headers(message):
        if message["type"] == "http.response.start":
            csp = (
                f"frame-ancestors 'none'; "
                f"default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic'; "
                f"style-src 'self' 'nonce-{nonce}'; "
                ...
            ).encode()
            headers.append((b"content-security-policy", csp))
        await send(message)
    ...
```

2. Frontend Next.js: configurar `experimental.cspNonce` (Next 14+) ou middleware Next.js que lê `x-csp-nonce` e injeta em `<script nonce="...">`.

3. Fase intermediária: report-only para descobrir violations:
```python
headers.append((b"content-security-policy-report-only", csp))
```

### Files
- `backend/app/core/middleware.py`
- `frontend/next.config.js`
- `frontend/src/middleware.ts` (criar; lê nonce do header)

### Verificação
- DevTools console sem CSP violations
- Tentar inserir `<script>alert(1)</script>` em campo de input → bloqueado

---

## 2.4 — Cookie `secure` env-aware

### Problema
`routers/auth.py:33` — `secure: True` fixo. Em desenvolvimento local (http), browser silenciosamente descarta o cookie. Atrapalha dev e mascara bugs.

### Fix
```python
# routers/auth.py
from app.config import settings

COOKIE_CONFIG = {
    "httponly": True,
    "secure": settings.ambiente != "desenvolvimento",
    "samesite": "strict",  # strict é melhor que lax para refresh tokens
    "path": "/",
    "max_age": 604800,
}
```

Plus: trocar `samesite="lax"` para `"strict"`. Refresh tokens não precisam funcionar em top-level navigation.

### Files
- `backend/app/routers/auth.py`

### Verificação
- Dev local: cookie aparece em DevTools com `secure=false`
- Prod: `secure=true; SameSite=Strict`

---

## 2.5 — TOTP valid_window

### Problema
`core/seguranca.py:100` — `valid_window=1` permite código atual + anterior + próximo (90s window). Padrão TOTP é 30s. Replay attack mais fácil.

### Fix
```python
def verificar_totp(segredo: str, codigo: str) -> bool:
    totp = pyotp.TOTP(segredo)
    # window=0: apenas o código atual (30s)
    return totp.verify(codigo, valid_window=0)
```

Plus: marcar último código usado em `mfa_dispositivos.ultimo_codigo` para prevenir replay dentro da janela:
```python
ALTER TABLE mfa_dispositivos ADD COLUMN ultimo_codigo VARCHAR(6) NULL;
```

```python
if dispositivo.ultimo_codigo == codigo:
    return False  # replay
dispositivo.ultimo_codigo = codigo
```

### Files
- `backend/app/core/seguranca.py`
- `backend/app/services/mfa_service.py`
- `backend/app/models/mfa_dispositivo.py`
- Migration

---

## 2.6 — CORS restrita

### Problema
`main.py:72-78` — `allow_credentials=True` + métodos amplos. Em prod com múltiplos ambientes, é bom restringir.

### Fix
```python
# config.py
cors_origins: list[str] = ["http://localhost:3000"]

# main.py
app = CORSMiddleware(
    wrapped,
    allow_origins=settings.cors_origins,  # lista, não único
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],  # remover PUT/OPTIONS (auto)
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    max_age=600,  # cache preflight
)
```

`.env` em prod: `CORS_ORIGINS=["https://app.example.com"]`.

### Files
- `backend/app/config.py`
- `backend/app/main.py`

---

## 2.7 — Servir frontend via reverse proxy (não FastAPI)

### Problema
`main.py:42-68` — catchall fallback para arquivos estáticos. Em prod, isso passa pelo CSRF middleware, SecurityHeaders, async stack — overhead em cada `/favicon.ico`, `/_next/...`. Plus, FastAPI não é otimizado para serving estático.

### Fix
- Em desenvolvimento: manter o catchall (conveniência).
- Em produção: nginx serve `/static/_next/*` e demais arquivos diretamente; FastAPI só responde `/api/*`.

```python
# main.py
if settings.ambiente == "desenvolvimento" and FRONTEND_DIR.is_dir():
    # ... código atual ...
```

`docs/deploy.md`: bloco nginx exemplo:
```nginx
location /_next/ { alias /var/www/frontend/_next/; expires 1y; }
location /api/ { proxy_pass http://localhost:8000; }
location / { try_files $uri $uri.html /index.html; }
```

### Files
- `backend/app/main.py`
- `docs/deploy.md`

---

## 2.8 — Consolidar embeddings via LangChain (remover httpx direto)

### Problema (#48)
`agents/inlinks/inseridor.py` e outros — mistura LangChain `ChatOpenAI` com chamadas próprias via httpx para embeddings (alguns lugares). Inconsistente e bypass de LangChain cache helpers.

### Fix
Padronizar uso de `langchain-openai`:

```python
from langchain_openai import OpenAIEmbeddings
from langchain_core.globals import set_llm_cache
from langchain_community.cache import RedisCache  # ou InMemoryCache

# core/embeddings.py
def _get_embeddings_model():
    if settings.llm_provider == "openai":
        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=settings.embedding_dimensions,
            api_key=settings.openai_api_key,
            max_retries=3,
            timeout=30,
        )
    # ...
```

Configurar cache LLM global em startup:
```python
# main.py / lifespan
from langchain_core.globals import set_llm_cache
from langchain_community.cache import RedisCache
import redis.asyncio as redis
set_llm_cache(RedisCache(redis.from_url(settings.redis_url)))
```

### Files
- `backend/app/core/embeddings.py`
- `backend/app/main.py` (lifespan)

---

## Critério de pronto

- [ ] Counter de hash legacy implementado; cutoff configurado em 2026-07-15
- [ ] HIBP retorna `None` se indisponível; modo `queue` revalida em background
- [ ] CSP sem `unsafe-*` em prod; nonces funcionando
- [ ] Cookie `secure` automático por ambiente; `samesite=strict`
- [ ] TOTP `valid_window=0` + anti-replay
- [ ] CORS origins via env var
- [ ] Em prod, nginx serve estáticos
- [ ] LangChain OpenAIEmbeddings unificado

## Riscos
- CSP nonces requer mudança no Next.js — testar dev primeiro.
- TOTP `valid_window=0` pode irritar usuários com drift de relógio. Monitorar tickets.
- Migration legacy hash precisa email service funcionando para forced reset.
