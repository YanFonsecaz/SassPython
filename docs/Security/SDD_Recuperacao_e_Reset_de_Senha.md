# SOFTWARE DESIGN DOCUMENT (SDD)

## Recuperação e Reset de Senha — Boas Práticas de Segurança

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Sistema de Recuperação e Reset de Senha                     |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança e os requisitos técnicos para a implementação de um fluxo de recuperação e reset de senha seguro em aplicações web. O fluxo de reset de senha é um dos processos mais críticos e mais explorados por agressores, e deve ser tratado em **modo paranóico** — o mesmo nível de segurança aplicado a cadastro e autenticação.

### 1.2 Escopo

- Prevenção contra User Enumeration no fluxo de reset
- Geração segura de tokens de reset (CSPRNG)
- Construção segura da página de reset de senha
- Proteção contra injeção de header Host
- Controle de expiração de tokens
- Boas práticas pós-reset (invalidação de sessões, notificação)
- Análise de segurança de perguntas de segurança

### 1.3 Definições e Acrônimos

| Termo          | Definição                                                        |
|----------------|------------------------------------------------------------------|
| **SDD**        | Software Design Document                                         |
| **CSPRNG**     | Cryptographically Secure Pseudo Random Number Generator           |
| **User Enumeration** | Técnica de descobrir quais e-mails são usuários registrados  |
| **Timing Attack** | Ataque baseado na análise do tempo de resposta do servidor   |
| **Header Injection** | Inserção maliciosa de headers HTTP pelo cliente            |
| **Referrer Policy** | Header HTTP que controla o envio do header Referer          |
| **MFA**        | Multi-Factor Authentication                                      |
| **Rate Limit** | Limite de requisições por IP/usuario em determinado intervalo    |

---

## 2. Visão Geral de Arquitetura

### 2.1 Fluxo Completo de Reset de Senha

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────┐
│  Usuário │────▶│   Servidor   │────▶│   Banco de    │────▶│  Tabela   │
│          │◀────│   Web (API)  │◀────│   Dados       │◀────│  users   │
└──────────┘     └──────┬───────┘     └───────────────┘     └──────────┘
                        │
                        ▼
                 ┌──────────────┐
                 │  Serviço de  │
                 │    E-mail    │
                 └──────────────┘
```

**Etapas do fluxo:**

```
1. Usuário solicita reset ("Esqueci minha senha")
   └── Entrada: e-mail
   └── Saída: mesma resposta para e-mail válido e inválido
   └── Tempo: consistente (~1.5s) independente da validade do e-mail

2. Servidor gera token (CSPRNG) e salva no banco
   └── Token: 32 bytes, codificado em Base64URL
   └── Tempo de requisição: registrado (reset_time)

3. Servidor envia e-mail com link de reset
   └── URL: host fixo (config), nunca do header Host
   └── Link: /new-password?token={token}

4. Usuário clica no link → página de reset
   └── Rate limit por IP
   └── Validação de expiração do token
   └── Confirmação de senha (digitar duas vezes)
   └── MFA se habilitado

5. Usuário submete nova senha
   └── Invalidar todas as sessões ativas
   └── Enviar notificação por e-mail
   └── Redirecionar para tela de login (NÃO autenticar automaticamente)
