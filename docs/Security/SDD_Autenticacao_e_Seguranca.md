# SOFTWARE DESIGN DOCUMENT (SDD)

## Sistema de Autenticação e Segurança para Aplicações Web

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Sistema de Autenticação Multi-Fator com Login/Senha, OTP e FIDO2 |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design arquitetural e os requisitos técnicos para a implementação de um sistema de autenticação seguro para aplicações web. O design abrange autenticação por login/senha, autenticação multi-fator (MFA), One-Time Password (OTP) via TOTP e autenticação sem senha utilizando chaves FIDO2/WebAuthn.

### 1.2 Escopo

O sistema descrito neste SDD abrange:

- Autenticação primária via login e senha com boas práticas de segurança
- Armazenamento seguro de senhas utilizando funções de hashing resistentes (Argon2)
- Migração de hashes legados (SHA-256) para Argon2 com transparência ao usuário
- Validação de força de senha e verificação contra vazamentos (Have I Been Pwned API)
- Implementação de MFA via TOTP (Google Authenticator, Microsoft Authenticator, Ente, etc.)
- Implementação de autenticação sem senha via FIDO2/WebAuthn (Passkeys)
- Boas práticas para reautenticação em operações sensíveis

### 1.3 Definições e Acrônimos

| Termo       | Definição                                                    |
|-------------|--------------------------------------------------------------|
| **SDD**     | Software Design Document                                     |
| **MFA**     | Multi-Factor Authentication (Autenticação Multi-Fator)       |
| **OTP**     | One-Time Password (Senha de Uso Único)                       |
| **TOTP**    | Time-based One-Time Password                                 |
| **HOTP**    | HMAC-based One-Time Password                                 |
| **FIDO2**   | Fast Identity Online 2                                       |
| **WebAuthn**| Web Authentication API (padrão W3C)                          |
| **Hash**    | Função de dispersão criptográfica unidirecional              |
| **Salt**    | Valor aleatório global concatenado à senha antes do hashing   |
| **Pepper**  | Valor aleatório único por senha concatenado antes do hashing  |
| **Rainbow Table** | Tabela pré-computada de hashes para ataque de dicionário |
| **CSRF**    | Cross-Site Request Forgery                                   |

---

## 2. Visão Geral de Arquitetura

### 2.1 Fatores de Autenticação

O sistema suporta múltiplos fatores de autenticação, classificados em cinco categorias:

```
┌─────────────────────────────────────────────────────────────────┐
│                    FATORES DE AUTENTICAÇÃO                      │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│ Algo que você│ Algo que você│ Algo que você│ Onde você está     │
│    SABE      │     TEM      │      É       │                    │
├──────────────┼──────────────┼──────────────┼────────────────────┤
│ - Senha      │ - Token OTP  │ - Impressão  │ - Endereço IP      │
│ - PIN        │ - Token FIDO │   digital    │ - Geolocalização   │
│ - Pergunta de│ - Smart Card │ - Reconhec.  │ - Geofencing       │
│   segurança  │ - Certificado│   facial     │                    │
│              │ - SMS        │ - Íris       │                    │
│              │ - E-mail     │              │                    │
│              │ - Ligação    │              │                    │
│              │   telefônica │              │                    │
├──────────────┴──────────────┴──────────────┴────────────────────┤
│                 Algo que você FAZ                               │
├─────────────────────────────────────────────────────────────────┤
│ - Perfil comportamental (ritmo de digitação, uso do mouse)      │
│ - Análise de marcha (acesso físico)                            │
└─────────────────────────────────────────────────────────────────┘
```

**Princípio fundamental:** A combinação de múltiplos fatores torna o sistema exponencialmente mais seguro, elevando drasticamente o custo de um ataque bem-sucedido.

