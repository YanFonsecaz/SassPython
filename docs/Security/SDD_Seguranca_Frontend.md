# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança Frontend — JavaScript, CSS, Clickjacking e Sub-Resource Integrity

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança Frontend: Scripts de Terceiros, Clickjacking, CSP e SRI |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para aplicações frontend, abordando a gestão segura de recursos de terceiros (JavaScript, CSS), proteção contra Clickjacking via Content Security Policy (CSP), uso de Sub-Resource Integrity (SRI), e boas práticas para Tag Managers e nomenclatura de classes CSS.

### 1.2 Escopo

- Gestão de JavaScript de terceiros (CDN, código inline, Sub-Resource Integrity)
- Gestão de CSS e vazamento de informações via nomes de classes
- Proteção contra Clickjacking via CSP `frame-ancestors`
- Gestão segura de Tag Managers (Google Tag Manager)
- Remoção do header X-Frame-Options (legado) e uso de CSP

### 1.3 Definições e Acrônimos

| Termo      | Definição                                                        |
|------------|------------------------------------------------------------------|
| **SRI**    | Sub-Resource Integrity — verificação de integridade de recursos |
| **CSP**    | Content Security Policy — política de segurança de conteúdo      |
| **SRI**    | Sub-Resource Integrity — integridade de sub-recurso             |
| **CSP**    | Content Security Policy — política de segurança de conteúdo      |
| **Clickjacking** | Ataque que usa iframe invisível para induzir cliques       |
| **MIME Sniffing** | Prática do navegador de inferir o tipo de arquivo            |
| **Tag Manager** | Ferramenta que gerencia inserção de scripts no frontend     |

---

## 2. Visão Geral de Arquitetura

### 2.1 Modelos de Inclusão de JavaScript de Terceiros

```
┌───────────────────────────────────────────────────────────────────┐
│          MODELOS DE INCLUSÃO DE JAVASCRIPT DE TERCEIROS          │
│                                                                   │
│  Modelo 1: Cópia Local (MAIS SEGURO)                             │
│  ┌─────────────────────────────────────────────────┐              │
│  │  Baixar script → Auditar código → Versionar no    │              │
│  │  repo → Servir do próprio servidor                │              │
│  │                                                  │              │
│  │  Vantagens: Controle total, sem dependência       │              │
│  │  Desvantagens: Sem benefícios de CDN, manutenção  │              │
│  └─────────────────────────────────────────────────┘              │
│                                                                   │
│  Modelo 2: CDN com SRI (EQUILIBRADO)                              │
│  ┌─────────────────────────────────────────────────┐              │
│  │  <script src="https://cdn.com/lib.js"            │              │
│  │    integrity="sha384-ABC123..."                    │              │
│  │    crossorigin="anonymous"></script>              │              │
│  │                                                  │              │
│  │  Vantagens: CDN + integridade garantida           │              │
│  │  Desvantagens: CDN precisa CORS habilitado       │              │
│  └─────────────────────────────────────────────────┘              │
│                                                                   │
│  Modelo 3: CDN sem SRI (INSEGURO)                                │
│  ┌─────────────────────────────────────────────────┐              │
│  │  <script src="https://cdn.com/lib.js"></script>  │              │
│  │                                                  │              │
│  │  Riscos: Código pode ser modificado sem detecção │              │
│  └─────────────────────────────────────────────────┘              │
│                                                                   │
│  Modelo 4: Tag Manager (RISCO ELEVADO)                            │
│  ┌─────────────────────────────────────────────────┐              │
│  │  Código do Tag Manager insere scripts dinamicamente│           │
│  │  Qualquer pessoa com acesso ao TM pode injetar JS │           │
│  │  Equivalente a acesso root ao frontend            │              │
│  └─────────────────────────────────────────────────┘              │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 Arquitetura de Proteção contra Clickjacking

```
┌──────────────────────────────────────────────────────────────────┐
│                    PROTEÇÃO CONTRA CLICKJACKING                   │
│                                                                  │
│  ATAQUE:                                                         │
│  ┌─────────────────────┐     ┌───────────────────────┐            │
│  │  Site do Hacker     │     │  Site Alvo (iframe)   │           │
│  │                     │     │                       │            │
│  │  [Interface fake]   │     │  ┌─────────────────┐  │           │
│  │  ┌─────────────────┐│     │  │ Formulário       │  │           │
│  │  │ pointer-events: ││     │  │ de transferência │  │           │
│  │  │    none         ││     │  │ (escondido)      │  │           │
│  │  │  (transparente) ││     │  └─────────────────┘  │           │
│  │  └────────┬────────┘│     └───────────────────────┘            │
│  │           │ clique │                                       │
│  │           ▼ passa  │                                       │
│  │  para o iframe!   │                                       │
│  └─────────────────────┘                                       │
│                                                                  │
│  DEFESA:                                                        │
│  ┌──────────────────────────────────────────────────┐            │
│  │  Content-Security-Policy: frame-ancestors 'none'  │           │
│  │  → Navegador RECUSA carregar a página em iframe   │           │
│  └──────────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Design de Componentes

