# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança de Deploy, Gestão de Segredos e Logging de Segurança

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança de Deploy, Gestão de Segredos e Logging de Segurança |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para o processo de deploy de aplicações, gestão de segredos e logging voltado à segurança. Abrange configuração segura de CI/CD com GitHub Actions, segregação de privilégios, storage seguro de credenciais, e logging estruturado para detecção e investigação de incidentes.

### 1.2 Escopo

- Deploy: systemd, proxy reverso, segregação de usuário, permissões mínimas
- CI/CD: GitHub Actions, Deploy Keys, Secrets, pipeline automatizado
- Gestão de Segredos: config.json fora do versionamento, GitHub Secrets, Zero Trust
- Banco de Dados: permissões mínimas (READ-only quando possível), bind local
- Logging de Segurança: eventos a registrar, dados a incluir/excluir, monitoramento

### 1.3 Definições e Acrônimos

| Termo                    | Definição                                                        |
|--------------------------|------------------------------------------------------------------|
| **Systemd**               | Gerenciador de serviços e daemons do Linux                     |
| **Proxy Reverso**         | Servidor web que repassa requisições para aplicação backend   |
| **GitHub Actions**         | CI/CD integrado ao GitHub                               |
| **Deploy Key**            | Chave SSH de acesso somente leitura no repositório            |
| **GitHub Secrets**        | Segredos criptografados acessíveis apenas por Actions           |
| **Zero Trust**            | Nunca confie por padrão — acesso mínimo necessário          |

### 1.4 Princípio Fundamental

> **O segredo não pode estar no código.** Credenciais, chaves, senhas e tokens devem estar vinculados ao ambiente de execução (servidor, CI/CD), nunca no repositório. Vazamento de segredos é uma das vulnerabilidades mais comuns em produção.

---

## 2. Visão Geral de Arquitetura

### 2.1 Arquitetura de Deploy

```
┌──────────────────────────────────────────────────────────────────────┐
│              ARQUITETURA DE DEPLOY SEGURO                         │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  GITHUB                                                         │      │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐     │      │
│  │  │ Código    │  │ Deploy Key   │  │ GitHub Secrets   │     │      │
│  │  │ (.py,     │  │ (read-only)  │  │ (SSH Key)      │     │      │
│  │  │  .json,   │  └──────┬───────┘  └──────┬──────────┘     │      │
│  │  │  .git)    │         │               │         │             │      │
│  │  └─────┬────┘         │               │         │             │      │
│  │        │               │               │         │             │      │
│  │  ┌────▼───────────────▼───────▼──────────────▼─────────▼─────┐   │      │
│  │  │  GitHub Actions (.github/workflows/deploy.yaml)          │   │      │
│  │  │  1. Setup SSH Key                                  │   │      │
│  │  │  2. git pull                                         │   │      │
│  │  │  3. sudo /usr/local/bin/deploy_seguro.sh restart     │   │      │
│  └──┼──────────────────────────────────────────────────────────┼───┘      │
│     │                                                               │          │
│     ▼                                                               │          │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │  SERVIDOR (seguro.elcio.com.br)                              │          │
│  │                                                               │          │
│  │  ┌────────────┐  ┌──────────────┐  ┌───────────────────────┐│          │
│  │  │  Firewall   │  │  Apache      │  │  Systemd Service     ││          │
│  │  │  (UFW)     │  │  (Proxy     │  │  (seguro.service)   ││          │
│  │  │            │  │   Reverso)  │  │  Usuário: seguro    ││          │
│  │  │            │  │  :80/:443   │  │  Sem acesso root    ││          │
│  │  └────────────┘  └──────┬───────┘  └─────────┬──────────┘│          │
│  │                          │                     │          │          │
│  │                          ▼                     ▼          │          │
│  │  ┌──────────────────────────────────────────────────────┐  │          │
│  │  │  Aplicação Python (Gunicorn :8000)                       │  │          │
│  │  └────────────────────────┬─────────────────────────────┘  │          │
│  │                        │                                        │          │
│  │                        ▼                                        │          │
│  │  ┌──────────────────────────────────────────────────────┐  │          │
│  │  │  MariaDB (localhost:3306)                              │  │          │
│  │  │  Usuário: seguro | Permissão: SELECT ONLY           │  │          │
│  │  │  Bind: 127.0.0.1    | Não pode INSERT/UPDATE/DELETE    │  │          │
│  │  └──────────────────────────────────────────────────────┘  │          │
│  │                                                               │          │
│  │  ┌──────────────────────────────────────────────────────┐  │          │
│  │  │  Arquivos de Configuração                                │  │          │
│  │  │  • config.json (NÃO versionado)                       │  │          │
│  │  │  • config.sample.json (versionado, sem dados reais)   │  │          │
│  │  │  • /usr/local/bin/deploy_seguro.sh (sudoers only)     │  │          │
│  │  └──────────────────────────────────────────────────────┘  │          │
│  └──────────────────────────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Fluxo de Deploy Automatizado

```
┌─────────┐    ┌─────────────┐    ┌──────────────────┐    ┌───────────────┐
│  Push    │───→│ GitHub     │───→│ GitHub Actions    │───→│ SSH         │
│  main    │    │ Actions     │    │ (Ubuntu Latest) │    │ git pull    │
│         │    │ Trigger    │    │                  │    │             │
└─────────┘    └─────────────┘    │                  │    │             │
                                        │                  │    │ sudo        │
                                        ▼                  │    │ deploy_     │
                               ┌────────────────┐    │    │ seguro.sh   │
                               │ Setup SSH Key    │    │    │ restart    │
                               └────────┬───────┘    └────────┬────────┘
                                        │                   │          │
                                        ▼                   ▼          ▼
                               ┌──────────────────────────────────────┐
                               │ sudo systemctl restart seguro.service       │
                               └──────────────────────────────────────┘
                                        │
                                        ▼
                               Aplicação atualizada em produção