```

---

## 3. Design de Componentes

### 3.1 Componente 1: Solicitação de Reset (Anti-Enumeration)

#### 3.1.1 Requisitos

| ID       | Requisito                                                            | Prioridade |
|----------|----------------------------------------------------------------------|------------|
| RESET-01 | A resposta deve ser idêntica para e-mail existente e inexistente     | Alta       |
| RESET-02 | O tempo de resposta deve ser consistente (~1.500ms fixos)            | Alta       |
| RESET-03 | Headers, cookies e conteúdo HTTP devem ser idênticos em ambos casos  | Alta       |
| RESET-04 | O token deve ser gerado com CSPRNG (32 bytes mínimo)                 | Alta       |

#### 3.1.2 Prevenção contra User Enumeration

**Problema:** Se a API retorna mensagens diferentes ("e-mail enviado" vs. "e-mail não encontrado"), o agressor pode mapear quais e-mails são usuários do sistema.

**Problema secundário (Timing Attack):** Se a resposta para e-mail existente leva ~750ms (porque envia e-mail) e para inexistente leva ~12ms, o agressor usa a diferença de tempo para descobrir usuários.

**Solução:** Equalizar o tempo de resposta

```
┌─────────────────────────────────────────────────────────┐
│            CONTROLE DE TEMPO DE RESPOSTA                 │
│                                                         │
│  start = Date.now()                                     │
│                                                         │
│  // Processar solicitação (busca + envio de e-mail)     │
│                                                         │
│  elapsed = Date.now() - start                           │
│  TARGET_TIME = 1500ms                                   │
│                                                         │
│  if (elapsed < TARGET_TIME) {                           │
│      sleep(TARGET_TIME - elapsed)                       │
│  }                                                      │
│                                                         │
│  // Retornar resposta padronizada                       │
│  return "Se este e-mail está cadastrado, você           │
│          receberá as instruções."                        │
└─────────────────────────────────────────────────────────┘
```

**Resultado:**

| Cenário           | Tempo de Resposta (antes) | Tempo de Resposta (depois) |
|-------------------|---------------------------|----------------------------|
| E-mail existente  | ~750ms                    | ~1.520ms                   |
| E-mail inexistente| ~12ms                     | ~1.520ms                   |

> **Nota:** Um acréscimo de 1.5s no reset de senha é aceitável — o usuário fará essa operação raramente e ainda precisará abrir o e-mail.

#### 3.1.3 Geração Segura de Token

**Problema:** `Math.random()` e funções `random()` padrão das linguagens não são criptograficamente seguras. Computadores são determinísticos; funções `random` comuns usam fontes previsíveis (relógio do sistema, estado da memória).

**Solução:** Utilizar CSPRNG (Cryptographically Secure Pseudo Random Number Generator)

| Linguagem  | Função Insegura (NÃO USAR) | Função Segura (USAR)                       |
|------------|-----------------------------|---------------------------------------------|
| JavaScript | `Math.random()`             | `crypto.randomBytes()` (Node.js)            |
| Python     | `random`                    | `secrets.token_hex()` / `os.urandom()`     |
| PHP        | `rand()`, `mt_rand()`       | `random_bytes()`                            |
| Java       | `Math.random()`             | `java.security.SecureRandom`                |
| Go         | `math/rand`                 | `crypto/rand`                               |
| Ruby       | `rand`                      | `SecureRandom`                              |
| C#         | `System.Random`             | `RandomNumberGenerator` (System.Security)   |

**Implementação de referência (Node.js):**

```javascript
const crypto = require('crypto');

// Token seguro: 32 bytes em Base64URL
const token = crypto.randomBytes(32).toString('base64url');
```

> **Por que 32 bytes?** Oferece 256 bits de entropia — inviável de adivinhar por força bruta mesmo com recursos computacionais massivos.

#### 3.1.4 Proteção contra Injeção de Header Host

**Problema:** Construir URLs de reset usando `req.headers.host` permite que um agressor injete um host malicioso:

```
Ataque:
  $ curl -H "Host: hacker.com" https://meusite.com/reset-password?email=vitima@site.com

Resultado no e-mail da vítima:
  "Para resetar sua senha, clique: https://hacker.com/new-password?token=abc123"
```

O agressor monitora os logs do `hacker.com`, captura o token e usa-o para resetar a senha no domínio real.

**Solução:**

| Abordagem                  | Descrição                                                        |
|----------------------------|------------------------------------------------------------------|
| Host fixo em configuração  | Definir o host em variável de ambiente ou arquivo de config     |
| Whitelist de hosts válidos | Validar `req.headers.host` contra lista de hosts permitidos      |
| Log silencioso de hosts inválidos | Responder normalmente (mesmo tempo) mas NÃO enviar e-mail |

**Implementação de referência (Node.js):**

```javascript
// Nunca use req.headers.host para montar URLs
// const host = req.headers.host; // ❌ INSEGURO