### 3.1 Componente 1: Sub-Resource Integrity (SRI)

#### 3.1.1 Requisitos

| ID       | Requisito                                                             | Prioridade |
|----------|-----------------------------------------------------------------------|------------|
| SRI-01   | Usar SRI para todo script carregado de fonte externa (CDN)            | Alta       |
| SRI-02   | Usar SRI para todo CSS carregado de fonte externa                     | Alta       |
| SRI-03   | Usar versões específicas (versionadas) de bibliotecas de terceiros   | Alta       |
| SRI-04   | Carregar recursos externos apenas via HTTPS                           | Alta       |
| SRI-05   | Requisitar CDN com CORS habilitado (`crossorigin="anonymous"`)        | Média      |

#### 3.1.2 Riscos de JavaScript de Terceiros

| Tipo de Risco           | Descrição                                                            |
|-------------------------|----------------------------------------------------------------------|
| **Comportamento**       | Script modificado quebra a funcionalidade da página                  |
| **Execução maliciosa**  | Script hackeado executa código malicioso (roubo de dados, crypto mining) |
| **Vazamento de privacidade** | Script captura dados dos usuários para terceiros                 |
| **Comprometimento de cadeia** | CDN pega código de GitHub; conta do mantenedor é invadida    |

#### 3.1.3 Implementação de SRI

**Formato do atributo `integrity`:**

```html
<script
  src="https://cdn.example.com/lib.js"
  integrity="sha384-{BASE64_HASH}"
  crossorigin="anonymous">
</script>
```

| Componente        | Descrição                                            |
|--------------------|------------------------------------------------------|
| `integrity`        | `sha384-` ou `sha512-` seguido do hash em Base64     |
| `crossorigin`      | `anonymous` — required para que o navegador faça verificação SRI |
| `src`              | URL do recurso na CDN (versão específica)            |

**Algoritmos suportados:**

| Algoritmo | Uso Recomendado                                       |
|-----------|-------------------------------------------------------|
| SHA-256   | Balance entre segurança e tamanho do atributo         |
| SHA-384   | Maior segurança                                       |
| SHA-512   | Máxima segurança                                      |

#### 3.1.4 Cálculo do Hash SRI

**Linha de comando (OpenSSL):**

```bash
openssl dgst -sha384 -binary script.js | base64
```

**Python:**

```python
import hashlib
import base64

with open("script.js", "rb") as f:
    content = f.read()
    hash_digest = hashlib.sha384(content).digest()
    integrity = base64.b64encode(hash_digest).decode()
    print(f"sha384-{integrity}")
```

**Node.js:**

```javascript
const fs = require("fs");
const crypto = require("crypto");

const content = fs.readFileSync("script.js", "utf8");
const hash = crypto.createHash("sha384").update(content).digest("base64");
console.log(`sha384-${hash}`);
```

#### 3.1.5 Comportamento em Caso de Modificação