### 2.2 Arquitetura do Fluxo de Autenticação

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────┐
│  Cliente │────▶│  Servidor    │────▶│  Banco de     │────▶│ Tabela   │
│ (Nav./   │◀────│  Web (API)   │◀────│  Dados        │◀────│ Usuários │
│  App)    │     │              │     │               │     │ Tabela   │
│          │     │              │     │               │     │ Chaves   │
│          │     │              │     │               │     │ Tabela   │
│          │     │              │     │               │     │ OTP      │
└──────────┘     └──────────────┘     └───────────────┘     └──────────┘
      │                │                      │
      │                ▼                      ▼
      │         ┌──────────────┐     ┌───────────────┐
      │         │ HIBP API     │     │ TOTP Engine   │
      │         │ (Vazamentos) │     │ (Geração OTP) │
      │         └──────────────┘     └───────────────┘
      │
      ▼
┌──────────┐
│ WebAuthn │
│ (FIDO2)  │
│ Authenticator
└──────────┘
```

---

## 3. Design de Componentes

### 3.1 Componente 1: Autenticação por Login e Senha

#### 3.1.1 Requisitos de Segurança

| ID    | Requisito                                                                 | Prioridade |
|-------|---------------------------------------------------------------------------|------------|
| AUTH-01 | Separar logins administrativos de logins de usuário em estruturas distintas | Alta      |
| AUTH-02 | Exigir HTTPS em todo o fluxo de autenticação (idealmente em todo o site)  | Alta      |
| AUTH-03 | User ID não deve ser sequencial (prevenção contra User Enumeration)      | Média     |
| AUTH-04 | Validar e-mail do usuário via confirmação por e-mail                      | Alta      |
| AUTH-05 | Senha: mínimo de 8 caracteres, máximo de 64 caracteres                    | Alta      |
| AUTH-06 | Validação de comprimento de senha deve ocorrer no servidor                | Alta      |
| AUTH-07 | Nunca truncar senhas — retornar erro caso exceda o máximo                 | Alta      |

#### 3.1.2 Justificativa do Mínimo de 8 Caracteres

| Comprimento | Ataque Online (100 req/h) | Hash Seguro (offline) | Hash Fraco (offline) |
|-------------|---------------------------|----------------------|---------------------|
| 7 caracteres| 11 anos                   | 17 minutos           | < 1 segundo         |
| 8 caracteres| 4 meses                   | 3 horas              | < 1 segundo         |

> Um único caractere adicional eleva exponencialmente o custo do ataque.

#### 3.1.3 Validação de Força de Senha (zxcvbn)

- **Biblioteca recomendada:** zxcvbn (desenvolvida pelo Dropbox)
- **Disponível em:** Python, JavaScript/TypeScript, PHP, Java, Go, Ruby, .NET e outras
- **Funcionalidades:**
  - Score de 0 a 4 (aceitar apenas score >= 3)
  - Detecção de padrões fracos (sequências, repetições, datas)
  - Dicionário baseado em dados do usuário (nome, e-mail, data de nascimento)
  - Integração com a API do Have I Been Pwned para senhas vazadas
  - Estimativa de tempo para quebra da senha (online e offline)

#### 3.1.4 Verificação contra Vazamentos (Have I Been Pwned API)

**Protocolo de verificação:**

```
1. Calcular hash SHA-1 da senha
2. Extrair os 5 primeiros caracteres do hash
3. Enviar consulta à API: https://api.pwnedpasswords.com/range/{prefix}
4. Receber lista de sufixos de senhas vazadas
5. Verificar se o sufixo restante do hash está na lista
6. Se presente → rejeitar senha (senha comprometida)
```

> **Nota:** A API utiliza k-anonymity: o servidor recebe apenas o prefixo, nunca a senha completa ou o hash completo.

#### 3.1.5 Validação de Campos (Client-side e Server-side)

**Validação obrigatória no servidor:**

| Campo              | Tipo     | Restrições                                  |
|--------------------|----------|---------------------------------------------|
| E-mail             | `email`  | Obrigatório, formato válido, único          |
| Senha              | `text`   | Obrigatório, 8-64 caracteres                |
| Confirmação de Senha | `text` | Obrigatório, deve ser idêntica à senha     |

**Validação no client-side (UX complementar):**
- Verificação de coincidência entre senha e confirmação
- Feedback visual via zxcvbn (score em tempo real)
- `maxLength="64"` no campo (bloqueio de UX, não de segurança)

---

### 3.2 Componente 2: Armazenamento Seguro de Senhas

#### 3.2.1 Problema

O acesso ao banco de dados pode não ser garantido durante toda a vida útil do software. Motivos:
- Funcionários com acesso ao banco não devem ter acesso a senhas de usuários
- Vazamentos de dados podem expor o banco de dados
- A forma de armazenamento impacta diretamente na segurança

#### 3.2.2 Evolução das Técnicas de Armazenamento

**Nível 1 — Hash Simples (INSUFICIENTE):**

```python
import hashlib
sha256(password).hexdigest()
```

- Vulnerável a ataques de dicionário e Rainbow Tables
- A mesma senha sempre gera o mesmo hash (comparável entre usuários)

**Nível 2 — Hash com Salt (GLOBAL):**

```python
sha256(SALT + password).hexdigest()
```

- `SALT`: string secreta global (variável de ambiente)
- Protege contra Rainbow Tables genéricas
- Vulnerabilidade: um dicionário com o salt descoberto compromete todos os usuários

**Nível 3 — Hash com Salt + Pepper (POR USUÁRIO):**

```python
# Pepper: valor aleatório e único por usuário
pepper = secrets.token_hex(16)  # 16 bytes hexadecimais
hashed = sha256(pepper + SALT + password).hexdigest()
# Armazenar: "pepper,hashed"
```

- `Pepper`: valor aleatório único por senha (gerado com entropia criptográfica)
- O atacante precisa gerar um dicionário separado para cada usuário
- Para 10.000 usuários, o custo do ataque aumenta 10.000x

#### 3.2.3 Funções Random Seguras por Linguagem

| Linguagem | Função Insegura (NÃO USAR)        | Função Segura (USAR)                       |
|-----------|-----------------------------------|---------------------------------------------|
| Python    | `random`                          | `secrets`                                   |
| PHP       | `rand()`, `array_rand()`          | `random_bytes()`                            |
| Java      | `Math.random()`                   | `java.security.SecureRandom`                |
| JavaScript| `Math.random()`                   | `crypto.randomBytes()` (Node.js)            |
| C#        | `System.Random`                   | `System.Security.Cryptography.RandomNumberGenerator` |
| Ruby      | `rand`                            | `SecureRandom`                              |
| Go        | `math/rand`                       | `crypto/rand`                               |

#### 3.2.4 Algoritmo Recomendado: Argon2

**Argon2** é o vencedor da Password Hashing Competition (2013-2015), desenvolvido pela Universidade de Luxemburgo.

**Características:**
- Implementa internamente Salt e Pepper (por usuário)
- Configurável: paralelismo, custo de memória, iterações
- Resistente a ataques por GPU/ASIC (custo de memória alto)

**Configuração recomendada:**

| Parâmetro           | Valor Mínimo | Valor Recomendado |
|---------------------|-------------|-------------------|
| Custo de Memória    | 19 MB       | 64 MB             |
| Iterações           | 2           | 3                 |
| Fator de Paralelismo| 1           | 4                 |
| Tamanho do Salt     | 16 bytes    | 24 bytes          |

**Hierarquia de algoritmos para escolha:**

```
Argon2 (recomendado)
   │
   ├── Disponível? → USE Argon2
   │
   └── Não disponível? → scrypt (alternativa comparável)
                           │
                           └── Não disponível? → bcrypt (mínimo aceitável,
                                                   legados)
