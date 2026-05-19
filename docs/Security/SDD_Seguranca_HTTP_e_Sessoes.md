# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança HTTP, Gerenciamento de Sessões e Headers de Segurança

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança HTTP, Sessões e Headers de Segurança               |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para headers HTTP, gerenciamento de sessões de servidor e configuração de CORS (Cross-Origin Resource Sharing) em aplicações web. O documento aborda tanto responsabilidades do programador quanto da infraestrutura, delineando claramente onde cada atua.

### 1.2 Escopo

- Configuração segura de CORS (Access-Control-Allow-Origin)
- Gerenciamento de sessões server-side (cookies, expiração, strict mode)
- Headers de segurança: Referrer-Policy, HSTS, X-Content-Type-Options, remoção de headers de fingerprinting
- Content-Type e proteção contra MIME sniffing
- Arquivos poliglotas e proteções associadas

### 1.3 Definições e Acrônimos

| Termo                | Definição                                                        |
|----------------------|------------------------------------------------------------------|
| **CORS**             | Cross-Origin Resource Sharing                                    |
| **CSPRNG**           | Cryptographically Secure Pseudo Random Number Generator           |
| **HSTS**             | HTTP Strict Transport Security                                    |
| **MIME Sniffing**    | Prática do navegador de inferir o tipo de arquivo                |
| **Polyglot**         | Arquivo válido em múltiplos formatos (HTML, JPEG, PDF, ZIP)      |
| **Session Fixation** | Ataque em que o agressor fixa o ID de sessão da vítima           |
| **Preflight**        | Requisição OPTIONS enviada pelo navegador antes da requisição real |
| **Origin**           | Esquema + host + porta (ex: `https://example.com:443`)           |
| **SameSite**         | Atributo de cookie que controla envio em requisições cross-site  |

### 1.4 Responsabilidades: Programador vs. Infraestrutura

| Tópico                           | Responsável    | Motivo                                              |
|----------------------------------|----------------|------------------------------------------------------|
| CORS (allow-origin, methods)     | **Programador**| Depende de regras de negócio e origens conhecidas    |
| Cookie de sessão (flags)         | **Programador**| Configurado no código da aplicação                  |
| Referrer-Policy (por página)     | **Programador**| Páginas específicas exigem valores específicos      |
| HSTS                             | **Infra**      | Configurado no servidor web                         |
| Remoção de Server header         | **Infra**      | Configurado no servidor web (Apache, Nginx, IIS)    |
| X-Content-Type-Options          | **Infra**      | Configurado no servidor web                         |
| Content-Type de respostas da API | **Programador**| Definido no código da aplicação                     |

---

## 2. Visão Geral de Arquitetura

### 2.1 Fluxo CORS

```
┌───────────────────────────────────────────────────────────────────┐
│                    FLUXO DE REQUISIÇÃO CORS                       │
│                                                                   │
│  ┌──────────┐         ┌──────────────┐         ┌──────────────┐  │
│  │ Cliente  │         │  Navegador   │         │   Servidor   │  │
│  │ (JS/Fetch)│        │              │         │    API       │  │
│  └────┬─────┘         └──────┬───────┘         └──────┬───────┘  │
│       │                      │                         │          │
│       │  1. fetch("api/url") │                         │          │
│       │─────────────────────▶│                         │          │
│       │                      │  2. Preflight (OPTIONS) │          │
│       │                      │────────────────────────▶│          │
│       │                      │                         │          │
│       │                      │  3. Access-Control-*    │          │
│       │                      │    Allow-Origin: {origin}│          │
│       │                      │    Allow-Methods: GET..  │          │
│       │                      │    Allow-Headers: ...   │          │
│       │                      │◀────────────────────────│          │
│       │                      │                         │          │
│       │                      │  4. Requisição real     │          │
│       │                      │  (GET/POST/etc)         │          │
│       │                      │────────────────────────▶│          │
│       │                      │                         │          │
│       │                      │  5. Resposta + Headers  │          │
│       │                      │    CORS                  │          │
│       │                      │◀────────────────────────│          │
│       │  6. Dados            │                         │          │
│       │◀─────────────────────│                         │          │
└───────────────────────────────────────────────────────────────────┘

  Se origin NÃO está na whitelist → Navegador bloqueia no passo 2/3
  Se origin ESTÁ na whitelist → Requisição segue normalmente
```