```
┌──────────────────────────────────────────────────────────────┐
│            COMPORTAMENTO DO SRI EM CASO DE VIOLAÇÃO          │
│                                                              │
│  Hash no atributo integrity: sha384-UAWC...TRN8             │
│  Hash calculado pelo navegador: sha384-XNV7...QPL3          │
│                                                              │
│  Resultado:                                                  │
│  • Navegador BLOQUEIA o script                               │
│  • Recurso é marcado como "blocked" no DevTools              │
│  • Erro no console: "Failed to find a valid digest..."       │
│  • Código malicioso NÃO é executado                          │
│                                                              │
│  Propriedade dos algoritmos de hash:                        │
│  • Um único espaço adicionado → hash completamente diferente  │
│  • Qualquer modificação, por menor que seja → detectada      │
└──────────────────────────────────────────────────────────────┘
```

---

### 3.2 Componente 2: CSS como Vetor de Intel (Vazamento de Informações)

#### 3.2.1 Requisitos

| ID       | Requisito                                                                    | Prioridade |
|----------|-----------------------------------------------------------------------------|------------|
| CSS-01   | Não usar nomes de classes semânticos em áreas administrativas/sensíveis     | Alta       |
| CSS-02   | Minificar CSS de áreas restritas                                            | Média      |
| CSS-03   | Servir CSS de áreas administrativas de forma dinâmica (não como arquivo estático) | Média  |
| CSS-04   | Não expor nomes de arquivos CSS por perfil de usuário (viewer.css, admin.css) | Média   |
| CSS-05   | Não revelar papéis/roles through nomes de classes (admin-only, root-only)     | Alta       |

#### 3.2.2 Problema: CSS como Fonte de Intel para o Agressor

O CSS não permite invasão direta, mas é amplamente usado na **fase de reconhecimento (Intel)** para mapear:

| Informação Vazada           | Exemplo de Classe CSS                          |
|-----------------------------|------------------------------------------------|
| Perfis/roles de usuário     | `.role-root`, `.super-admin`, `.admin-only`    |
| Funcionalidades admin      | `.admin-panel`, `.system-settings`, `.wipe-db` |
| Ambientes (dev/staging/prod)| `.env-dev`, `.env-staging`, `.env-production`  |
| Rotas sensíveis            | `.payment-gateway-bypass`, `.debug-toolbar`    |
| Controles regionais        | `.gdpr-controls`, `.ccpa-controls`            |
| Funcionalidades específicas| `.user-impersonation`, `.issue-refund`        |

**Ataque típico:**

```
1. Agressor carrega viewer.css → identifica o padrão
2. Testa admin.css, root.css → descobre perfis existentes
3. Mapeia classes → descobre funcionalidades e rotas
4. Testa acesso a staging/dev → encontra bypass de pagamento
5. Usa informações para direcionar ataques mais precisos
```

#### 3.2.3 Estratégias de Defesa

| Estratégia                                    | Descrição                                                            |
|-----------------------------------------------|----------------------------------------------------------------------|
| **Nomes não semânticos**                     | Usar frameworks CSS (Tailwind, Bootstrap) com classes genéricas       |
| **CSS dinâmico**                              | Servir CSS de áreas admin via rota autenticada, não como arquivo público |
| **Minificação**                               | Minificar CSS para dificultar leitura humana                          |
| **Público vs. restrito**                      | CSS público pode ser semântico; CSS admin deve ser ofuscado          |
| **Nomes de arquivo genéricos**                | Evitar `admin.css`, `moderator.css`; usar hash ou nomes neutros       |

**Exemplo de CSS dinâmico (server-side):**

```python
# PHP/Python/Node — servir CSS autenticado
@app.route("/admin/styles")
@login_required
def admin_styles():
    if current_user.role != "admin":
        abort(403)
    css_content = load_css_for_role("admin")
    return Response(css_content, mimetype="text/css")
```

---

### 3.3 Componente 3: Clickjacking

#### 3.3.1 Requisitos

| ID       | Requisito                                                                   | Prioridade |
|----------|----------------------------------------------------------------------------|------------|
| CJ-01    | Implementar `Content-Security-Policy: frame-ancestors` em todas as páginas  | Alta       |
| CJ-02    | Páginas sensíveis (transferência, senha, exclusão): `frame-ancestors 'none'` | Alta     |
| CJ-03    | Aplicar modelo de lista branca (default `none`, exceções específicas)        | Alta       |
| CJ-04    | Widgets para parceiros: `frame-ancestors` com lista específica de domínios | Média      |