```

**Implementação de referência (Python):**

```python
from argon2 import PasswordHasher

ph = PasswordHasher(
    time_cost=3,          # Iterações
    memory_cost=65536,    # 64 MB
    parallelism=4         # Threads
)

# Hashing
hashed = ph.hash(password)

# Verificação
try:
    ph.verify(hashed, password)
except:
    # Senha inválida
```

---

### 3.3 Componente 3: Migração de Hashes Legados

#### 3.3.1 Problema

Sistemas existentes podem utilizar algoritmos de hashing obsoletos (MD5, SHA-1, SHA-256 sem Salt/Pepper). É necessário migrar para Argon2 sem interromper o acesso dos usuários.

#### 3.3.2 Estratégia: Migração Transparente (Lazy Migration)

```
┌─────────────────────────────────────────────────────────┐
│                  FLUXO DE LOGIN                          │
│                                                         │
│  1. Receber senha do usuário                            │
│  2. Buscar hash no banco de dados                       │
│  3. Verificar tipo do hash:                             │
│     ├── Argon2? → Verificar com Argon2                  │
│     └── Legado (SHA-256)? → Verificar com SHA-256      │
│         ├── Inválido → Retornar erro                    │
│         └── Válido → Autenticar usuário                 │
│                    └── Re-hash com Argon2               │
│                        └── Atualizar banco de dados     │
└─────────────────────────────────────────────────────────┘
```

**Implementação de referência (Python):**

```python
def login(email, password):
    hashed = db.query("SELECT password FROM users WHERE email = ?", (email,))
    if not hashed:
        return False

    try:
        # Tentar Argon2 primeiro
        if ph.verify(hashed, password):
            return user_id
    except:
        pass

    # Fallback: hash legado (SHA-256)
    import hashlib
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()

    if legacy_hash == hashed:
        # Upgrade: re-hash com Argon2
        new_hash = ph.hash(password)
        db.execute("UPDATE users SET password = ? WHERE id = ?", (new_hash, user_id))

        # Marcar flag de upgrade (opcional)
        print("Upgrading password hash")

        return user_id

    return False