### 2.2 Arquitetura de Sessões Server-Side

```
┌─────────────────────────────────────────────────────────┐
│                 GERENCIAMENTO DE SESSÃO                  │
│                                                         │
│  ┌──────────┐    Cookie     ┌──────────────┐            │
│  │ Navegador │◄────────────▶│   Servidor    │           │
│  │           │  SessionID   │              │            │
│  │           │  (HTTPonly,  │  ┌────────┐  │            │
│  │           │   Secure,    │  │Storage │  │            │
│  │           │   SameSite)  │  │Sessões │  │            │
│  └──────────┘               │  └────────┘  │            │
│                             └──────────────┘            │
│                                                         │
│  Flags obrigatórias do cookie de sessão:                 │
│  • HttpOnly    → JavaScript não acessa o cookie          │
│  • Secure      → Enviado apenas via HTTPS                │
│  • SameSite    → Controle de envio cross-site            │
│  • Path        → Escopo do cookie (/ para toda a app)   │
│  • Strict Mode → Rejeita IDs de sessão não gerados      │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Design de Componentes

### 3.1 Componente 1: CORS (Cross-Origin Resource Sharing)

#### 3.1.1 Requisitos

| ID       | Requisito                                                                     | Prioridade |
|----------|-------------------------------------------------------------------------------|------------|
| CORS-01  | Implementar whitelist de origens conhecidas                                  | Alta       |
| CORS-02  | NUNCA usar `Access-Control-Allow-Origin: *` para APIs com dados sensíveis    | Alta       |
| CORS-03  | Implementar rota OPTIONS (preflight) que retorne headers CORS                | Alta       |
| CORS-04  | Limitar `Access-Control-Allow-Methods` aos métodos necessários por rota     | Média      |
| CORS-05  | Declarar `Access-Control-Allow-Headers` para headers customizados            | Média      |
| CORS-06  | Retornar a origem específica (não `*`) quando credenciais estão envolvidas   | Média      |

#### 3.1.2 Por que `*` (Asterisco) é Perigoso

```
┌─────────────────────────────────────────────────────────┐
│           RISCO DO Access-Control-Allow-Origin: *        │
│                                                         │
│  Qualquer site na internet pode fazer requisições à API │
│                                                         │
│  hacker.com                                            │
│    ├── fetch("https://meusite.com/api/saque")           │
│    ├── fetch("https://meusite.com/api/transferencia")   │
│    └── fetch("https://meusite.com/api/dados-sensiveis") │
│                                                         │
│  Se o usuário estiver logado, cookies são enviados      │
│  automaticamente → dados exfiltrados para o atacante    │
└─────────────────────────────────────────────────────────┘
```

#### 3.1.3 Implementação de Referência

```ruby
# Helpers de CORS (Ruby/Sinatra — conceito aplicável a qualquer linguagem)

KNOWN_HOSTS = [
  "http://localhost:5000",
  "http://127.0.0.1:5000",
  "https://meusite.com",
  "https://app.meusite.com"
]

def set_cors(response)
  origin = request.env["HTTP_ORIGIN"]

  if KNOWN_HOSTS.include?(origin)
    response.headers["Access-Control-Allow-Origin"] = origin  # A origem específica
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
  end
  # Se não está na lista → não retorna header CORS
  # O navegador bloqueia automaticamente
end
```

**Para APIs de parceiros (B2B):**
```ruby
# Consultar origens cadastradas no banco de dados
origin = request.env["HTTP_ORIGIN"]
partner = Partner.find_by(origin: origin)
if partner && partner.active?
  response.headers["Access-Control-Allow-Origin"] = origin
