# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança CI/CD — Análise Estática (SAST), Gestão de Dependências e Modelagem de Ameaças

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança CI/CD: SAST, Gestão de Dependências (SCA) e Modelagem de Ameaças |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para o processo de Integração Contínua (CI/CD), abordando análise estática de código (SAST), gestão de vulnerabilidades em dependências (SCA) e modelagem de ameaças como práticas contínuas da equipe.

### 1.2 Escopo

- SAST (Static Application Security Testing): análise automatizada de código-fonte para detecção de vulnerabilidades
- SCA (Software Composition Analysis): monitoramento de vulnerabilidades em dependências de terceiros
- Modelagem de ameaças: metodologia STRIDE para identificar e mitigar ameaças proativamente
- OWASP Cornucopia: jogo de cartas para exercitar pensamento criativo em segurança
- Dependency-Track: plataforma centralizada para gestão de SBOM (Software Bill of Materials)
- Integração com CI/CD: hooks de git, pipelines, alertas automatizados

### 1.3 Definições e Acrônimos

| Termo                    | Definição                                                        |
|--------------------------|------------------------------------------------------------------|
| **SAST**                 | Static Application Security Testing — análise estática de código-fonte |
| **SCA**                  | Software Composition Analysis — análise de vulnerabilidades em dependências |
| **SBOM**                 | Software Bill of Materials — lista padronizada de dependências  |
| **STRIDE**               | Spoofing, Tampering, Repudiation, Information Disclosure, DoS, EoP |
| **OWASP Cornucopia**     | Jogo de cartas da OWASP para modelagem de ameaças em equipe     |
| **PURL**                 | Package URL — padrão universal para identificar pacotes         |
| **CPE**                  | Common Platform Enumeration — padrão do NIST para identificar componentes |
| **NVD**                  | National Vulnerability Database — banco de dados do NIST         |
| **CVE**                  | Common Vulnerabilities and Exposures — identificador de vulnerabilidade |

### 1.4 Princípio Fundamental

> **Segurança é um processo contínuo, não um checklist.** Vulnerabilidades novas são descobertas diariamente. Um sistema seguro hoje pode estar vulnerável amanhã. Ferramentas automatizadas (SAST, SCA) fornecem camadas adicionais de proteção, mas não substituem o pensamento criativo humano — modelagem de ameaças deve ser praticada regularmente pela equipe.

---

## 2. Visão Geral de Arquitetura

### 2.1 Camadas de Automação de Segurança

```
┌──────────────────────────────────────────────────────────────────────┐
│           CAMADAS DE AUTOMAÇÃO DE SEGURANÇA                        │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 1 — SAST (Análise Estática de Código)              │      │
│  │  • Específico da linguagem: Bandit (Python), Brakeman (Ruby)│      │
│  │  • Genérico: SonarQube, Semgrep, CodeQL                    │      │
│  │  • Roda no: Hook de Git, Pipeline de CI, Máquina local     │      │
│  │  • Detecta: SQL Injection, MD5, código inseguro            │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 2 — SCA (Gestão de Dependências)                   │      │
│  │  • Específico da linguagem: pip-audit (Python), npm audit  │      │
│  │  • Genérico: Dependency-Track, Snyk, Renovate              │      │
│  │  • Formato: SBOM (CycloneDX, SPDX)                         │      │
│  │  • Detecta: Dependências com CVEs conhecidos               │      │
│  │  • Alerta: E-mail, notificação, quando nova CVE é publicada│      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 3 — Modelagem de Ameaças (Humana)                  │      │
│  │  • Diagramas: ThreatDragon, Microsoft Threat Modeling Tool │      │
│  │  • Jogo: OWASP Cornucopia                                 │      │
│  │  • Frequência: A cada 3 meses ou quando arquitetura muda  │      │
│  │  • Output: Lista de ameaças com severidade e mitigação     │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ⚠️  Nenhuma camada substitui as outras — todas são complementares  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Fluxo de Gestão de Dependências

```
┌──────────────────────────────────────────────────────────────────────┐
│              FLUXO DE GESTÃO DE DEPENDÊNCIAS                         │
│                                                                      │
│  Desenvolvedor               CI/CD                  Plataforma       │
│  ┌──────────┐         ┌──────────────┐         ┌──────────────┐     │
│  │ pip add  │─────→   │ pipdeptree   │─────→   │ Dependency-  │     │
│  │ pacote   │         │ cyclonedx    │         │ Track        │     │
│  └──────────┘         │ (SBOM JSON)  │         │              │     │
│                       └──────────────┘         │ • Upload BOM │     │
│                                                 │ • Análise    │     │
│                                                 │ • Alertas    │     │
│                                                 │ • NVD + OSV  │     │
│                                                 └──────┬───────┘     │
│                                                        │              │
│                                                        ▼              │
│                                                 ┌──────────────┐     │
│                                                 │ E-mail/Slack │     │
│                                                 │ Nova CVE     │     │
│                                                 │ encontrada!  │     │
│                                                 └──────────────┘     │
│                                                                      │
│  Fontes de vulnerabilidades:                                        │
│  • NVD (NIST) — mirroring local via API key                         │
│  • OSV (Google Open Source Vulnerabilities) — PyPI, NPM, etc.       │
│  • Analyzers internos: Trivy, Snoky, VulnDB                        │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.3 Fluxo de Modelagem de Ameaças com Cornucopia