```

**Pontos críticos:**
- Manter o bloco de fallback até que todos os usuários tenham feito login ao menos uma vez
- Monitorar logs para identificar quando todos os hashes foram migrados
- Após migração completa, remover o bloco de compatibilidade legada

---

### 3.4 Componente 4: Autenticação Multi-Fator (MFA) — OTP/TOTP

#### 3.4.1 Visão Geral

A autenticação via TOTP (Time-based One-Time Password) adiciona um segundo fator ("algo que você tem") ao processo de autenticação.

**Protocolo:** `otpauth://totp/`

**Implementação compatível:** Google Authenticator, Microsoft Authenticator, Ente, Authy, Alt, entre outros.

#### 3.4.2 Design do Fluxo

```
┌───────────┐       ┌──────────────┐       ┌──────────────┐
│  Servidor  │       │   Cliente    │       │  App OTP     │
│            │       │  (Navegador) │       │ (Celular)    │
│            │       │              │       │              │
│ 1. Gerar   │──────▶│              │       │              │
│    segredo  │       │              │       │              │
│    OTP     │       │              │       │              │
│            │       │ 2. Exibir    │       │              │
│            │       │    QR Code   │       │              │
│            │       │              │──────▶│              │
│            │       │              │ 3. Scan│              │
│            │       │              │ QR Code│              │
│            │       │              │       │ 4. Gerar     │
│            │       │              │       │    código     │
│            │       │ 5. Digitar   │       │    TOTP       │
│            │       │    código    │◀──────│    (30s)      │
│            │       │              │       │              │
│ 6. Validar │◀──────│    código    │       │              │
│    TOTP.now│       │              │       │              │
│            │──────▶│              │       │              │
│ 7. Result  │       │ 8. Acesso    │       │              │
│            │       │    concedido │       │              │
└───────────┘       └──────────────┘       └──────────────┘
```

#### 3.4.3 Especificação Técnica

| Parâmetro        | Valor                                           |
|------------------|-------------------------------------------------|
| Tipo             | TOTP (Time-based) — 99% dos casos de uso       |
| Duração do código| 30 segundos (padrão, configurável)              |
| Geração de segredo| `pyotp.random_base32()` (criptograficamente seguro) |
| URI de provisionamento | `otpauth://totp/{issuer}:{user}?secret={secret}&issuer={issuer}` |

**Implementação de referência (Python):**