```

---

## 3. Componentes de Design

### 3.1 Componente: Configuração Segura de Aplicação

#### 3.1.1 Descrição

Credenciais de banco de dados, chaves API e outros segredos nunca devem ser versionados no repositório. Usa-se um arquivo de configuração (config.json, .env, config.py) que é adicionado ao .gitignore, com um arquivo de exemplo (config.sample.json) versionado sem dados reais.

#### 3.1.2 Código Vulnerável vs. Seguro

```json
// ❌ VULNERÁVEL — Credenciais hardcoded no código
app.py:
  conn = mysql.connect(
    host="localhost",
    user="test",
    password="test",
    database="task"
  )
```

```python
# ✅ SEGURO — Credenciais em arquivo externo (config.json)
# config.json (NÃO versionado — está no .gitignore)
{
    "db": {
        "host": "127.0.0.1",
        "user": "seguro",
        "password": "[SENHA_CSPRNG_32_CHARS]",
        "database": "seguro"
    }
}

# config.sample.json (versionado — sem dados reais)
{
    "db": {
        "host": "localhost",
        "user": "exemplo",
        "password": "sua_senha_aqui",
        "database": "seu_banco"
    }
}

# app.py — Lê configuração do arquivo externo
import json
with open('config.json') as f:
    config = json.load(f)
conn = mysql.connect(**config['db'])
```

```
.gitignore:
config.json
senha.db
*.pem
*.key
.env
```

#### 3.1.3 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| CF-1 | Nunca versione credenciais no repositório                           | Crítica    |
| CF-2 | Use arquivo de configuração externo (config.json, .env)               | Crítica    |
| CF-3 | Adicione arquivo de exemplo ao repositório (config.sample.json)          | Alta       |
| CF-4 | Adicione arquivo de configuração ao .gitignore                           | Crítica    |
| CF-5 | O usuário da aplicação NÃO deve ter acesso root                            | Alta       |

---

### 3.2 Componente: Deploy com Segregação de Privilégios

#### 3.2.1 Descrição

A aplicação roda como usuário não-privilegiado (`seguro`), sem acesso root. O deploy automatizado usa sudo para executar apenas o script de restart. O banco de dados aceita apenas SELECT. Cada componente tem a permissão mínima necessária.

#### 3.2.2 Configuração Systemd

```ini
# /etc/systemd/system/seguro.service
[Unit]
Description=app seguro

[Service]
User=seguro
WorkingDirectory=/home/seguro/seguro
ExecStart=/home/seguro/seguro/run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 3.2.3 Permissões do Script de Deploy