```
┌──────────────────────────────────────────────────────────────────────┐
│              JOGO OWASP CORNUCOPIA                                   │
│                                                                      │
│  1. Reunir equipe (3-6 pessoas, 1 tarde)                            │
│  2. Embaralhar cartas (A♠ até K por categoria)                     │
│  3. Jogador inicial escolhe carta e a apresenta                    │
│  4. Jogador deve CONVENCER a equipe de que a ameaça se aplica      │
│  5. Se equipe concorda → cria tarefa no Jira + ameaça no diagrama   │
│  6. Próximo jogador tenta superar com carta maior da mesma categoria│
│  7. Pontuação: 1 ponto por carta jogada, +1 para a maior           │
│  8. Jokers (Coringas): podem ser usados em qualquer categoria       │
│                                                                      │
│  Categorias das cartas:                                             │
│  ♠ Validação de dados    ♥ Autenticação                             │
│  ♦ Gerenciamento de sessão  ♣ Controle de acesso                    │
│                                                                      │
│  Output:                                                             │
│  • Diagrama STRIDE preenchido com ameaças reais                     │
│  • Tarefas priorizadas por severidade                               │
│  • Equipe alinhada sobre riscos de segurança                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Componentes de Design

### 3.1 Componente: SAST — Análise Estática de Código

#### 3.1.1 Descrição

SAST analisa o código-fonte sem executá-lo para detectar padrões de código inseguro. Existem dois tipos de ferramenta: específicas da linguagem (mais precisas, rápidas) e genéricas (multi-linguagem, centralizadas). Ambas devem ser usadas em conjunto.

#### 3.1.2 Ferramenta Específica — Bandit (Python)

```bash
# Instalação e execução
pip install bandit
bandit -r src/ -f html -o report.html
```

```
Detectado no código de exemplo:

1. POSSIBLE SQL INJECTION
   Linha: query = f"SELECT * FROM users WHERE username='{username}'"
   Severidade: HIGH
   → Montagem de query por concatenação de strings

2. WEAK CRYPTOGRAPHIC ALGORITHM
   Linha: hashlib.md5(password.encode())
   Severidade: HIGH
   → Uso de MD5 para hashing de senha

3. REQUEST WITHOUT TIMEOUT
   Linha: requests.get(url + cep)
   Severidade: MEDIUM
   → Requisição HTTP sem timeout pode causar DoS

4. SYNCHRONOUS REQUEST IN ASYNC FUNCTION
   Linha: requests.get() dentro de async def
   Severidade: MEDIUM
   → Cliente síncrono em função assíncrona bloqueia event loop
```

#### 3.1.3 Ferramenta Genérica — SonarQube

```
Características:
  • Multi-linguagem (Python, JS, Java, Ruby, PHP, etc.)
  • Interface web centralizada
  • Integrável com Jenkins, GitHub Actions, Bitbucket Pipelines, GitLab CI
  • Gestão de riscos compartilhada pela equipe
  • Relatórios e dashboards por projeto
  • Análise de qualidade de código (não apenas segurança)

Execução:
  sonar-scanner \
    -Dsonar.projectKey=meu-projeto \
    -Dsonar.sources=. \
    -Dsonar.host.url=http://localhost:9000 \
    -Dsonar.login=TOKEN