```python
import pyotp
import segno

# Geração do segredo (armazenar no banco de dados por usuário)
secret = pyotp.random_base32()

# Criação do objeto TOTP
totp = pyotp.TOTP(secret)

# Geração da URI para QR Code
uri = totp.provisioning_uri(name="usuario@exemplo.com", issuer_name="MeuApp")

# Geração do QR Code
qrcode = segno.make(uri)

# Validação do código
def verify_code(user_secret, user_code):
    totp = pyotp.TOTP(user_secret)
    return totp.verify(user_code)
```

#### 3.4.4 Regras de Ativação

1. Exibir QR Code na tela de configuração de MFA
2. Solicitar que o usuário digite um código gerado para confirmar sincronização
3. Validar o primeiro código antes de ativar o MFA
4. Armazenar flag `mfa_enabled = true` no banco de dados apenas após validação
5. Se o dispositivo estiver com relógio errado, o código não será validado — permitir nova tentativa sem bloquear o usuário

---

### 3.5 Componente 5: Autenticação Sem Senha — FIDO2/WebAuthn

#### 3.5.1 Visão Geral

**WebAuthn** (Web Authentication API) é um padrão W3C/FIDO Alliance aprovado em 2018. Permite autenticação utilizando chaves criptográficas (Passkeys) armazenadas no dispositivo do usuário ou em gerenciadores de senhas.

**API:** `navigator.credentials` (browser nativo)

**Bibliotecas recomendadas:**
- Repositório de referência: `awesomewebauthn` (coleção de bibliotecas, tutoriais e demos)
- Server (Python): `py_webauthn`
- Client (JavaScript): `simplewebauthn`

**Disponibilidade por linguagem:** Python, PHP, Go (várias), Java, Elixir, Ruby, Rust, Node.js, .NET, Swift, Kotlin.

#### 3.5.2 Design do Fluxo de Registro

```
┌───────────┐       ┌──────────────┐       ┌──────────────┐
│  Servidor  │       │   Cliente    │       │  Authenticator│
│            │       │  (Navegador) │       │ (FIDO2)      │
│            │       │              │       │              │
│ 1. Gerar   │──────▶│              │       │              │
│    Challenge│      │              │       │              │
│    (random) │      │              │       │              │
│            │       │ 2. Receber   │       │              │
│            │       │    options   │       │              │
│            │       │              │──────▶│              │
│            │       │ 3. Gerar     │       │              │
│            │       │    chave     │       │              │
│            │       │    cripto.   │       │              │
│            │       │              │◀──────│              │
│            │       │ 4. Retornar  │       │              │
│            │       │    chave pub.│       │              │
│            │       │    + signed  │       │              │
│            │       │    challenge │       │              │
│ 5. Validar │◀──────│              │       │              │
│    challenge│      │              │       │              │
│ 6. Salvar  │       │              │       │              │
│    CredID +│       │              │       │              │
│    PubKey  │       │              │       │              │
└───────────┘       └──────────────┘       └──────────────┘
```

**Parâmetros do `generateRegistrationOptions`:**

| Parâmetro        | Descrição                                          | Obrigatório |
|------------------|----------------------------------------------------|-------------|
| `rpID`           | Domínio da aplicação (não pode ser IP)             | Sim         |
| `rpName`         | Nome de exibição da aplicação                      | Sim         |
| `userID`         | ID do usuário em bytes                             | Sim         |
| `userName`       | Identificador do usuário (e-mail)                  | Sim         |
| `userDisplayName`| Nome de exibição do usuário                        | Opcional    |
| `challenge`      | Valor aleatório em bytes (guardar na sessão)       | Sim         |

#### 3.5.3 Design do Fluxo de Autenticação (Login)