const APP_HOST = process.env.APP_URL || 'https://meusite.com'; // ✅ SEGURO
const resetUrl = `${APP_HOST}/new-password?token=${token}`;
```

---

### 3.2 Componente 2: Expiração de Token

#### 3.2.1 Requisitos

| ID       | Requisito                                                        | Prioridade |
|----------|------------------------------------------------------------------|------------|
| RESET-05 | Todo token de reset deve ter tempo de expiração (máx. 30 min)   | Alta       |
| RESET-06 | Armazenar o momento da criação (reset_time), não o da expiração  | Média      |

#### 3.2.2 Design

**Estrutura da tabela:**

```sql
ALTER TABLE users ADD COLUMN reset_token TEXT;
ALTER TABLE users ADD COLUMN reset_time INTEGER;
```

**Por que armazenar `reset_time` (momento de criação) em vez de `expires_at`?**

1. Permite alterar o tempo de expiração posteriormente sem migrar tokens existentes
2. Permite validar tokens contra uma janela temporal (limite inferior e superior)
3. Impede injeção de `reset_time` futuro — o token não pode valer "daqui a uma semana"

**Consulta de validação:**

```sql
SELECT * FROM users
WHERE reset_token = ?
  AND reset_time >= ?   -- Limite inferior: não aceitar tokens muito antigos
  AND reset_time <= ?;  -- Limite superior: não aceitar tokens futuros
```

```
┌──────────────────────────────────────────────────┐
│           JANELA DE VALIDAÇÃO DO TOKEN            │
│                                                  │
│  Agora (now)                                     │
│     │                                            │
│     ◀──── Janela válida (ex: 30 min) ────▶       │
│     │                                            │
│  reset_time                        now - 30min   │
│  (criação)                         (expiração)   │
│                                                  │
│  ✅ Token dentro da janela → Aceitar              │
│  ❌ Token antes da janela → Expirado              │
│  ❌ Token após agora (futuro) → Rejeitar          │
└──────────────────────────────────────────────────┘
```

---

### 3.3 Componente 3: Página de Reset de Senha

#### 3.3.1 Requisitos

| ID       | Requisito                                                                | Prioridade |
|----------|--------------------------------------------------------------------------|------------|
| RESET-07 | Implementar rate limit por IP na página de reset (ex: 5 tentativas/min) | Alta       |
| RESET-08 | Solicitar senha e confirmação de senha (campo duplo obrigatório)         | Alta       |
| RESET-09 | Se MFA estiver habilitado, exigir MFA antes de permitir o reset         | Alta       |
| RESET-10 | Não carregar recursos externos (JS, CSS, fontes, analytics, tag manager) | Alta       |
| RESET-11 | Incluir header `Referrer-Policy: no-referrer` na página                  | Alta       |
| RESET-12 | Minimizar links na página (logotipo sem link, sem navegação)             | Média      |

#### 3.3.2 Construção Segura da Página

**Regra fundamental: Modo Paranóico — Nada Externo**

A página de reset de senha recebe um token secreto na URL. Qualquer código externo injetado nessa página pode:

- Ler `window.location` e capturar o token
- Enviar o token para um servidor do agressor
- Comprometer o processo de reset sem que o usuário perceba

**Recursos PROIBIDOS na página de reset:**

| Recurso                  | Motivo                                                  |
|--------------------------|---------------------------------------------------------|
| JavaScript de CDN        | Pode ser comprometido e ler `location`                  |
| CSS de CDN               | Pode ser comprometido e injetar código                  |
| Google Analytics         | Envia dados para terceiros, inclui JS externo           |
| Tag Manager              | Envia dados para terceiros, inclui JS externo           |
| Fontes externas          | Carregam recursos de terceiros                          |
| Qualquer script externo  | Superfície de ataque                                    |

**Header Referrer-Policy: no-referrer**

**Problema:** Se a página de reset contém links (ex: "Política de Privacidade"), ao clicar o navegador envia o header `Referer` com a URL completa — incluindo o token.

```
Cenário de ataque:
  1. Página de reset: https://meusite.com/reset?token=SEGREDO123
  2. Usuário clica em "Política de Privacidade"
  3. Navegador envia: Referer: https://meusite.com/reset?token=SEGREDO123
  4. CMS da página de privacidade tem vulnerabilidade
  5. Hacker lê $_SERVER['HTTP_REFERER'] e captura o token