#### 3.3.2 Mecanismo do Ataque

```
┌──────────────────────────────────────────────────────────────────────┐
│                    ANATOMIA DO ATAQUE CLICKJACKING                    │
│                                                                      │
│  Site do Hacker (hacker.com):                                        │
│  ┌──────────────────────────────────────────────┐                    │
│  │  <h1>Prove que você é humano!</h1>            │                    │
│  │  <input name="verify" placeholder="Nome...">  │                    │
│  │  <button style="pointer-events: none;         │                    │
│  │    position: absolute; top: 110px;            │                    │
│  │    left: 200px; z-index: 2;">                 │                    │
│  │    (botão invisível para o mouse)              │                    │
│  │  </button>                                    │                    │
│  │                                               │                    │
│  │  <iframe src="banco.com/transfer"             │                    │
│  │    style="position: absolute;                  │                    │
│  │    opacity: 0; width: 100%; height: 200px;">   │                    │
│  │  </iframe>                                    │                    │
│  └──────────────────────────────────────────────┘                    │
│                                                                      │
│  O que acontece:                                                      │
│  1. Usuário digita nome no campo visível                              │
│  2. Usuário clica no botão visível                                   │
│  3. `pointer-events: none` faz o clique passar para o iframe         │
│  4. O clique atinge o botão "Transferir" dentro do iframe            │
│  5. Usuário realizou transferência sem perceber                      │
│                                                                      │
│  Variantes avançadas:                                                 │
│  • Jogos interativos que guiam cliques para áreas específicas        │
│  • Múltiplos passos (trocar senha, confirmar, etc.)                  │
│  • Prova social: fazer usuários curtirem conteúdos                   │
└──────────────────────────────────────────────────────────────────────┘
```

#### 3.3.3 Defesa: Content Security Policy — frame-ancestors

**Implementação:**

```php
// PHP
header("Content-Security-Policy: frame-ancestors 'none'");

// Python (Flask)
@app.after_request
def set_csp(response):
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    return response

// Node.js (Express)
app.use((req, res, next) => {
    res.setHeader("Content-Security-Policy", "frame-ancestors 'none'");
    next();
});
```

**Valores de `frame-ancestors`:**

| Valor                          | Comportamento                                                | Uso                         |
|--------------------------------|--------------------------------------------------------------|-----------------------------|
| `'none'`                       | Página NÃO pode ser incluída em iframe de nenhum domínio    | Bancos, fintechs, governo    |
| `'self'`                       | Permite iframe apenas do mesmo domínio                     | Apps com iframe interno      |
| `https://parceiro.com`         | Permite iframe apenas de domínio específico                | Widgets para parceiros       |
| `'self' https://parceiro.com`  | Combinação de self + domínios específicos                   | Apps com iframe + parceiros  |

**Estratégia recomendada — Lista branca (default deny):**

```
┌──────────────────────────────────────────────────────────────┐
│              ESTRATÉGIA DE FRAME-ANCESTORS                   │
│                                                              │
│  Abordagem 1: Blacklist (menos segura)                       │
│  • frame-ancestors 'self' para tudo                         │
│  • frame-ancestors 'none' apenas nas páginas sensíveis      │
│                                                              │
│  Abordagem 2: Whitelist (MAIS SEGURA — RECOMENDADA)          │
│  • frame-ancestors 'none' para tudo                          │
│  • frame-ancestors 'self' ou domínios específicos           │
│    apenas onde iframe é estritamente necessário              │
│                                                              │
│  Casos de uso por valor:                                     │
│  • Bancos, fintechs, governo → sempre 'none'                 │
│  • Apps com iframe interno → 'self'                          │
│  • Widgets para parceiros → lista de domínios específicos   │
│  • Páginas de mudança de senha/transferência → sempre 'none'│
└──────────────────────────────────────────────────────────────┘
```

> **Nota:** O header legado `X-Frame-Options` foi substituído por CSP `frame-ancestors`. Use `frame-ancestors` como abordagem moderna.

---

### 3.4 Componente 4: Gestão de Tag Managers