```
┌───────────┐       ┌──────────────┐       ┌──────────────┐
│  Servidor  │       │   Cliente    │       │  Authenticator│
│            │       │  (Navegador) │       │ (FIDO2)      │
│            │       │              │       │              │
│ 1. Gerar   │──────▶│              │       │              │
│    Challenge│      │              │       │              │
│            │       │ 2. Receber   │       │              │
│            │       │    options   │       │              │
│            │       │              │──────▶│              │
│            │       │ 3. Selecionar│       │              │
│            │       │    chave     │       │              │
│            │       │    e assinar │       │              │
│            │       │    challenge │       │              │
│            │       │              │◀──────│              │
│            │       │ 4. Enviar    │       │              │
│            │       │    resposta  │       │              │
│ 5. Validar │◀──────│    assinada  │       │              │
│    com PubKey│     │              │       │              │
│            │──────▶│              │       │              │
│ 6. Login OK│       │ 7. Sessão    │       │              │
│            │       │    autenticada│       │              │
└───────────┘       └──────────────┘       └──────────────┘
```

**Parâmetros do `verifyAuthenticationResponse`:**

| Parâmetro              | Descrição                                          |
|------------------------|----------------------------------------------------|
| `challenge`            | Challenge enviado ao cliente                        |
| `expectedOrigin`       | Origem esperada (ex: `https://localhost:5000`)      |
| `expectedRPID`         | Domínio da aplicação                               |
| `credentialPublicKey`  | Chave pública salva no banco                       |
| `credentialID`         | ID da credencial (identifica a chave do usuário)   |
| `currentSignCount`     | Contador de autenticações (anti-replay, default: 0)|

#### 3.5.4 Modelo de Dados — Tabela de Chaves

```sql
CREATE TABLE user_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    credential_id   TEXT NOT NULL,
    public_key      TEXT NOT NULL,
    sign_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

> Um usuário pode ter múltiplas chaves (computador pessoal, computador do trabalho, celular).

#### 3.5.5 Opções de Verificação do Usuário (User Verification)

| Nível        | Comportamento                                                | Uso Recomendado                 |
|--------------|--------------------------------------------------------------|----------------------------------|
| `preferred`  | Solicita verificação se disponível; não falha se ausente    | Padrão, aplicações gerais       |
| `required`   | Exige verificação (PIN, biometria, senha do SO); falha se não disponível | Bancos, fintechs, governo |
| `discouraged`| Não solicita verificação                                    | Social media, baixo risco        |

**Implementação:**

```python
# No registration options:
AuthenticatorSelectionCriteria(
    user_verification=UserVerificationRequirement.REQUIRED
)

# Na verificação:
verify_registration_response(
    ...,
    require_user_verification=True
)
```

#### 3.5.6 Boas Práticas para MFA com WebAuthn

1. **Não exigir MFA imediatamente após login FIDO2** — a chave FIDO já é um fator forte
2. **Pedir segundo fator em operações sensíveis** (transferências, alteração de dados críticos)
3. **Não utilizar IP como endereço (`rpID`)** — deve ser um domínio registrado

---

### 3.6 Componente 6: Reautenticação em Operações Sensíveis

#### 3.6.1 Requisito

O sistema deve solicitar reautenticação do usuário em operações sensíveis, mesmo que o usuário já esteja logado.

#### 3.6.2 Operações que Requerem Reautenticação

| Operação                    | Motivo                                                 |
|-----------------------------|--------------------------------------------------------|
| Alteração de senha          | Impedir que agressor troque a senha de sessão abandonada |
| Alteração de e-mail         | Impedir redirecionamento de recuperação para e-mail do agressor |
| Compras/envios para novo endereço | Impedir fraudes com sessões abandonadas        |
| Transferências bancárias    | Proteger contra acesso físico não autorizado            |
| Exibição de dados sensíveis | Proteger informações confidenciais                     |

#### 3.6.3 Design do Fluxo

```
┌───────────────────────────────────────────────────┐
│            Operação Sensível Solicitada            │
└───────────────────────┬───────────────────────────┘
                        ▼
┌───────────────────────────────────────────────────┐
│         Solicitar Reautenticação                   │
│  - Senha atual                                    │
│  - OU código OTP (se MFA habilitado)              │
│  - OU verificação FIDO2 (se disponível)           │
└───────────────────────┬───────────────────────────┘
                        ▼
              ┌─────────┴─────────┐
              │  Validado?         │
              ├─── SIM ───────────▶ Executar operação
              └─── NÃO ───────────▶ Bloquear e registrar tentativa