end
```

#### 3.1.4 Headers CORS Essenciais

| Header                            | Descrição                                              |
|-----------------------------------|--------------------------------------------------------|
| `Access-Control-Allow-Origin`     | Origem permitida (lista específica, nunca `*`)         |
| `Access-Control-Allow-Methods`    | Métodos HTTP permitidos (GET, POST, etc.)             |
| `Access-Control-Allow-Headers`    | Headers customizados permitidos na requisição          |
| `Access-Control-Allow-Credentials`| Permite envio de cookies (`true` exige origem específica) |
| `Access-Control-Max-Age`          | Tempo de cache do preflight (em segundos)              |

---

### 3.2 Componente 2: Gerenciamento de Sessões Server-Side

#### 3.2.1 Requisitos

| ID       | Requisito                                                                  | Prioridade |
|----------|----------------------------------------------------------------------------|------------|
| SESS-01  | Usar mecanismo de sessão do framework (nunca implementar do zero)          | Alta       |
| SESS-02  | Cookie de sessão: nome genérico (ex: `sessionid`), sem identificar a plataforma | Alta   |
| SESS-03  | Cookie de sessão: `HttpOnly = true`                                         | Alta       |
| SESS-04  | Cookie de sessão: `Secure = true` (HTTPS obrigatório)                       | Alta       |
| SESS-05  | Cookie de sessão: `SameSite = Strict` ou `Lax`                              | Alta       |
| SESS-06  | Session ID: gerado com CSPRNG, mínimo 64 bits de entropia (8 bytes)        | Alta       |
| SESS-07  | Session ID: validar formato como qualquer input do usuário                  | Alta       |
| SESS-08  | Strict Mode: habilitado (rejeitar IDs de sessão não gerados pelo servidor)  | Alta       |
| SESS-09  | Renovar ID de sessão em mudanças de privilégio                               | Alta       |
| SESS-10  | Expiração da sessão: tempo curto (2-5 min fintech, 15-30 min e-commerce)    | Alta       |
| SESS-11  | Área logada: `Cache-Control: no-store`                                      | Alta       |
| SESS-12  | Logout automático por inatividade (server-side obrigatório, client-side UX)  | Alta       |
| SESS-13  | Tela de login: timeout de inatividade (redirecionar para logout)             | Média      |
| SESS-14  | Fechar navegador → logout forçado                                            | Média      |

#### 3.2.2 Configuração do Cookie de Sessão

| Atributo  | Valor Recomendado | Motivo                                                    |
|-----------|-------------------|-----------------------------------------------------------|
| `Name`    | `sessionid`       | Não vaza a plataforma (evita `PHPSESSID`, `JSESSIONID`)  |
| `HttpOnly`| `true`            | JavaScript não pode ler o cookie                          |
| `Secure`  | `true`            | Enviado apenas via HTTPS                                  |
| `SameSite`| `Strict` ou `Lax` | Controle de envio cross-site                              |
| `Path`    | `/`               | Cookie válido em todo o site                              |

**Valores de SameSite:**

| Valor      | Comportamento                                                                    | Uso Recomendado          |
|------------|----------------------------------------------------------------------------------|--------------------------|
| `Strict`   | Cookie NUNCA é enviado em navegação cross-site                                   | Bancos, fintechs, governo |
| `Lax`      | Cookie enviado em navegação top-level (GET via link), mas não em requests cross-site | Padrão, maioria das apps |
| `None`     | Cookie enviado em TODAS as requisições cross-site (requer `Secure`)              | **NÃO RECOMENDADO**      |

> **Nota:** `SameSite: None` só funciona com `Secure: true`. Nunca use `None` a menos que tenha um motivo justificado.

#### 3.2.3 Entropia do Session ID

| Entropia     | Tempo para Quebra (1.000 req/s, 10.000 sessões ativas) |
|--------------|---------------------------------------------------------|
| 32 bits (4 B) | ~7 minutos                                              |
| 64 bits (8 B) | ~585 anos                                               |
| 128 bits (16 B)| Praticamente impossível                                  |

> Use CSPRNG para gerar o Session ID. Nunca use `Math.random()` ou funções `random()` padrão.

#### 3.2.4 Strict Mode (Proteção contra Session Fixation)

**Problema:** Sem strict mode, se um agressor enviar um cookie com um Session ID arbitrário para a vítima, e a vítima navegar até o site, o servidor **cria uma sessão** com aquele ID arbitrário. O agressor, conhecendo o ID, assume a sessão.

**Ataque:**

```
┌──────────────────────────────────────────────────────────────┐
│               ATAQUE DE SESSION FIXATION                      │
│                                                              │
│  1. Hacker cria página maliciosa com:                        │
│     document.cookie = "sessionid=123456"                      │
│                                                              │
│  2. Envia link para vítima                                   │
│                                                              │
│  3. Vítima clica no link → cookie é setado                   │
│                                                              │
│  4. Vítima navega até o site legítimo                        │
│     → Servidor cria sessão com ID "123456"                   │
│     → Vítima se cadastra, faz login, etc.                    │
│                                                              │
│  5. Hacker usa cookie "123456" → assume a sessão da vítima   │
└──────────────────────────────────────────────────────────────┘
```

**Solução:** Habilitar strict mode

```
┌──────────────────────────────────────────────────────────────┐
│               STRICT MODE HABILITADO                          │
│                                                              │
│  1. Vítima acessa site com cookie "123456"                   │
│     → Servidor verifica: "123456" não foi gerado por mim     │
│     → Servidor IGNORA o cookie                                │
│     → Servidor gera NOVO session ID                           │
│     → Servidor envia novo cookie para a vítima               │
│                                                              │
│  2. Ataque neutralizado: o hacker não conhece o novo ID       │
└──────────────────────────────────────────────────────────────┘
```

**Configuração por plataforma:**

| Plataforma | Configuração                                          |
|------------|-------------------------------------------------------|
| PHP        | `session.use_strict_mode = 1` no `php.ini`            |
| Express    | Middleware de validação de session ID customizado      |
| Django     | `SESSION_COOKIE_SECURE = True` no `settings.py`       |
| Rails      | `Rails.application.config.session_store` (Strict por padrão) |

#### 3.2.5 Renovação de Sessão em Mudança de Privilégio

```
┌──────────────────────────────────────────────────────────┐
│           RENOVAÇÃO DE SESSÃO EM MUDANÇA DE PRINCÍPIO    │
│                                                          │
│  Gatilhos:                                               │
│  • Usuário alterou plano (ex: free → premium)            │
│  • Administrador revogou acesso                          │
│  • Permissão alterada (admin → user, author → editor)    │
│  • Usuário ativou/desativou MFA                          │
│                                                          │
│  Ações:                                                 │
│  1. Expirar todas as sessões do usuário                  │
│  2. Obrigá-lo a fazer login novamente                    │
│  3. Recarregar permissões do zero                        │
└──────────────────────────────────────────────────────────┘
```

#### 3.2.6 Cache-Control para Área Logada

**Problema:** O navegador pode armazenar respostas HTTP completas em disco, incluindo o Session ID no cookie.

| Header                        | Comportamento                                                        |
|-------------------------------|----------------------------------------------------------------------|
| `Cache-Control: no-cache`     | Revalida sempre, mas **pode** armazenar em disco                     |
| `Cache-Control: no-store`     | **NÃO armazena em disco** — mantém apenas na memória                |

```http
Cache-Control: no-store, no-cache, must-revalidate, max-age=0
```

> Toda a área logada deve usar `no-store`. O cache da área logada não traz benefício (conteúdo é dinâmico por usuário).

#### 3.2.7 Timeout e Inatividade

| Mecanismo                            | Onde Implementar | Motivo                                        |
|--------------------------------------|------------------|-----------------------------------------------|
| Timeout na tela de login             | Client (JS)      | Evita session fixation via cookie pré-fixado   |
| Logout automático por inatividade    | Server           | Proteção primária contra acesso físico         |
| Logout automático por inatividade    | Client (UX)      | Melhora experiência (ex: modal do WordPress)   |
| Fechar navegador → logout            | Server           | Cookie de sessão sem `max-age` persistente     |

**Implementação server-side:**
```ruby
# Exemplo: verificar última atividade
if session[:last_activity] && (Time.now - session[:last_activity]) > SESSION_TIMEOUT
  session.destroy
  redirect '/login'