Configuração recomendada:
  • Bloquear pipeline se severidade HIGH for encontrada
  • Quality Gate: 0 vulnerabilidades CRITICAL, 0 HIGH
  • Revisão obrigatória de Security Hotspots
```

#### 3.1.4 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| ST-1 | Tenha pelo menos 1 ferramenta SAST específica da linguagem              | Alta       |
| ST-2 | Tenha 1 ferramenta genérica integrada no CI/CD                          | Alta       |
| ST-3 | Configure hook de Git para rodar SAST local antes do commit             | Média      |
| ST-4 | Bloqueie pipeline de CI se vulnerabilidades HIGH/CRITICAL forem encontradas | Alta       |
| ST-5 | Revise Security Hotspots periodicamente                                  | Média      |
| ST-6 | Ignore diretórios de virtualenv/node_modules nas análises                | Média      |

---

### 3.2 Componente: SCA — Gestão de Dependências

#### 3.2.1 Descrição

SCA monitora continuamente as dependências do projeto em busca de vulnerabilidades conhecidas (CVEs). Uma dependência segura hoje pode se tornar vulnerável amanhã. O monitoramento deve ser contínuo e automatizado, com alertas quando novas CVEs são publicadas.

#### 3.2.2 Ferramenta Específica — pip-audit (Python)

```bash
# Instalação e execução
pip install pip-audit
pip-audit

# Output de exemplo:
# Django 4.0       CVE-2023-xxxxx  CRITICAL  → Atualizar para 4.2.x
# Django 4.0       CVE-2023-xxxxx  HIGH      → Atualizar para 4.2.x
# Flask 0.5        CVE-2019-xxxxx  HIGH      → Atualizar para 2.x
# requests 2.x     CVE-2023-xxxxx  MEDIUM    → Requer versão X.Y.Z+

# Cache renovado automaticamente a cada execução
# Pode ser integrado no hook de Git ou pipeline de CI
```

#### 3.2.3 Ferramenta Genérica — Dependency-Track (OWASP)

```
Setup:
  1. Docker Compose (3 containers: Postgres, Backend, Frontend)
  2. Configurar API Key do NVD (NIST)
  3. Habilitar Google OSV para ecossistemas relevantes (PyPI, NPM, etc.)
  4. Configurar CPE Matching + PURL Matching

Workflow:
  1. pip install pipdeptree cyclonedx-bom
  2. pipdeptree --json-tree > requirements.rtxt
  3. cyclonedx-py requirements.rtxt -o bom.json --format json
  4. Upload BOM no Dependency-Track
  5. Análise automática (diária) contra NVD + OSV

Configurações recomendadas:
  • Mirroring via API (NVD) — não usar feed deprecated
  • Task Scheduler: 24h para análise periódica
  • E-mail: alertar quando novas CVEs forem encontradas
  • CPE Matching: pode gerar falsos positivos, mas é melhor que falsos negativos

Dashboard:
  • Vulnerabilidade por severidade (Critical, High, Medium, Low)
  • Lista de componentes afetados
  • Status: Open / In Analysis / False Positive
  • Histórico de auditorias ao longo do tempo
```

#### 3.2.4 Formato SBOM (Software Bill of Materials)

```
CycloneDX — Formato padronizado de lista de dependências:

{
  "bomFormat": "CycloneDX",
  "specVersion": "1.4",
  "metadata": {
    "component": {
      "name": "meu-projeto",
      "type": "application"
    }
  },
  "components": [
    {
      "name": "Django",
      "version": "4.0",
      "purl": "pkg:pypi/django@4.0",
      "type": "library"
    },
    {
      "name": "fastapi",
      "version": "0.100.0",
      "purl": "pkg:pypi/fastapi@0.100.0",
      "type": "library"
    }
  ]
}

Identificadores:
  PURL (Package URL): pkg:pypi/django@4.0         ← Padrão da comunidade
  CPE (NIST):          cpe:2.3:a:djangoproject:django:4.0:*:*:*:*:*:*:*