```bash
# /usr/local/bin/deploy_seguro.sh (proprietade: root, executável por todos)
#!/bin/bash
systemctl restart seguro.service

# /etc/sudoers.d/deploy_seguro (permissão sudo mínima)
seguro ALL=(ALL) NOPASSWD: /usr/local/bin/deploy_seguro.sh
```

```
Permissões:
  deploy_seguro.sh → -rwxr-xr-x (todos leem/executam, só root escreve)
  sudoers.d/deploy_seguro → -r--r----- (só root lê, sem grupo/outros)
```

#### 3.2.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| DP-1 | Rode a aplicação como usuário não-privilegiado                      | Crítica    |
| DP-2 | Use Systemd para gerenciar o serviço (não screen/tmux)               | Alta       |
| DP-3 | Script de deploy deve ser propriedade de root                          | Alta       |
| DP-4 | Permita sudo APENAS para o comando de deploy específico               | Alta       |
| DP-5 | Nunca use ALL=(ALL) NOPASSWD para o usuário de aplicação           | Crítica    |
| DP-6 | Banco de dados com permissão READ-ONLY quando possível               | Alta       |
| DP-7 | Banco de dados com bind restrito (127.0.0.1)                         | Alta       |
| DP-8 | Servidor web (Apache) como proxy reverso para a aplicação             | Média      |

---

### 3.3 Componente: CI/CD com GitHub Actions

#### 3.3.1 Descrição

Pipeline automatizado de deploy usando GitHub Actions. Deploy Key de acesso somente leitura para git pull. GitHub Secrets para armazenar a chave SSH privada de forma criptografada.

#### 3.3.2 Configuração GitHub

```
.github/workflows/deploy.yaml:

name: deploy-prod
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      SSH_KEY: ${{ secrets.SSH_KEY }}
    steps:
      - name: Setup SSH Key
        run: |
          mkdir -p ~/.ssh
          echo "${{ env.SSH_KEY }}" > ~/.ssh/id_rsa
          chmod 600 ~/.ssh/id_rsa

      - name: Deploy
        run: ssh -o StrictHostKeyChecking=no \
            deploy@seguro.exemplo.com.br /home/deploy/seguro.sh

      - name: Restart Service
        run: ssh -o StrictHostKeyChecking=no \
            deploy@seguro.exemplo.com.br \
            sudo /usr/local/bin/deploy_seguro.sh
```

```
GitHub Settings → Secrets and Variables → Actions:
  SSH_KEY = (chave privada criptografada — irreversível após salvar)
```

#### 3.3.3 Fluxo de Acesso

```
┌─────────────────────────────────────────────────────────────────┐
│  ACESSO AO CÓDIGO                                                  │
│                                                                    │
│  Deploy Key (read-only)  →  git pull                                   │
│  GitHub Actions (secrets) →  chave SSH para SSH                  │
│  Servidor (sudoers)      →  restart do serviço                   │
│  Usuário seguro           →  rodar aplicação + git pull                │
│  Banco de dados            →  SELECT ONLY                                │
│  Chave SSH privada       →  GitHub Secrets (criptografada)        │
│  Configuração (DB pass)  →  config.json (servidor, não versionado)    │
│                                                                    │
│  Ninguém tem acesso completo a tudo — mínimo privilégio necessário    │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.3.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| CD-1 | Use GitHub Secrets (não variáveis de ambiente) para chaves SSH    | Crítica    |
| CD-2 | Deploy Key com acesso somente leitura ao repositório               | Alta       |
| CD-3 | Chave SSH privada NUNCA no código, apenas em Secrets               | Crítica    |
| CD-4 | StrictHostKeyChecking=no apenas em CI automatizado                  | Média      |
| CD-5 | Pipeline em modo detection-only durante estágio inicial               | Média      |
| CD-6 | Valide em qual branch o deploy pode ocorrer (main, staging)         | Média      |

---

### 3.4 Componente: Banco de Dados com Permissões Mínimas

#### 3.4.1 Descrição

O banco de dados é acessível apenas localmente (bind-address: 127.0.0.1). A aplicação recebe permissão SELECT ONLY — não pode INSERT, UPDATE, DELETE ou DROP. Essa granularidade limita o impacto em caso de comprometimento.

#### 3.4.2 Configuração

```sql
-- Criar usuário com permissão mínima
CREATE USER 'seguro'@'localhost' IDENTIFIED BY '[SENHA_FORTE]';