end
session[:last_activity] = Time.now
```

---

### 3.3 Componente 3: Referrer-Policy

#### 3.3.1 Visão Geral

O header `Referer` é enviado automaticamente pelo navegador em cada requisição, contendo a URL de origem. Isso pode vazar tokens, dados sensíveis e informações de navegação.

#### 3.3.2 Valores Disponíveis

| Valor                            | Comportamento                                                                 | Uso                           |
|----------------------------------|-------------------------------------------------------------------------------|-------------------------------|
| `no-referrer`                    | NUNCA envia o header Referer                                                 | Páginas com token na URL      |
| `no-referrer-when-downgrade`     | Envia apenas se o destino for HTTPS ou mesmo nível                            | Raramente usado               |
| `origin`                         | Envia apenas a origem (domínio sem caminho)                                  | APIs                          |
| `origin-when-cross-origin`       | Caminho completo no mesmo site; apenas origem para fora                      | Padrão conservador            |
| `same-origin`                    | Caminho completo no mesmo site; nada para fora                               | Aplicações com áreas sensíveis|
| `strict-origin`                  | Origem apenas, mas NADA em downgrade (HTTPS → HTTP)                           | Configuração segura           |
| `strict-origin-when-cross-origin`| **Padrão dos navegadores moderno**: caminho interno, origem externa, nada em downgrade | **Recomendado geral**  |
| `unsafe-url`                     | Sempre envia URL completa                                                     | **NÃO USAR**                  |

#### 3.3.3 Recomendação

```http
# Para o site inteiro (configuração do servidor):
Referrer-Policy: strict-origin-when-cross-origin