#### 3.4.1 Requisitos

| ID       | Requisito                                                                   | Prioridade |
|----------|----------------------------------------------------------------------------|------------|
| TM-01    | Controle de acesso rigoroso ao Tag Manager                                 | Alta       |
| TM-02    | Cada usuário deve ter conta individual (contas compartilhidas são proibidas) | Alta     |
| TM-03    | MFA obrigatório para todos os usuários do Tag Manager                        | Alta       |
| TM-04    | Processo de offboarding: desativar acesso ao TM quando funcionário sai      | Alta       |
| TM-05    | Auditoria de scripts inseridos (rastreabilidade de quem inseriu o quê)       | Alta       |
| TM-06    | Não usar Tag Manager em páginas sensíveis (reset de senha, login, admin)     | Alta       |

#### 3.4.2 Risco: Tag Manager como Root Access ao Frontend

```
┌──────────────────────────────────────────────────────────────────┐
│            RISCO DO TAG MANAGER                                  │
│                                                                  │
│  Quem tem acesso ao Tag Manager pode:                            │
│  ├── Inserir JavaScript arbitrário no site                       │
│  ├── Roubar dados de formulários (senhas, cartões)               │
│  ├── Fazer defacement (alterar aparência do site)               │
│  ├── Redirecionar usuários para sites maliciosos                │
│  ├── Injetar keyloggers                                          │
│  ├── Criar script injection em qualquer página                    │
│  └── Acessar cookies (se não forem HttpOnly)                     │
│                                                                  │
│  Comparação:                                                     │
│                                                                  │
│  Processo de deploy de código (SEGURO):                          │
│  Clone → Branch → Commit → Push → CI/CD → Pull Request →         │
│  Code Review → Aprovação → Deploy                                │
│                                                                  │
│  Acesso ao Tag Manager (INSEGURO sem gestão):                    │
│  E-mail compartilhido → Senha em planilha → Login →               │
│  Inserir script → Imediato em produção                           │
│                                                                  │
│  Problemas comuns:                                                │
│  • Conta compartilhida (marketing@empresa.com)                    │
│  • Senha em planilha compartilhada                                │
│  • Funcionário desligado sem revogar acesso                       │
│  • Sem MFA                                                       │
│  • Scripts copiados de blogs sem auditoria                       │
└──────────────────────────────────────────────────────────────────┘
```

#### 3.4.3 Mecanismo dos Tag Managers

Os Tag Managers funcionam injetando JavaScript dinamicamente:

```javascript
// Mecanismo simplificado de um Tag Manager
const script = document.createElement("script");
script.src = "https://tagmanager.example.com/container.js";
document.body.appendChild(script);

// O container.js pode criar novos scripts dinamicamente:
const thirdParty = document.createElement("script");
thirdParty.src = "https://analytics.example.com/tracker.js";
document.body.appendChild(thirdParty);
```

> **Consequência:** Qualquer pessoa com acesso ao Tag Manager tem controle total sobre o frontend da aplicação.

---

## 4. Checklist de Segurança Frontend

### 4.1 JavaScript de Terceiros

- [ ] Scripts de CDN possuem atributo `integrity` (SRI)
- [ ] `crossorigin="anonymous"` presente em todos os recursos com SRI
- [ ] Versões específicas (não `latest`) de bibliotecas
- [ ] Recursos externos carregados apenas via HTTPS
- [ ] Auditoria realizada em código de terceiros antes da inclusão
- [ ] Script copiado localmente quando segurança é prioridade

### 4.2 CSS

- [ ] Áreas administrativas: nomes de classes não semânticos
- [ ] Áreas administrativas: CSS minificado
- [ ] Áreas administrativas: CSS servido dinamicamente (com autenticação)
- [ ] Nomes de arquivos CSS não revelam perfis de usuário
- [ ] Classes CSS não revelam funcionalidades sensíveis

### 4.3 Clickjacking

- [ ] `frame-ancestors 'none'` como padrão global
- [ ] Páginas sensíveis (senha, transferência, exclusão): `frame-ancestors 'none'`
- [ ] Páginas que precisam de iframe: `frame-ancestors` com whitelist específica
- [ ] Widgets para parceiros: lista de domínios específicos