```

**Solução:**

```php
<?php
// No topo da página de reset de senha
header("Referrer-Policy: no-referrer");
?>
```

**Resultado:** O header `Referer` não será enviado em nenhuma navegação a partir desta página.

#### 3.3.3 Design da Interface

```
┌──────────────────────────────────────┐
│           [LOGOTIPO]                 │  ← Sem link
│                                      │
│  ┌────────────────────────────────┐  │
│  │  Nova Senha                    │  │
│  │  [________________]  👁        │  │
│  │                                │  │
│  │  Confirmar Senha               │  │
│  │  [________________]  👁        │  │
│  │                                │  │
│  │  [   Redefinir Senha   ]       │  │
│  └────────────────────────────────┘  │
│                                      │
│  ❌ Sem links de navegação           │
│  ❌ Sem footer                       │
│  ❌ Sem menu                         │
│  ❌ Sem recursos externos            │
└──────────────────────────────────────┘
```

> **Nota:** O usuário chegou a esta página via e-mail, não estava navegando no site. Links de "voltar" ou "cancelar" não são necessários.

#### 3.3.4 Por que Confirmação de Senha no Reset?

Diferente do cadastro (onde o gerenciador de senhas ou a repetição de uma senha conhecida facilitam), no reset:

- O usuário **esqueceu a senha** ou **não consegue digitar corretamente**
- Sem confirmação, ele pode digitar uma senha com erro (Caps Lock, typo)
- Terá que fazer reset novamente no dia seguinte
- Confirmação garante que ele consegue reproduzir a senha corretamente

---

### 3.4 Componente 4: Pós-Reset (Ações Pós-Senha Alterada)

#### 3.4.1 Requisitos

| ID       | Requisito                                                                   | Prioridade |
|----------|-----------------------------------------------------------------------------|------------|
| RESET-13 | Enviar notificação por e-mail imediata após alteração de senha             | Alta       |
| RESET-14 | Invalidar todas as sessões ativas do usuário                                | Alta       |
| RESET-15 | Redirecionar para tela de login (NÃO autenticar automaticamente)            | Alta       |

#### 3.4.2 Notificação por E-mail

**Objetivo:** Iniciar a corrida contra o tempo entre o usuário legítimo e o agressor.

| Cenário                    | Sem Notificação                              | Com Notificação                           |
|----------------------------|----------------------------------------------|-------------------------------------------|
| Senha trocada pelo dono    | Sem impacto                                  | Confirmação tranquila                     |
| Senha trocada por agressor | Usuário descobre após 2 semanas             | Usuário descobre em minutos               |

**Conteúdo do e-mail de notificação:**

> "Sua senha foi alterada recentemente. Se você não realizou esta alteração, acesse imediatamente e troque sua senha ou entre em contato com o suporte."

#### 3.4.3 Invalidação de Sessões

**Motivo:** Usuários frequentemente compartilham senhas (mesmo que não devessem). Ao trocar a senha, todas as sessões devem ser encerradas.

```
Cenário:
  1. Usuário compartilha senha com colega
  2. Colega é demitido ou muda de departamento
  3. Usuário troca a senha
  4. Todas as sessões são invalidadas → Colega perde acesso
```

**Implementação:**

```sql
-- Ao alterar a senha, invalidar todas as sessões
DELETE FROM sessions WHERE user_id = ?;