# Para páginas específicas com token/segredo na URL:
Referrer-Policy: no-referrer
```

---

### 3.4 Componente 4: HSTS (HTTP Strict Transport Security)

#### 3.4.1 Requisitos

| ID       | Requisito                                                        | Prioridade |
|----------|------------------------------------------------------------------|------------|
| HSTS-01  | Habilitar header Strict-Transport-Security em produção           | Alta       |
| HSTS-02  | Configurar max-age (recomendado: 1 ano)                          | Alta       |
| HSTS-03  | Considerar preload para inclusão na lista HSTS dos navegadores   | Média      |
| HSTS-04  | Implementar gradativemente (15 min → 1 semana → 1 ano)          | Média      |

#### 3.4.2 Implementação

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

| Parâmetro          | Descrição                                                  |
|--------------------|------------------------------------------------------------|
| `max-age`          | Tempo em segundos que o navegador cacheia a diretiva (31536000 = 1 ano) |
| `includeSubDomains`| Aplica HSTS a todos os subdomínios                          |
| `preload`          | Inclui na lista HSTS pré-carregada dos navegadores (Chrome, Firefox) |

**Comportamento:**

```
┌──────────────────────────────────────────────────────────┐
│             COM E SEM HSTS                                │
│                                                          │
│  SEM HSTS:                                               │
│  • Usuário digita http:// → carrega (inseguro!)          │
│  • Certificado inválido → usuário pode clicar "avançar"  │
│  • Redirecionamento HTTPS depende do servidor            │
│                                                          │
│  COM HSTS:                                               │
│  • Usuário digita http:// → navegador força HTTPS        │
│  • Certificado inválido → IMPOSSÍVEL prosseguir          │
│  • Primeira visita → cabeçalho é cacheado                │
│  • Preload → funciona MESMO na primeira visita           │
└──────────────────────────────────────────────────────────┘
```

**Estratégia de implantação gradual:**

| Fase  | max-age      | Duração  | Objetivo                                        |
|-------|-------------|----------|--------------------------------------------------|
| 1     | 900 (15 min)| 2 dias   | Teste — se houver problema, impacto mínimo      |
| 2     | 604800 (7d) | 1 semana  | Validação estendida                             |
| 3     | 31536000 (1a)| Permanente| Produção — segurança máxima                     |

---

### 3.5 Componente 5: Headers Anti-Fingerprinting

#### 3.5.1 Requisitos

| ID       | Requisito                                                        | Prioridade |
|----------|------------------------------------------------------------------|------------|
| FP-01    | Remover header `Server` (versão e SO do servidor web)           | Alta       |
| FP-02    | Remover header `X-Powered-By`                                    | Alta       |
| FP-03    | Remover header gerado por frameworks/CMS (ex: `X-AspNet-Version`, `Generator`) | Alta |
| FP-04    | Remover identificador de plataforma do cookie de sessão         | Alta       |

#### 3.5.2 Headers a Remover

| Header               | Exemplo de Valor                         | Risco                                              |
|----------------------|------------------------------------------|----------------------------------------------------|
| `Server`             | `Apache/2.4.52 (Ubuntu)`                | Versão desatualizada = falha conhecida explorável  |
| `X-Powered-By`       | `Express`, `PHP/8.4`, `ASP.NET`         | Identifica a linguagem/framework                   |
| `X-AspNet-Version`   | `4.0.30319`                              | Versão específica do framework                     |
| `Generator`          | `WordPress 6.4.2`                        | Versão específica do CMS                           |

**Configuração por servidor web:**

| Servidor | Configuração                                      |
|----------|---------------------------------------------------|
| Apache   | `ServerTokens Prod` no `security.conf`            |
| Nginx    | `server_tokens off;` no `nginx.conf`              |
| IIS      | `requestFiltering removeServerHeader="true"`      |

---

### 3.6 Componente 6: Content-Type e X-Content-Type-Options

#### 3.6.1 Requisitos

| ID       | Requisito                                                        | Prioridade |
|----------|------------------------------------------------------------------|------------|
| CT-01    | Sempre enviar header `Content-Type` com charset                   | Alta       |
| CT-02    | Enviar `X-Content-Type-Options: nosniff` em todas as respostas   | Alta       |
| CT-03    | Nunca confiar na extensão do arquivo para determinar o tipo      | Alta       |

#### 3.6.2 Por que Content-Type é Crítico

**Problema 1 — MIME Sniffing sem Content-Type:**

Sem `Content-Type`, o navegador **adivinha** o tipo do arquivo com base no conteúdo. Isso permite ataques:

```
Arquivo .txt contendo JavaScript:
  → Sem Content-Type: navegador pode executar como JS
  → Com Content-Type: text/plain → navegador NÃO executa