```

#### 3.2.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| DP-1 | Monitore dependências continuamente — vulnerabilidades novas aparecem diariamente | Crítica |
| DP-2 | Use ferramenta SCA específica da linguagem no desenvolvimento local      | Alta       |
| DP-3 | Use ferramenta SCA genérica no CI/CD com alertas automáticos            | Alta       |
| DP-4 | Gere SBOM (CycloneDX ou SPDX) para todos os projetos                     | Alta       |
| DP-5 | Configure alertas por e-mail quando novas CVEs forem detectadas         | Alta       |
| DP-6 | Use NVD Mirroring via API — não dependa de feeds deprecated             | Média      |
| DP-7 | Habilite Google OSV para os ecossistemas relevantes                     | Média      |
| DP-8 | Revise falsos positivos e marque no sistema                             | Média      |
| DP-9 | Projetos legados precisam de monitoramento mesmo sem desenvolvimento ativo | Alta       |

---

### 3.3 Componente: Modelagem de Ameaças — STRIDE

#### 3.3.1 Descrição

Modelagem de ameaças é a disciplina de identificar proativamente como um sistema pode ser atacado, antes que o ataque ocorra. Usa o modelo STRIDE para categorizar ameaças e diagramas para mapear componentes, fluxos de dados e limites de confiança.

#### 3.3.2 Modelo STRIDE

| Letra | Ameaça                          | Descrição                                                        |
|-------|----------------------------------|------------------------------------------------------------------|
| **S** | Spoofing                        | Falsificação de identidade (personificação)                     |
| **T** | Tampering                        | Modificação de dados ou código                                   |
| **R** | Repudiation                      | Negar que uma ação foi realizada                                |
| **I** | Information Disclosure           | Vazamento de dados para partes não autorizadas                  |
| **D** | Denial of Service                | Indisponibilidade do sistema                                    |
| **E** | Elevation of Privilege           | Escalação de privilégios (acesso não autorizado a funções admin) |

#### 3.3.3 Componentes do Diagrama

```
┌──────────────────────────────────────────────────────────────────┐
│  COMPONENTES DO DIAGRAMA STRIDE                                  │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐ │
│  │  ACTOR         │  │  PROCESS       │  │  DATA STORE         │ │
│  │  (Externo)     │  │  (Aplicação)   │  │  (Banco de Dados)  │ │
│  │                │  │                │  │                     │ │
│  │  • Parceiros   │  │  • API Proxy   │  │  • PostgreSQL       │ │
│  │  • Usuários    │  │  • Backend     │  │  • Redis            │ │
│  │  • Admins      │  │  • Worker      │  │  • S3               │ │
│  └────────────────┘  └────────────────┘  └────────────────────┘ │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐ │
│  │  DATA FLOW     │  │  TRUST         │  │  BOUNDARY           │ │
│  │  (Fluxo de     │  │  BOUNDARY      │  │  (Limite)           │ │
│  │   Dados)       │  │  (Limite de    │  │                     │ │
│  │                │  │   Confiança)   │  │  • VPN Interna      │ │
│  │  • REST API    │  │                │  │  • Internet         │ │
│  │  • GraphQL     │  │  • Internet    │  │  • Datacenter       │ │
│  │  • PostgreSQL  │  │  • VPN         │  │                     │ │
│  │  • HTTP        │  │  • Permissões  │  │  Fora de escopo:    │ │
│  └────────────────┘  └────────────────┘  │  sistemas parceiros │ │
│                                              └────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

#### 3.3.4 Exemplo de Diagrama — API Proxy