-- Atualizar senha
UPDATE users SET password = ? WHERE id = ?;
```

#### 3.4.4 Por que NÃO Autenticar Automaticamente?

| Critério                    | Autenticar Auto  | Redirecionar para Login |
|-----------------------------|-------------------|-------------------------|
| Superfície de ataque        | Maior (2 pontos)  | Menor (1 ponto)         |
| Manutenção do código        | Alterar em 2 lugares | Alterar em 1 lugar   |
| Teste da nova senha         | Não testada       | Testada imediatamente   |
| Consistência                | Fluxo diferente   | Fluxo único             |

> Um único ponto de autenticação reduz a superfície de ataque e simplifica a manutenção.

---

### 3.5 Componente 5: Perguntas de Segurança (NÃO UTILIZAR)

#### 3.5.1 Recomendação

**NÃO utilize perguntas de segurança como mecanismo de recuperação de senha.** Esta seção documenta por que a prática é insegura.

#### 3.5.2 Análise das 5 Características Necessárias

Para que uma pergunta de segurança seja eficaz, ela precisa atender a **todos** os cinco critérios:

| Característica | Descrição                                                                 | Problema Prático                                              |
|----------------|---------------------------------------------------------------------------|---------------------------------------------------------------|
| **Memorável**  | O usuário deve lembrar a resposta                                        | Perguntas muito antigas são esquecidas                        |
| **Consistente**| A resposta não pode mudar ao longo do tempo                               | "Cantor favorito", "Sabor de bolo favorito" mudam             |
| **Aplicável**  | O usuário deve ter uma resposta para a pergunta                           | "Time de basquete favorito" — maioria não tem                 |
| **Confidencial**| A resposta deve ser difícil de descobrir                                 | "Apelido" está na rede social; "Primeiro carro" é deduzível   |
| **Específica** | O usuário deve ter uma única resposta clara na mente                      | "Viagem mais memorável" — várias respostas possíveis           |

> Na prática, é extremamente difícil encontrar perguntas que atendam a todos os 5 critérios simultaneamente para a maioria dos usuários.

#### 3.5.3 Ataque de Pescaria (Phishing de Perguntas)

```
┌─────────────────────────────────────────────────────────┐
│           ATAQUE DE PHISHING DE PERGUNTAS                │
│                                                         │
│  1. Aggressor cria site falso com mesmo tema            │
│  2. Usa as MESMAS perguntas de segurança                │
│  3. Divulga na comunidade de usuários do alvo           │
│  4. Usuários se cadastram no site falso                 │
│  5. Aggressor coleta respostas idênticas                │
│  6. Usa respostas para recuperar contas no alvo real    │
└─────────────────────────────────────────────────────────┘
```

> As pessoas tendem a usar as mesmas respostas para as mesmas perguntas em diferentes sites.

#### 3.5.4 Evidência Acadêmica e Industrial

| Estudo     | Ano | Autores         | Conclusão                                                   |
|------------|-----|-----------------|-------------------------------------------------------------|
| Microsoft  | 2009 | 3 pesquisadores | 16 páginas: perguntas de segurança não são seguras          |
| Google     | 2015 | 5 pesquisadores | 10 páginas: pessoas escolhem as mesmas perguntas e respostas |

**Alternativas seguras a perguntas de segurança:**
- OTP via TOTP (Google Authenticator, etc.)
- OTP via e-mail
- OTP via SMS
- Chaves FIDO2/WebAuthn (Passkeys)
- Códigos de recuperação (backup codes)

---

## 4. Modelo de Dados

### 4.1 Schema — Tabela de Usuários (Campos de Reset)

```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    password        TEXT NOT NULL,           -- Hash Argon2
    reset_token     TEXT,                    -- Token CSPRNG (Base64URL, 32 bytes)
    reset_time      INTEGER,                 -- Timestamp Unix da criação do token
    mfa_enabled     BOOLEAN DEFAULT FALSE,   -- Flag de MFA
    otp_secret      TEXT,                    -- Segredo TOTP (se aplicável)
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índice para busca de token
CREATE INDEX idx_users_reset_token ON users(reset_token);