```

**Problema 2 — Arquivos Poliglotas:**

Um mesmo arquivo pode ser válido em múltiplos formatos:

```
┌─────────────────────────────────────────────┐
│         ARQUIVO POLYGLOTA                   │
│                                             │
│  index.html  → página HTML válida           │
│  index.jpg   → imagem JPEG válida           │
│  index.pdf   → documento PDF válido         │
│  index.zip   → archive ZIP válido           │
│                                             │
│  (mesmo arquivo binário, cabeçalhos manip.)│
└─────────────────────────────────────────────┘
```

> Se o servidor servir um upload sem Content-Type correto, o navegador pode interpretá-lo como um tipo perigoso.

#### 3.6.3 Header X-Content-Type-Options

```http
X-Content-Type-Options: nosniff
```

| Com header `nosniff` | Sem header `nosniff`                            |
|----------------------|-------------------------------------------------|
| Navegador **obedece** o Content-Type declarado | Navegador pode **ignorar** o Content-Type e "adivinhar" |
| `.txt` com JS nunca é executado              | `.txt` com JS pode ser executado como script    |
| Upload malicioso não é interpretado           | Upload poliglota pode ser interpretado perigosamente |

**Configuração no Apache:**

```apache
# .htaccess ou configuração do virtual host
Header always set X-Content-Type-Options "nosniff"
```

#### 3.6.4 Boas Práticas para Upload de Arquivos

1. Sempre servir uploads com Content-Type explícito (não depender de extensão)
2. Habilitar `X-Content-Type-Options: nosniff` globalmente
3. Validar o tipo real do arquivo (não apenas a extensão)
4. Não servir uploads do mesmo domínio da aplicação (usar CDN/subdomínio dedicado)

---

## 4. Checklist de Configuração

### 4.1 CORS

- [ ] Whitelist de origens conhecidas implementada
- [ ] `Access-Control-Allow-Origin: *` NÃO utilizado
- [ ] Rota OPTIONS (preflight) configurada
- [ ] `Access-Control-Allow-Methods` limitado por rota
- [ ] `Access-Control-Allow-Headers` declarado
- [ ] CORS aplicado apenas às rotas da API

### 4.2 Sessões

- [ ] Usando mecanismo de sessão do framework (não custom)
- [ ] Cookie nomeado de forma genérica (`sessionid`)
- [ ] `HttpOnly = true`
- [ ] `Secure = true`
- [ ] `SameSite = Lax` ou `Strict`
- [ ] Strict Mode habilitado
- [ ] Session ID com 64+ bits de entropia (CSPRNG)
- [ ] Session ID validado como input de usuário
- [ ] Sessão renovada em mudança de privilégio
- [ ] Expiração configurada (tempo curto)
- [ ] `Cache-Control: no-store` na área logada
- [ ] Logout automático por inatividade (server)
- [ ] Timeout na tela de login (client)

### 4.3 Headers de Segurança

- [ ] `Referrer-Policy: strict-origin-when-cross-origin` (global)
- [ ] `Referrer-Policy: no-referrer` (páginas com token na URL)
- [ ] `Strict-Transport-Security` habilitado (produção)
- [ ] `X-Content-Type-Options: nosniff` habilitado
- [ ] Header `Server` sem versão/SO
- [ ] Header `X-Powered-By` removido
- [ ] Content-Type com charset em todas as respostas da API

---

## 5. Considerações de Segurança

### 5.1 Ameaças e Mitigações

| Ameaça                                | Mitigação                                         | Ref.        |
|---------------------------------------|---------------------------------------------------|-------------|
| API acessada de origem não autorizada  | CORS com whitelist de origens                     | CORS-01     |
| Dados exfiltrados via fetch cross-origin| `Access-Control-Allow-Origin` específico           | CORS-02     |
| Session fixation                       | Strict Mode habilitado                            | SESS-08     |
| Roubo de cookie via JavaScript         | `HttpOnly = true`                                 | SESS-03     |
| Cookie interceptado em tráfego HTTP    | `Secure = true`                                   | SESS-04     |
| CSRF via cookie cross-site             | `SameSite = Lax` ou `Strict`                     | SESS-05     |
| Força bruta de Session ID              | 64+ bits entropia (CSPRNG)                        | SESS-06     |
| Privilegio obsoleto em sessão ativa    | Renovação de sessão em mudança de privilégio      | SESS-09     |
| Sessão abandonada                      | Logout automático por inatividade                 | SESS-12     |
| Token vazado via Referer               | `Referrer-Policy: no-referrer`                    | §3.3        |
| Certificado removido por atacante      | HSTS com preload                                  | HSTS-03     |
| Fingerprinting do servidor             | Remoção de headers Server, X-Powered-By, etc.     | §3.5        |
| Execução de upload como script         | `X-Content-Type-Options: nosniff` + Content-Type  | §3.6        |
| Arquivo poliglota executado            | Content-Type explícito + validação de tipo real   | CT-03       |

---

## 6. Referências

### 6.1 Especificações

| Padrão                     | Descrição                                           |
|----------------------------|-----------------------------------------------------|
| CORS (Fetch)               | W3C — Cross-Origin Resource Sharing                 |
| Referrer Policy            | W3C — Referrer Policy                               |
| HSTS                       | RFC 6797 — HTTP Strict Transport Security           |
| Cookie SameSite            | RFC 6265bis — Same-Site Cookies                     |
| X-Content-Type-Options     | IETF — MIME Type Sniffing Protection                |
| HSTS Preload List          | hstspreload.org — Lista de domínios pré-carregados  |

### 6.2 Ferramentas de Diagnóstico

| Ferramenta   | URL                      | Uso                                          |
|--------------|--------------------------|----------------------------------------------|
| Enable CORS  | enable-cors.org          | Guia de configuração CORS por servidor       |
| Security Headers | securityheaders.com  | Análise de headers de segurança               |
| HSTS Preload | hstspreload.org          | Submissão para lista HSTS de navegadores     |

---

## 7. Histórico de Revisões

| Versão | Data       | Descrição                                            |
|--------|------------|------------------------------------------------------|
| 1.0    | 2026-04-08 | Versão inicial — Baseado no curso "Segurança Para Devs" |