### 4.4 Tag Manager

- [ ] Acesso restrito (cada usuário com conta própria)
- [ ] MFA obrigatório
- [ ] Processo de offboarding documentado e automatizado
- [ ] Auditoria de scripts inseridos
- [ ] Tag Manager NÃO carregado em páginas sensíveis (login, reset, admin)
- [ ] Equipe de marketing ciente dos riscos de segurança

---

## 5. Considerações de Segurança

### 5.1 Ameaças e Mitigações

| Ameaça                                      | Mitigação                                        | Ref.        |
|---------------------------------------------|--------------------------------------------------|-------------|
| Script de CDN modificado                    | Sub-Resource Integrity (SRI)                     | SRI-01      |
| CDN sem CORS                                | `crossorigin="anonymous"`                       | SRI-05      |
| Biblioteca sem versão altera sem aviso       | Usar versões específicas                         | SRI-03      |
| Reconnhecimento via CSS (Intel)             | Nomes não semânticos + CSS dinâmico             | CSS-01/03   |
| Vazamento de roles via classes CSS          | Ofuscar nomes de classes em áreas admin         | CSS-05      |
| Clickjacking via iframe                     | `frame-ancestors 'none'`                        | CJ-01       |
| Clickjacking em página interna              | `frame-ancestors 'self'`                        | CJ-02       |
| Acesso não autorizado ao Tag Manager        | Controle de acesso + MFA + contas individuais    | TM-01/02/03|
| Script malicioso via Tag Manager            | Offboarding + auditoria + restrição de páginas   | TM-04/06   |
| Funcionário desligado com acesso ao TM      | Processo de offboarding automatizado            | TM-04       |

### 5.2 Comparação: Deploy de Código vs. Tag Manager

| Critério                  | Deploy de Código (via Git)           | Tag Manager                   |
|---------------------------|--------------------------------------|-------------------------------|
| Acesso                   | Repo Git com SSH key                 | E-mail + senha                |
| Autenticação             | Chave SSH (2048+ bits)               | Geralmente apenas senha       |
| Revisão                  | Code Review por pares                 | Nenhuma                       |
| Testes automatizados     | CI/CD pipeline                        | Nenhum                        |
| Rastreabilidade          | Git history + commit author           | Geralmente nenhuma            |
| Offboarding              | Desativar acesso ao repo             | Manual (trocar senha?)       |
| MFA                      | Via provedor Git                      | Raramente                     |
| Tempo até produção       | Minutos a horas                      | Imediato                      |
| Risco                    | Baixo (processo robusto)             | Alto (acesso direto)          |

---

## 6. Referências

### 6.1 Especificações e Documentação

| Recurso                          | URL                                    |
|----------------------------------|----------------------------------------|
| Sub-Resource Integrity           | developer.mozilla.org/en-US/docs/Web/Security/SRI |
| Content Security Policy          | developer.mozilla.org/en-US/docs/Web/HTTP/CSP |
| CSP: frame-ancestors            | developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/frame-ancestors |
| SRI Hash Generator              | www.srihash.org/                       |
| CSP Evaluator                   | securityheaders.com/                    |

### 6.2 Diretivas CSP Relacionadas

| Diretiva         | Uso                                               |
|------------------|---------------------------------------------------|
| `frame-ancestors`| Controla quais domínios podem embeber a página   |
| `script-src`     | Controla quais scripts podem ser executados        |
| `style-src`      | Controla quais CSS podem ser aplicados             |
| `default-src`    | Fallback para todas as diretivas                    |
| `img-src`        | Controla quais imagens podem ser carregadas         |
| `connect-src`    | Controla quais URLs podem ser acessadas via fetch/XHR |

> **Nota:** Este documento aborda `frame-ancestors` em profundidade. As demais diretivas CSP serão detalhadas em documentos complementares.

---

## 7. Histórico de Revisões

| Versão | Data       | Descrição                                            |
|--------|------------|------------------------------------------------------|
| 1.0    | 2026-04-08 | Versão inicial — Baseado no curso "Segurança Para Devs" |