-- Tabela de sessões
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
```

---

## 5. Checklist de Segurança — Reset de Senha

### 5.1 Pré-Reset (Solicitação)

- [ ] Resposta idêntica para e-mail válido e inválido
- [ ] Tempo de resposta consistente (~1.500ms)
- [ ] Token gerado com CSPRNG (32+ bytes)
- [ ] URL construída com host fixo (nunca do header Host)
- [ ] Whitelist de hosts válidos (se necessário usar header Host)

### 5.2 Token

- [ ] Expiração configurada (recomendado: 30 minutos)
- [ ] Armazenar `reset_time` (momento de criação), não `expires_at`
- [ ] Validação contra janela temporal (limite inferior + superior)
- [ ] Token invalidado após uso (uso único)

### 5.3 Página de Reset

- [ ] Rate limit por IP implementado
- [ ] Senha + Confirmação de Senha (campos obrigatórios)
- [ ] MFA exigido se habilitado para o usuário
- [ ] Nenhum recurso externo carregado (JS, CSS, fontes, analytics)
- [ ] Header `Referrer-Policy: no-referrer` presente
- [ ] Minimizar links (logotipo sem link, sem navegação)

### 5.4 Pós-Reset

- [ ] Notificação por e-mail enviada imediatamente
- [ ] Todas as sessões ativas invalidadas
- [ ] Redirecionar para tela de login (sem auto-autenticação)

### 5.5 Não Implementar

- [ ] Perguntas de segurança (inseguras, substituídas por MFA)

---

## 6. Considerações de Segurança

### 6.1 Ameaças e Mitigações

| Ameaça                                | Mitigação                                               | Ref.        |
|---------------------------------------|---------------------------------------------------------|-------------|
| User Enumeration                      | Resposta + tempo consistentes                          | RESET-01/02 |
| Timing Attack                         | Equalização do tempo de resposta (~1.500ms)            | RESET-02    |
| Token previsível                      | CSPRNG para geração (32 bytes)                         | RESET-04    |
| Header Host Injection                 | Host fixo em configuração ou whitelist                  | §3.1.4      |
| Token sem expiração                   | `reset_time` + janela de validação                     | RESET-05    |
| Vazamento de token via Referer        | `Referrer-Policy: no-referrer`                         | RESET-11    |
| Código externo captura token          | Zero recursos externos na página de reset               | RESET-10    |
| Força bruta de token                  | Rate limit por IP                                      | RESET-07    |
| Phishing de perguntas de segurança    | Não utilizar perguntas de segurança                    | §3.5        |
| Sessão sobrevivente ao reset          | Invalidar todas as sessões                             | RESET-14    |
| Detecção tardia de comprometimento    | Notificação por e-mail imediata                        | RESET-13    |

### 6.2 Referência Rápida de CSPRNG por Linguagem

| Linguagem    | Módulo/Função                                        |
|--------------|------------------------------------------------------|
| Node.js      | `crypto.randomBytes(size)`                           |
| Python       | `secrets.token_bytes(size)`, `os.urandom(size)`      |
| PHP          | `random_bytes(size)`                                 |
| Java         | `new java.security.SecureRandom().nextBytes(bytes)`  |
| Go           | `crypto/rand.Read(bytes)`                            |
| Ruby         | `SecureRandom.random_bytes(size)`                    |
| C#/.NET      | `RandomNumberGenerator.GetBytes(bytes)`               |
| Rust         | `rand::thread_rng().fill_bytes(&mut bytes)`          |

---

## 7. Referências

### 7.1 Estudos Acadêmicos

- Microsoft Research (2009) — "Users Are Not the Enemy" — Análise de 16 páginas sobre insegurança de perguntas de segurança
- Google Research (2015) — Estudo de 10 páginas sobre eficácia de perguntas de segurança

### 7.2 Especificações

| Padrão             | Descrição                                            |
|--------------------|------------------------------------------------------|
| Referrer-Policy    | W3C — `no-referrer` para páginas sensíveis          |
| CSPRNG             | NIST SP 800-90A — Geradores de números aleatórios   |

---

## 8. Histórico de Revisões

| Versão | Data       | Descrição                                            |
|--------|------------|------------------------------------------------------|
| 1.0    | 2026-04-08 | Versão inicial — Baseado no curso "Segurança Para Devs" |