-- GRANT SELECT ONLY na tabela específica
GRANT SELECT ON seguro.pessoa TO 'seguro'@'localhost';

-- Sem permissões para outras operações
-- INSERT, UPDATE, DELETE, CREATE, DROP → Permission denied

FLUSH PRIVILEGES;
```

```ini
# /etc/mysql/mariadb.conf.d/50-server.cnf
bind-address = 127.0.0.1
# → Banco de dados inacessível pela internet (mesmo que o firewall bloqueie)
```

#### 3.4.3 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| DB-1 | Bind do banco em 127.0.0.1 (não expor para a rede)         | Crítica    |
| DB-2 | Conexão do banco usa usuário dedicado (não root)                   | Alta       |
| DB-3 | Permissão SELECT ONLY quando a aplicação é só leitura              | Alta       |
| DB-4 | Crie usuário/seleção de banco separados por aplicação              | Alta       |

---

### 3.5 Componente: Logging de Segurança

#### 3.5.1 Descrição

Logs são essenciais para detecção, investigação e resposta a incidentes de segurança. O log deve capturar eventos suspeitos, ações de alto risco e informações de auditoria, sem expor dados sensíveis. Logs nunca devem ser acessíveis via web e o usuário da aplicação não deve ter acesso aos logs do sistema.

#### 3.5.2 O Que Logar

**Eventos de segurança (flag security=true):**

| Categoria                      | Exemplos                                                        |
|--------------------------------|------------------------------------------------------------------|
| Falhas de validação de entrada | Valor inválido em query string, número fora do intervalo, JSON malformado |
| Validação contra lista discreta   | País diferente dos 8 permitidos no select                     |
| Falhas de validação de saída     | JSON de resposta inválido                                    |
| Autenticação                    | Login com sucesso/falha, troca de senha, logout                |
| Autorização                     | Acesso a recurso não pertencente (IDOR), função não autorizada |
| Sessão                         | Cookie inválido, JWT suspeito, sessão de outro usuário          |
| Erros de aplicação             | Erro de sintaxe, timeout, falha de TLS, erro de third-party       |
| Ações administrativas          | Criar/excluir usuário, alterar privilégios, criar token            |
| Uso de conta compartilhada      | Login como "root", "admin"                                   |
| Acesso a dados sensíveis         | Leitura de dados de pagamento, cartão de crédito                  |
| Uso de privilégios do sistema     | Acesso root, modificações em arquivos do sistema              |
| Upload de arquivos              | Arquivo enviado (nome, tipo, tamanho)                         |
| Exportação de dados             | Dados exportados, relatórios gerados                             |
| Atividades suspeitas de negócio   | Ação fora de ordem, cancelamento pós-aprovação               |
| Violação de limites            | Requisição acima do limite (10/dia), 50k acima do teto       |
| Falhas de TLS                 | Falha de validação de certificado no backend                  |
| Opt-ins legais                  | Aceite termos, consentimento de dados, notificações              |
| Detecção de vírus              | Antivírus identificou arquivo suspeito no upload               |

#### 3.5.3 Onde Logar (metadados obrigatórios)

| Dado                            | Razão                                                        |
|---------------------------------|----------------------------------------------------------------|
| Timestamp (evento)              | Saber quando o evento ocorreu                                 |
| Timestamp (log)                 | Saber quando foi processado (útil em filas/eventos)       |
| ID da interação                  | Rastrear toda a interação do início ao fim                   |
| Nome e versão da aplicação      | Saber qual código estava rodando no momento do incidente       |
| Hostname / IP da aplicação      | Identificar qual servidor processou (múltiplos servidores)  |
| URL da requisição               | Saber qual rota/recurso foi acessado                          |
| Local no código (módulo/arquivo) | Saber onde o log foi gerado (evitar grep em 38 arquivos) |
| IP de origem (Request IP)       | Identificar a origem da requisição                             |
| User-Agent                      | Identificar navegador/dispositivo                                |
| ID do usuário                  | Identificar qual usuário realizou a ação                          |
| Tipo e severidade do evento      | Classificar a gravidade (log levels: ERROR, WARN, INFO)        |
| Flag de relevância de segurança   | true para logs de segurança, false para logs de negócio          |
| Descrição                       | O que de fato aconteceu                                      |

#### 3.5.4 O Que NUNCA Logar

| Dado                            | Risco se Vazado                                               |
|---------------------------------|----------------------------------------------------------------|
| Código-fonte da aplicação         | Expõe lógica de negócio                                       |
| Stack traces completos            | Expõe estrutura interna                                     |
| Identificador de sessão (session ID)  | Permite sequesto de conta (criar cookie e assumir identidade)|
| Tokens de acesso (JWT, OAuth)     | Permite acesso autenticado sem senha                       |
| Dados pessoais sensíveis (CPF, RG) | Violação de LGPD e leis de privacidade                  |
| Dados de saúde                  | Violação de LGPD e leis de privacidade                  |
| Senhas (hash ou plaintext)        | Acesso direto a contas                                      |
| Strings de conexão com senha     | Acesso ao banco de dados                                    |
| Chaves criptográficas            | Descriptografia de dados em repouso                           |
| Dados de cartão/pagamento       | Violação PCI DSS                                        |
| Segredos (API keys, tokens)     | Acesso a serviços de terceiros                               |
| Código-fonte (tracebacks)         | Expõe estrutura interna                                     |
| Conteúdo comercial sensível      | Informação proprietária da empresa                            |
| Dados cuja coleta é ilegal     | Risco jurídico                                              |

#### 3.5.5 Onde Armazenar Logs

```
Requisitos de armazenamento:
  ✅ Permissões restritas (dono + grupo admin)
  ✅ Usuário da aplicação NÃO é dono dos logs
  ✅ NUNCA acessível via web
  ✅ Partição separada (se possível)
  ✅ Banco de dados separado do banco da aplicação
  ✅ Conta separada no serviço de log (CloudWatch, etc.)
  ✅ Usuário de log NÃO tem acesso ao banco da aplicação
  ✅ Usuário da aplicação NÃO tem acesso ao banco de log