```

---

## 4. Modelo de Dados

### 4.1 Esquema do Banco de Dados

```sql
-- Tabela de usuários
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    password        TEXT NOT NULL,        -- Hash Argon2
    otp_secret      TEXT,                  -- Segredo TOTP (criptografado)
    mfa_enabled     BOOLEAN DEFAULT FALSE, -- Flag de MFA ativo
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de chaves FIDO2 (WebAuthn)
CREATE TABLE user_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    credential_id   TEXT NOT NULL UNIQUE,
    public_key      TEXT NOT NULL,
    sign_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tabela de sessões (opcional, para controle)
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

## 5. Considerações de Segurança

### 5.1 Ameaças e Mitigações

| Ameaça                          | Mitigação                                              | Componente      |
|---------------------------------|--------------------------------------------------------|-----------------|
| Ataque de dicionário            | Argon2 + Salt + Pepper                                 | Armazenamento   |
| Rainbow Table                   | Salt global + Pepper por usuário                       | Armazenamento   |
| Força bruta                     | Máximo de 64 caracteres + rate limiting                | Login           |
| Senhas vazadas                  | Validação via Have I Been Pwned API                    | Cadastro        |
| Vazamento de banco de dados     | Hashing com Argon2 (custo computacional alto)          | Armazenamento   |
| Sessão abandonada               | Reautenticação em operações sensíveis                  | Autenticação    |
| CSRF                            | Validação de `origin` no WebAuthn                      | FIDO2           |
| Man-in-the-middle               | Challenge-response criptográfico                       | FIDO2           |
| Replay attack                   | Contador `signCount` no WebAuthn                       | FIDO2           |
| Dispositivo comprometido        | User Verification (`required`) no registro/login FIDO2 | FIDO2           |

### 5.2 Níveis de Segurança Recomendados por Tipo de Aplicação

| Tipo de Aplicação               | Mínimo Recomendado                                    |
|---------------------------------|-------------------------------------------------------|
| Aplicação de baixo risco        | Senha forte (zxcvbn) + Argon2                         |
| Aplicação de médio risco        | Senha forte + Argon2 + MFA (OTP)                      |
| Aplicação de alto risco         | Senha forte + Argon2 + FIDO2 + User Verification      |
| Infraestrutura crítica          | Senha forte + Argon2 + FIDO2 + User Verification + Geofencing |

---

## 6. Referências e Ferramentas

### 6.1 Bibliotecas e APIs

| Recurso                     | URL/Referência                                          |
|-----------------------------|---------------------------------------------------------|
| zxcvbn (Dropbox)            | `github.com/zxcvbn-ts/zxcvbn`                          |
| Have I Been Pwned API       | `haveibeenpwned.com/API/v3#PwnedPasswords`             |
| Argon2                      | Vencedor da Password Hashing Competition (2015)        |
| PyWebAuthn (Python)         | Biblioteca server-side para WebAuthn                   |
| SimpleWebAuthn (JS)         | Biblioteca client-side para WebAuthn                   |
| Awesome WebAuthn            | `github.com/herrjemand/awesome-webauthn`               |
| PyOTP (Python)              | Biblioteca para TOTP/HOTP                              |

### 6.2 Padrões

| Padrão     | Descrição                                                    |
|------------|--------------------------------------------------------------|
| W3C WebAuthn | Web Authentication API — w3.org/TR/webauthn              |
| FIDO2      | Fast Identity Online 2 — fidoalliance.org                    |
| OTP        | `otpauth://totp/` — RFC 6238 (TOTP), RFC 4226 (HOTP)        |

---

## 7. Histórico de Revisões

| Versão | Data       | Descrição                                            |
|--------|------------|------------------------------------------------------|
| 1.0    | 2026-04-08 | Versão inicial — SDD baseado no curso "Segurança Para Devs" |