```
┌─ TRUST BOUNDARY: Internet ──────────────────────────────────────┐
│                                                                   │
│  [Sistema Parceiro]  ──REST (HTTPS)──→  ┌─ VPN Interna ──────┐ │
│       FORA DE ESCOPO                      │                     │ │
│                                            │  [API Proxy]       │ │
│                                            │  • Autenticação    │ │
│                                            │  • Rate Limit      │ │
│                                            │       │             │ │
│  [Sistema A] ──GraphQL──→                   │       │ PostgreSQL  │ │
│       FORA DE ESCOPO                      │       ▼             │ │
│                                            │  [Data Store]      │ │
│  [Sistema B] ──REST────→                   │  • Credenciais     │ │
│       FORA DE ESCOPO                      │  • Inventário      │ │
│                                            └─────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

#### 3.3.5 Exemplo de Ameaças Identificadas

| Componente    | Ameaça              | Categoria STRIDE | Severidade | Status      | Mitigação                                    |
|---------------|---------------------|-------------------|------------|-------------|----------------------------------------------|
| API Proxy     | Credential Stuffing  | S (Spoofing)      | Alta       | Open → Mitigated | Token por parceiro + Rate Limit |
| API Proxy     | Outdated Components | S (Spoofing)      | Média      | Open        | Monitorar dependências via Dependency-Track |
| Data Store    | Data Scraping       | I (Info Disclosure)| Alta      | Open        | Criptografia em repouso + permissões no banco |
| Data Store    | Elevation of Privilege | E (EoP)         | Crítica    | Open        | Usuário limitado do proxy, senha própria do DB |
| Data Store    | Denial of Service    | D (DoS)           | Média      | Open        | Rate limit + backup + infra redundante      |

#### 3.3.6 Workflow de Modelagem de Ameaças

```
1. CRIAR diagrama de arquitetura (ThreatDragon ou similar)
2. IDENTIFICAR componentes, atores, fluxos de dados, trust boundaries
3. MARCAR componentes "fora de escopo"
4. LISTAR ameaças para cada componente (sugestões OWASP + brainstorming)
5. CLASSIFICAR severidade (Critical, High, Medium, Low)
6. DEFINIR mitigação para cada ameaça
7. PRIORIZAR e criar tarefas (Jira, Trello, etc.)
8. REVISAR periodicamente (a cada 3 meses ou quando arquitetura mudar)
```

#### 3.3.7 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| TM-1 | Faça modelagem de ameaças para todo novo projeto                        | Alta       |
| TM-2 | Revise diagramas a cada 3 meses ou quando a arquitetura mudar          | Alta       |
| TM-3 | Use STRIDE como modelo de categorização                                 | Média      |
| TM-4 | Marque componentes fora de escopo claramente                            | Média      |
| TM-5 | Cada ameaça deve ter severidade, status e mitigação definida            | Alta       |
| TM-6 | Use OWASP Cornucopia para sessões criativas com a equipe                | Média      |
| TM-7 | Transforme ameaças em tarefas rastreáveis (Jira, Trello)                | Alta       |
| TM-8 | Não presuma que ferramentas substituem pensamento humano                 | Alta       |

---

## 4. Matriz de Ameaças e Mitigações

| # | Ameaça                              | Vetor                         | Impacto                           | Mitigação                                      | Ref. |
|---|-------------------------------------|-------------------------------|-----------------------------------|------------------------------------------------|------|
| 1 | SQL Injection não detectada         | Código sem SAST              | Bypass de autenticação            | Bandit + SonarQube no CI                        | 3.1  |
| 2 | Uso de criptografia fraca (MD5)     | Código sem SAST              | Hash reversível de senhas         | Bandit detecta automaticamente                  | 3.1  |
| 3 | DoS por requisição sem timeout      | Código sem SAST              | Negação de serviço                | Bandit detecta requests sem timeout             | 3.1  |
| 4 | Dependência com CVE crítica         | Django 4.0, Flask 0.5         | RCE, bypass de segurança          | pip-audit + Dependency-Track                    | 3.2  |
| 5 | Nova CVE descoberta em dependência  | Pacote atual ontem, CVE hoje | Vulnerabilidade introduzida       | Monitoramento contínuo + alertas por e-mail      | 3.2  |
| 6 | Projeto legado sem monitoramento    | Software antigo em produção  | Múltiplas CVEs acumuladas         | Dependency-Track para todos os projetos         | 3.2  |
| 7 | Ameaça não identificada             | Falha de modelagem           | Exploração sem defesa             | Modelagem STRIDE + Cornucopia                   | 3.3  |
| 8 | Credential Stuffing                 | API sem rate limit           | Bypass de autenticação            | Token por parceiro + Rate Limit + HIBP          | 3.3  |
| 9 | Elevação de privilégio no DB        | Mesmo usuário para app e DB  | Acesso total ao banco de dados    | Usuários separados com permissões limitadas      | 3.3  |

---

## 5. Checklists de Verificação

### 5.1 Checklist — SAST

- [ ] Ferramenta SAST específica da linguagem está instalada e configurada
- [ ] Ferramenta SAST genérica está integrada no CI/CD
- [ ] Hook de Git roda SAST antes do commit (opcional mas recomendado)
- [ ] Pipeline bloqueia em vulnerabilidades HIGH/CRITICAL
- [ ] Virtualenv/node_modules excluídos das análises
- [ ] Falsos positivos são revisados e documentados
- [ ] Relatórios são gerados em formato acessível (HTML, dashboard)
- [ ] Security Hotspots são revisados pela equipe periodicamente

### 5.2 Checklist — SCA

- [ ] Ferramenta SCA específica da linguagem roda localmente (pip-audit, npm audit, etc.)
- [ ] Plataforma SCA genérica está configurada (Dependency-Track, Snyk, etc.)
- [ ] SBOM é gerado para todos os projetos (CycloneDX ou SPDX)
- [ ] NVD Mirroring via API está configurado com API key válida
- [ ] Google OSV está habilitado para os ecossistemas relevantes
- [ ] Alertas por e-mail estão configurados para novas CVEs
- [ ] Task Scheduler está configurado (análise diária recomendada)
- [ ] Projetos legados estão incluídos no monitoramento
- [ ] Falsos positivos são marcados no sistema

### 5.3 Checklist — Modelagem de Ameaças

- [ ] Diagrama de arquitetura foi criado com STRIDE
- [ ] Todos os componentes, atores e fluxos de dados estão mapeados
- [ ] Trust boundaries estão definidos (Internet, VPN, permissões)
- [ ] Componentes fora de escopo estão marcados
- [ ] Ameaças foram identificadas para cada componente
- [ ] Cada ameaça tem severidade e status definidos
- [ ] Mitigações foram propostas e discutidas com a equipe
- [ ] Tarefas foram criadas em ferramenta de rastreamento (Jira, etc.)
- [ ] OWASP Cornucopia foi jogado com a equipe (recomendado)
- [ ] Revisão agendada para 3 meses ou quando arquitetura mudar

---

## 6. Tabela Comparativa — Ferramentas

### 6.1 SAST

| Ferramenta   | Tipo        | Linguagens           | Interface   | CI/CD | Custo    |
|--------------|-------------|----------------------|-------------|-------|----------|
| **Bandit**   | Específica  | Python               | CLI + HTML  | Hook  | Gratuito |
| **Brakeman** | Específica  | Ruby on Rails        | CLI + HTML  | Hook  | Gratuito |
| **SonarQube**| Genérica    | Multi (20+)          | Web         | Plugin| Free/Paid|

### 6.2 SCA

| Ferramenta          | Tipo        | Linguagens           | Interface   | Alertas | Custo    |
|---------------------|-------------|----------------------|-------------|--------|----------|
| **pip-audit**       | Específica  | Python               | CLI         | Manual | Gratuito |
| **npm audit**       | Específica  | Node.js              | CLI         | Manual | Gratuito |
| **Dependency-Track**| Genérica    | Multi (SBOM)         | Web         | E-mail | Gratuito |

### 6.3 Modelagem de Ameaças

| Ferramenta                | Tipo           | Formato             | Interface    | Custo    |
|---------------------------|----------------|---------------------|--------------|----------|
| **ThreatDragon**          | Diagrama       | STRIDE              | Desktop/Web  | Gratuito |
| **MS Threat Modeling Tool**| Diagrama      | STRIDE              | Desktop      | Gratuito |
| **OWASP Cornucopia**      | Jogo de cartas | Categorias OWASP   | Cartas/Web   | Gratuito |

---

## 7. Referências

| Recurso                      | URL/Descrição                                             |
|------------------------------|-----------------------------------------------------------|
| OWASP — List of SAST Tools   | https://owasp.org/www-community/Source_Code_Analysis_Tools |
| OWASP — Dependency-Track      | https://dependencytrack.org/                              |
| OWASP — ThreatDragon          | https://owasp.org/www-project-threat-dragon/              |
| OWASP — Cornucopia            | https://owasp.org/www-project-cornucopia/                 |
| OWASP — CycloneDX             | https://owasp.org/www-project-cyclonedx/                  |
| NVD (NIST)                   | https://nvd.nist.gov/                                     |
| OSV (Google)                 | https://osv.dev/                                          |
| Bandit (Python SAST)         | https://github.com/PyCQA/bandit                           |
| pip-audit                    | https://github.com/pypa/pip-audit                         |
| SonarQube                    | https://www.sonarqube.org/                                |