```

#### 3.5.6 Monitoramento de Logs (Alertas)

| Métrica                                    | Alerta Quando                             |
|-------------------------------------------|-------------------------------------------|
| Logins por IP por dia                  | IP único com volume anormal (> 10x média)    |
| Logins fora do horário comercial       | Host com logins entre 00h-06h (>50x média)  |
| Falhas de autenticação por usuário      | Usuário com >10 logins falhos em 1 dia          |
| Bytes transferidos por IP de destino   | IP consumindo volume anormal de dados            |
| Região geográfica dos dados           | Spike de dados para regiões incomuns               |
| Linhas de log por dia                | Volume total de logs anormal (>2x média)        |
| Mensagens de erro por dia              | Volume de erros anormal (>5x média)              |
| Reinícios de serviço por dia           | Aplicação reiniciou inesperadamente               |

#### 3.5.7 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| LG-1 | Logue TODOS os eventos de segurança listados acima                  | Alta       |
| LG-2 | Inclua flag de relevância de segurança no log                    | Alta       |
| LG-3 | NUNCA logue dados sensíveis (session ID, tokens, senhas, CPF)   | Crítica    |
| LG-4 | NUNCA logue stack traces completos — use pasta separada     | Alta       |
| LG-5 | Logs nunca acessíveis via web                                     | Crítica    |
| LG-6 | Usuário da aplicação sem acesso aos logs                         | Alta       |
| LG-7 | Banco de dados de logs separado do banco da aplicação            | Alta       |
| LG-8 | Configure monitoramento automático para as métricas de alerta       | Alta       |

---

## 4. Matriz de Ameaças e Mitigações

| # | Ameaça                              | Vetor                         | Impacto                           | Mitigação                                      | Ref. |
|---|-------------------------------------|-------------------------------|-----------------------------------|------------------------------------------------|------|
| 1 | Credenciais no repositório            | config.json no commit       | Acesso ao banco de dados        | config.json no .gitignore + config.sample  | 3.1  |
| 2 | Chave SSH privada exposta           | Enviada por e-mail, chat    | Acesso ao servidor           | GitHub Secrets (criptografado, irreversível)     | 3.3  |
| 3 | GitHub Actions com variável        | Variável de ambiente       | Chave visível por funcionários | GitHub Secrets em vez de variáveis           | 3.3  |
| 4 | Usuário app com acesso root       | sudo ALL=(ALL)          | Takeover do servidor           | NOPASSWD para comando específico apenas        | 3.2  |
| 5 | App com INSERT/DELETE no DB       | GRANT ALL               | Exclusão de dados            | GRANT SELECT ONLY                              | 3.4  |
| 6 | Banco acessível pela internet      | bind-address = 0.0.0.0     | Acesso ao banco de dados        | bind-address = 127.0.0.1 + firewall            | 3.4  |
| 7 | Session ID nos logs                  | Log sem hash do ID       | Sequesto de conta            | Hash do session ID no log                     | 3.5  |
| 8 | Token JWT nos logs                  | Log sem hash            | Acesso autenticado sem senha | Hash do token no log                            | 3.5  |
| 9 | Logs acessíveis via web             | Log em /var/www/         | Vazamento completo            | Log em partição separada + sem acesso web       | 3.5  |

---

## 5. Checklists de Verificação

### 5.1 Checklist — Configuração de Segredos

- [ ] Nenhuma credencial está hardcoded no código-fonte
- [ ] Arquivo de configuração (config.json / .env) está no .gitignore
- [ ] Arquivo de exemplo (config.sample.json) está versionado sem dados reais
- [ ] Senhas geradas com CSPRNG (openssl rand -hex 32)
- [ ] Chaves SSH protegidas com senha ou disco criptografado
- [ ] Chave SSH privada NUNCA compartilhada (nem com colegas)
- [ ] Segredos armazenados como GitHub Secrets (não como variáveis)
- [ ] Registros DNS apontam para IP correto (IPv4 e IPv6)

### 5.2 Checklist — Deploy

- [ ] Aplicação roda como usuário não-privilegiado (sem root)
- [ ] Usuário não está no grupo sudo (ou sudoers restrito a 1 comando)
- [ ] Serviço gerenciado pelo Systemd (não screen/tmux)
- [ ] Script de deploy é propriedade de root, executável por todos
- [ ] Banco de dados com bind local (127.0.0.1) e permissão SELECT ONLY
- [ ] Servidor web (Apache/Nginx) como proxy reverso para a aplicação
- [ ] Deploy automatizado via CI/CD (GitHub Actions, GitLab CI, etc.)
- [ ] Deploy Key com acesso somente leitura ao repositório
- [ ] Deploy Key removido quando não mais necessário

### 5.3 Checklist — Logging

- [ ] Logs capturam eventos de segurança com flag security=true
- [ ] Timestamp do evento e do log estão incluídos
- [ ] ID da interação (request ID) está presente
- [ | Versão da aplicação (commit ID) está presente
- [ ] Hostname/IP do servidor e URL da requisição estão presentes
- [ ] IP de origem e User-Agent estão presentes
- [ ] ID do usuário está presente (não CPF, não dados sensíveis)
- [ ] Logs NUNCA são acessíveis via web
- [ ] Usuário da aplicação NÃO tem acesso aos logs do sistema
- [ ] Banco de dados de logs é separado do banco da aplicação
- [ ] Monitoramento automático configurado para métricas de segurança

---

## 6. Tabela Comparativa — Onde Armazenar Segredos

| Localização        | Criptografado em Repouso? | Acessível por | Risco se Vazado      |
|--------------------|---------------------------|-------------|------------------------|
| Código-fonte        | ❌ Não                    | Time todo mundo | **Crítico**           |
| Variável de ambiente | ❌ Não                    | Time + Funcionários | **Crítico**           |
| GitHub Secrets     | ✅ Sim (irreversível)       | Actions apenas | **Baixo**              |
| Arquivo no servidor | ✅ Sim (disco cript.)     | Time SRE + Admin | **Baixo**              |
| Servidor separado   | ✅ Sim (disco cript.)     | Admin dedicado    | **Baixo**              |

---

## 7. Referências

| Recurso                      | URL/Descrição                                             |
|------------------------------|-----------------------------------------------------------|
| OWASP — Secrets Management     | https://owasp.org/www-community/Secrets_Management_Cheat_Sheet.html |
| OWASP — Logging Cheat Sheet   | https://owasp.org/www-community/Logging_Cheat_Sheet.html |
| GitHub Actions Docs             | https://docs.github.com/en/actions                              |
| GitHub Secrets Docs             | https://docs.github.com/en/actions/security-guides/encrypted-secrets |
| Systemd Service Files        | https://www.freedesktop.org/wiki/Software/systemd/Systemd        |
| OWASP — Session Management    | https://owasp.org/www-community/Session_Management_Cheat_Sheet.html |
