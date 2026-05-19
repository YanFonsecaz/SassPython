# SPEC: Sistema de Login e Autenticação

> **Documento para consumo por Agente de IA.** Lê esta spec na íntegra antes de escrever qualquer código.
> Cada regra marcada com `PROIBIDO` é inviolável. Violações destas regras são bugs críticos de segurança.

| Campo | Valor |
|---|---|
| **Título** | Sistema de Login e Autenticação |
| **Versão** | 1.0 |
| **Data** | 2026-04-20 |
| **Classificação** | Confidencial |
| **Referência** | docs/Security/*.md |

---

## 1. REGRAS ABSOLUTAS — NUNCA FAÇA

| # | PROIBIDO | Motivo |
|---|----------|--------|
| 1 | **NUNCA** use `Math.random()`, `random`, `rand()`, `mt_rand()` para gerar tokens, session IDs, nonces ou segredos | Não são criptograficamente seguros. Use CSPRNG: `secrets` (Python), `crypto.randomBytes()` (Node.js), `random_bytes()` (PHP) |
| 2 | **NUNCA** use `Access-Control-Allow-Origin: *` | Permite que qualquer site faça requisições à sua API com cookies do usuário |
| 3 | **NUNCA** use `SameSite: None` nos cookies de sessão | Permite envio em TODAS as requisições cross-site |
| 4 | **NUNCA** use `innerHTML` com dados dinâmicos do usuário | XSS — use `innerText`, `createElement`, `createTextNode` |
| 5 | **NUNCA** use `eval()` ou `new Function()` | Execução de código arbitrário |
| 6 | **NUNCA** armazene senhas em texto plano, SHA-1, MD5 ou SHA-256 puro | Use Argon2id |
| 7 | **NUNCA** truncar senhas | Retorne erro se exceder 64 caracteres |
| 8 | **NUNCA** retorne mensagens diferentes para "email existe" vs "email não existe" no login e reset de senha | User Enumeration — use mensagem genérica |
| 9 | **NUNCA** construa URLs de reset usando `req.headers.host` | Header Host Injection — use host fixo em config |
| 10 | **NUNCA** inclua tokens secretos em query strings de requisições server-side | Use headers HTTP (Authorization) |
| 11 | **NUNCA** autentique automaticamente após reset de senha | Redirecione para login |
| 12 | **NUNCA** implemente perguntas de segurança | Inseguras por natureza — use MFA |
| 13 | **NUNCA** carregue recursos externos (CDN, analytics, tag manager, fontes) na página de reset de senha | Código externo pode capturar o token da URL |
| 14 | **NUNCA** confie no client-side para validação de segurança | Toda validação deve ser replicada no servidor |
| 15 | **NUNCA** exponha session IDs, tokens ou dados sensíveis em logs | Logs devem conter apenas user_id (não sensível), timestamp, request_url |
| 16 | **NUNCA** use `window.*` ou `document.*` para variáveis globais | Escopo global acessível por XSS |
| 17 | **NUNCA** use `JSON.parse` em conjunto com `eval` | Sempre use `JSON.parse()` isolado |
| 18 | **NUNCA** armazene dados sensíveis em localStorage ou sessionStorage | Acessível por XSS |
| 19 | **NUNCA** confie apenas em SameSite cookies para CSRF | Combine sempre com Nonce/CSRF Token |
| 20 | **NUNCA** use IP como `rpID` no FIDO2 | Deve ser um domínio registrado |
| 21 | **NUNCA** implemente sessão do zero | Use o mecanismo de sessão do framework |
| 22 | **NUNCA** nomeie o cookie de sessão com nome que identifique a plataforma (`PHPSESSID`, `JSESSIONID`, etc.) | Use `sessionid` |
| 23 | **NUNCA** valide prefixo de URL sem incluir a barra final | `http://localhost` é burlável por `localhost.hacker.com` — use `http://localhost/` |
| 24 | **NUNCA** exponha headers `Server` (com versão), `X-Powered-By`, `Generator` | Fingerprinting do servidor |
| 25 | **NUNCA** permita `Cache-Control` sem `no-store` na área autenticada | Sessão pode ser cacheada em disco |

---

## 2. STACK TECNOLÓGICA

| Componente | Tecnologia |
|---|---|
| Backend | Python (FastAPI ou Flask) |
| Hashing de senhas | `argon2-cffi` (PasswordHasher) |
| MFA TOTP | `pyotp` |
| MFA FIDO2 | `py_webauthn` (server) + `simplewebauthn` (client) |
| Validação de força de senha | `zxcvbn` |
| Vazamento de senhas | Have I Been Pwned API (k-anonymity) |
| QR Code | `segno` |
| Geração de tokens | `secrets` module (Python), `crypto.randomBytes()` (Node.js) |

---

## 3. MODELO DE DADOS

```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    password        TEXT NOT NULL,
    otp_secret      TEXT,
    mfa_enabled     BOOLEAN DEFAULT FALSE,
    reset_token     TEXT,
    reset_time      INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    credential_id   TEXT NOT NULL UNIQUE,
    public_key      TEXT NOT NULL,
    sign_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    token           TEXT NOT NULL UNIQUE,
    ip_address      TEXT,
    user_agent      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_users_reset_token ON users(reset_token);
```

---

## 4. ENDPOINTS DA API

### 4.1 `POST /api/auth/login`

**Request:**

```json
{
  "email": "string (required, formato email válido)",
  "password": "string (required, 8-64 chars)"
}
```

**Response (credenciais inválidas — 401):**

```json
{
  "error": "Credenciais inválidas"
}
```

**OBRIGATÓRIO:** Mesma mensagem e mesma latência (~1.5s) para email existente e inexistente.

**Response (MFA requerido — 200):**

```json
{
  "mfa_required": true,
  "mfa_type": "totp | webauthn",
  "temp_session": "string (session temporária, 5 min)"
}
```

**Response (sucesso — 200):**

```json
{
  "user": {
    "id": "integer",
    "email": "string"
  }
}
```

Cookie `sessionid` setado com: `HttpOnly=true`, `Secure=true`, `SameSite=Lax`, `Path=/`.

**Lógica:**

1. Buscar usuário por email
2. Se não encontrado: aguardar tempo restante para totalizar ~1.5s, retornar 401 genérico
3. Verificar hash Argon2. Se falhar: verificar hash legado SHA-256 (lazy migration). Se legado válido: re-hash com Argon2 e atualizar DB
4. Se MFA habilitado: criar session temporária (5 min), retornar `mfa_required`
5. Se não MFA: criar session, setar cookie, renovar session ID

### 4.2 `POST /api/auth/mfa/verify`

**Request (TOTP):**

```json
{
  "temp_session": "string",
  "code": "string (6 dígitos TOTP)"
}
```

**Request (WebAuthn):**

```json
{
  "temp_session": "string",
  "credential_id": "string",
  "signature": "string",
  "authenticator_data": "string",
  "client_data_json": "string"
}
```

**Response (inválido — 401):**

```json
{
  "error": "Código inválido"
}
```

**Response (sucesso — 200):**

```json
{
  "user": { "id": "integer", "email": "string" }
}
```

Cookie `sessionid` setado.

**Lógica TOTP:** `pyotp.TOTP(secret).verify(code, valid_window=1)`

**Lógica WebAuthn:** Validar `sign_count` > `currentSignCount` (anti-replay). Validar `expectedOrigin` e `expectedRPID`.

### 4.3 `POST /api/auth/logout`

**Response (200):**

```json
{
  "message": "Logout realizado"
}
```

**Lógica:** Destruir session no servidor. Cookie `sessionid` expirado.

### 4.4 `POST /api/auth/forgot-password`

**Request:**

```json
{
  "email": "string (required)"
}
```

**Response (200 — sempre):**

```json
{
  "message": "Se este e-mail está cadastrado, você receberá as instruções."
}
```

**OBRIGATÓRIO:**

- Mesma resposta para email válido e inválido
- Mesmo tempo de resposta (~1.5s) — usar `sleep()` se necessário
- **NUNCA** usar `req.headers.host` para montar URL do email — usar `APP_URL` de config
- Token: `secrets.token_urlsafe(32)` (32 bytes, Base64URL)
- Expiração: 30 minutos (armazenar `reset_time`, não `expires_at`)
- Armazenar token em `users.reset_token` e timestamp em `users.reset_time`

### 4.5 `POST /api/auth/reset-password`

**Request:**

```json
{
  "token": "string (Base64URL)",
  "password": "string (8-64 chars, score zxcvbn >= 3)",
  "password_confirmation": "string (idêntica à password)"
}
```

**Response (token inválido/expirado — 400):**

```json
{
  "error": "Token inválido ou expirado"
}
```

**Response (senha fraca — 400):**

```json
{
  "error": "Senha não atende aos requisitos de segurança"
}
```

**Response (sucesso — 200):**

```json
{
  "message": "Senha alterada com sucesso"
}
```

**Lógica obrigatória:**

1. Validar token contra janela temporal: `reset_time >= (now - 30min)` E `reset_time <= now`
2. Validar senha com `zxcvbn` (score >= 3)
3. Verificar contra HIBP API (k-anonymity: enviar apenas 5 primeiros chars do SHA-1)
4. Hash com Argon2: `PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4).hash(password)`
5. Se MFA habilitado para o usuário: exigir verificação MFA ANTES de permitir reset
6. Invalidar token (setar `reset_token = NULL`)
7. **Invalidar TODAS as sessões** do usuário: `DELETE FROM sessions WHERE user_id = ?`
8. Enviar notificação por email imediatamente
9. **NUNCA** autenticar automaticamente — redirecionar para login
10. Rate limit: 5 tentativas por IP por minuto

---

## 5. CONFIGURAÇÃO DE SESSÃO

| Parâmetro | Valor |
|---|---|
| Nome do cookie | `sessionid` |
| `HttpOnly` | `true` |
| `Secure` | `true` |
| `SameSite` | `Lax` (login), `Strict` (área autenticada) |
| `Path` | `/` |
| `max-age` | NÃO definir (expira ao fechar browser) |
| Entropia do Session ID | Mínimo 128 bits (CSPRNG) |
| Strict Mode | `true` |
| Timeout de inatividade | 15 minutos (server-side) |
| Renovação | Obrigatória em mudança de privilégio |
| Cache-Control | `no-store, no-cache, must-revalidate, max-age=0` (área logada) |

---

## 6. CONFIGURAÇÃO DE CORS

```python
KNOWN_HOSTS = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    # Adicionar domínios de produção aqui
]

def set_cors(response, request):
    origin = request.headers.get("Origin")
    if origin in KNOWN_HOSTS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Max-Age"] = "3600"
```

Rota OPTIONS preflight obrigatória. **NUNCA** retornar `*`.

---

## 7. PROTEÇÃO CSRF

**Todo** formulário que executa ação (POST/PUT/DELETE) DEVE ter nonce:

```python
# Gerar nonce
session['nonce'] = secrets.token_hex(16)

# No formulário HTML
# <input type="hidden" name="nonce" value="{session['nonce']}">

# Validar no servidor
nonce = request.form.get('nonce')
if not nonce or nonce != session.get('nonce'):
    return "Erro", 403
session.pop('nonce', None)  # Consumir — uso único
```

---

## 8. HEADERS DE SEGURANÇA (todas as respostas)

```http
Content-Security-Policy: frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Type: application/json; charset=utf-8
```

Na página de reset de senha:

```http
Referrer-Policy: no-referrer
```

Remover headers:

```http
Server: (sem versão)
X-Powered-By: (removido)
```

---

## 9. RATE LIMITING

| Endpoint | Limite | Lockout |
|---|---|---|
| `POST /api/auth/login` | 5 tentativas / IP / 15 min | Progressivo: 1min -> 5min -> 15min -> 30min |
| `POST /api/auth/forgot-password` | 3 / IP / hora | 1 hora |
| `POST /api/auth/reset-password` | 5 / IP / min | 15 min |
| `POST /api/auth/mfa/verify` | 10 / IP / 15 min | 15 min |

---

## 10. PÁGINA DE RESET DE SENHA — REGRAS

- **ZERO** recursos externos (sem CDN, sem Google Analytics, sem Tag Manager, sem fontes externas)
- HTML, CSS e JS inline apenas
- Header `Referrer-Policy: no-referrer`
- Minimizar links (logotipo sem link, sem footer, sem menu)
- Rate limit por IP
- Campo de senha + confirmação de senha (ambos obrigatórios)
- MFA se habilitado para o usuário

---

## 11. MIGRAÇÃO DE HASH LEGADO

```python
def login(email, password):
    start = time.time()
    user = db.query("SELECT id, password FROM users WHERE email = ?", (email,))
    if not user:
        elapsed = time.time() - start
        if elapsed < 1.5:
            time.sleep(1.5 - elapsed)
        return False

    try:
        if ph.verify(user.password, password):
            if ph.check_needs_rehash(user.password):
                new_hash = ph.hash(password)
                db.execute("UPDATE users SET password = ? WHERE id = ?", (new_hash, user.id))
            return user.id
    except Exception:
        pass

    # Fallback legado (SHA-256) — remover após migração completa
    import hashlib
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    if legacy_hash == user.password:
        new_hash = ph.hash(password)
        db.execute("UPDATE users SET password = ? WHERE id = ?", (new_hash, user.id))
        return user.id

    elapsed = time.time() - start
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)
    return False
```

---

## 12. REAUTENTICAÇÃO — OPERAÇÕES SENSÍVEIS

Estas operações exigem reautenticação (senha OU MFA OU FIDO2):

- Alteração de senha
- Alteração de email
- Ativação/desativação de MFA
- Qualquer operação de alto risco definida pelo negócio

---

## 13. LOGGING DE SEGURANÇA

**Campos obrigatórios:** `timestamp`, `interaction_id`, `app_version`, `hostname`, `request_url`, `user_id`

**PROIBIDO nos logs:** session IDs, tokens, senhas, dados pessoais sensíveis

**Banco de logs:** Separado do banco da aplicação. Usuário da app NÃO pode ter acesso ao banco de logs.

---

## 14. CHECKLIST DE VERIFICAÇÃO

- [ ] Senhas hasheadas com Argon2id (memory=64MB, time=3, parallelism=4)
- [ ] Session ID gerado com CSPRNG, mínimo 128 bits
- [ ] Cookie `sessionid`: HttpOnly, Secure, SameSite=Lax/Strict
- [ ] Strict Mode habilitado
- [ ] CORS com whitelist (nunca `*`)
- [ ] CSRF nonce em todos os formulários com ações
- [ ] Anti-enumeration no login e forgot-password (mesma resposta, mesmo tempo)
- [ ] Rate limiting em todos os endpoints de auth
- [ ] Reset de senha: token CSPRNG 32 bytes, expira 30 min
- [ ] Reset de senha: zero recursos externos na página
- [ ] Reset de senha: `Referrer-Policy: no-referrer`
- [ ] Reset de senha: invalidar todas as sessões + notificar por email
- [ ] Reset de senha: redirecionar para login (nunca auto-auth)
- [ ] Headers de segurança em todas as respostas
- [ ] `Cache-Control: no-store` na área autenticada
- [ ] `X-Content-Type-Options: nosniff` em todas as respostas
- [ ] Logs sem dados sensíveis, banco separado
- [ ] Migração lazy de hashes legados implementada
- [ ] Validação de senha com zxcvbn (score >= 3)
- [ ] Verificação contra HIBP API
- [ ] Nenhuma variável global em `window.*` ou `document.*`
- [ ] Nenhum uso de `innerHTML`, `eval()`, `new Function()`
- [ ] Nenhum dado sensível em localStorage/sessionStorage

---

## 15. HISTÓRICO DE REVISÕES

| Versão | Data | Descrição |
|---|---|---|
| 1.0 | 2026-04-20 | Versão inicial — Baseada nos SDDs de Segurança |
