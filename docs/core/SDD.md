# SDD — Software Design Document

## 1. Visão Geral da Arquitetura

### 1.1 Padrão arquitetural

Monolito MVC servido por um único processo FastAPI que:

- Expõe a API REST em `/api/*`
- Serve os arquivos estáticos do build do Next.js em `/*`
- Comunica-se com o PostgreSQL via asyncpg
- Integra LangChain 1.x e LangGraph 1.x para as ferramentas de SEO com IA

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                       │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │                   FastAPI                          │  │
│  │                                                    │  │
│  │  /api/*  →  Routers → Services → Models (DB)      │  │
│  │                                                    │  │
│  │  /api/ferramentas/* → Services → Agents           │  │
│  │                              (LangChain/LangGraph) │  │
│  │                                                    │  │
│  │  /*      →  StaticFiles (build Next.js)           │  │
│  └────────────────────┬──────────────────────────────┘  │
│                       │                                 │
│                  asyncpg                                 │
│                       │                                 │
└───────────────────────┼─────────────────────────────────┘
                        │
              ┌─────────┴─────────┐
              │   PostgreSQL 16    │
              │  (Docker Compose)  │
              └───────────────────┘
```

### 1.2 Decisões arquiteturais

| Decisão | Escolha | Justificativa |
|---|---|---|
| Monolito | Simples, um deploy | MVP, redução de complexidade operacional |
| FastAPI serve Next.js build | Build estático servido pelo Python | Elimina necessidade de Node.js em produção |
| MVC | Controllers (routers), Services (business), Models (data) | Separação de responsabilidades clara |
| Async | Toda a stack async (FastAPI, SQLAlchemy, asyncpg) | Desempenho com I/O bound (LLM calls) |
| ORM | SQLAlchemy 2.0 async | Maturidade, typed, migrações via Alembic |

---

## 2. Stack Tecnológico

### 2.1 Backend

| Tecnologia | Versão | Papel |
|---|---|---|
| Python | 3.14.4 | Runtime |
| FastAPI | latest | Framework web async |
| Uvicorn | latest | ASGI server |
| SQLAlchemy | 2.0.x | ORM async |
| asyncpg | latest | Driver PostgreSQL async |
| Alembic | latest | Migrações de banco |
| Pydantic | 2.x | Validação e serialização |
| LangChain | 1.2.x | Framework de integração LLM |
| LangGraph | 1.1.x | Orquestração de agentes (grafos) |
| argon2-cffi | latest | Hash de senhas (Argon2id) |
| PyJWT | latest | Tokens JWT (access + refresh) |
| pyotp | latest | Geração/validação TOTP |
| python-dateutil | latest | Manipulação de datas |
| uv | latest | Gerenciador de pacotes |

### 2.2 Frontend

| Tecnologia | Versão | Papel |
|---|---|---|
| Next.js | 16.x | Framework React (output: static) |
| React | 19.x | UI library |
| TypeScript | 5.x | Tipagem |
| Tailwind CSS | 4.x | Utility-first CSS |
| shadcn | 3.5.x | Componentes UI acessíveis |
| Node.js | 20.9+ | Runtime build (desenvolvimento) |

### 2.3 Infraestrutura

| Tecnologia | Papel |
|---|---|
| Docker | Containerização |
| Docker Compose | Orquestração local (app + PostgreSQL) |
| PostgreSQL 16 | Banco de dados relacional |
| GitHub Actions | CI/CD |

---

## 3. Estrutura de Diretórios

```
/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── usuario.py
│   │   │   ├── cliente.py
│   │   │   ├── plano.py
│   │   │   ├── conta_creditos.py
│   │   │   ├── transacao_credito.py
│   │   │   ├── execucao_ferramenta.py
│   │   │   ├── mfa_dispositivo.py
│   │   │   ├── sessao.py
│   │   │   ├── reset_senha_token.py
│   │   │   ├── pacote_credito.py
│   │   │   └── compra.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── cliente.py
│   │   │   ├── credito.py
│   │   │   ├── ferramenta.py
│   │   │   ├── billing.py
│   │   │   └── usuario.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── clientes.py
│   │   │   ├── ferramentas.py
│   │   │   ├── creditos.py
│   │   │   ├── billing.py
│   │   │   └── configuracoes.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── cliente_service.py
│   │   │   ├── credito_service.py
│   │   │   ├── billing_service.py
│   │   │   ├── mfa_service.py
│   │   │   └── ferramenta_service.py
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── gerar_artigo.py
│   │   │   ├── gerar_outline.py
│   │   │   ├── mapear_interlinks.py
│   │   │   ├── revisar_conteudo.py
│   │   │   ├── gerar_faq.py
│   │   │   ├── analisar_keywords.py
│   │   │   ├── gerar_schema.py
│   │   │   ├── gerar_h1.py
│   │   │   ├── gerar_meta_description.py
│   │   │   └── gerar_title_tag.py
│   │   └── core/
│   │       ├── __init__.py
│   │       ├── seguranca.py
│   │       ├── middleware.py
│   │       ├── excecoes.py
│   │       └── validacao.py
│   ├── db/
│   │   ├── __init__.py
│   │   └── session.py
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_clientes.py
│   │   ├── test_creditos.py
│   │   └── test_ferramentas.py
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   ├── (publico)/
│   │   │   │   ├── login/page.tsx
│   │   │   │   ├── cadastro/page.tsx
│   │   │   │   └── recuperar-senha/page.tsx
│   │   │   ├── (app)/
│   │   │   │   ├── layout.tsx
│   │   │   │   ├── dashboard/page.tsx
│   │   │   │   ├── clientes/
│   │   │   │   │   ├── page.tsx
│   │   │   │   │   └── [id]/page.tsx
│   │   │   │   ├── ferramentas/
│   │   │   │   │   ├── page.tsx
│   │   │   │   │   └── [slug]/page.tsx
│   │   │   │   ├── creditos/page.tsx
│   │   │   │   ├── historico/page.tsx
│   │   │   │   └── configuracoes/page.tsx
│   │   ├── components/
│   │   │   ├── ui/
│   │   │   ├── layout/
│   │   │   │   ├── cabecalho.tsx
│   │   │   │   ├── barra-lateral.tsx
│   │   │   │   └── saldo-creditos.tsx
│   │   │   ├── clientes/
│   │   │   │   ├── formulario-cliente.tsx
│   │   │   │   └── card-cliente.tsx
│   │   │   ├── ferramentas/
│   │   │   │   ├── formulario-ferramenta.tsx
│   │   │   │   └── resultado-ferramenta.tsx
│   │   │   └── auth/
│   │   │       ├── formulario-login.tsx
│   │   │       ├── formulario-cadastro.tsx
│   │   │       └── formulario-mfa.tsx
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── auth.ts
│   │   │   └── utils.ts
│   │   ├── hooks/
│   │   │   ├── use-auth.ts
│   │   │   ├── use-creditos.ts
│   │   │   └── use-clientes.ts
│   │   ├── types/
│   │   │   └── index.ts
│   │   └── styles/
│   │       └── globals.css
│   ├── public/
│   ├── next.config.ts
│   ├── package.json
│   └── tsconfig.json
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
└── docs/
    ├── core/
    │   ├── PRD.md
    │   └── SDD.md
    └── Security/
        └── (12 SDDs de segurança)
```

### 3.1 Convenções de nomenclatura

| Elemento | Regra | Exemplo |
|---|---|---|
| Arquivos Python | snake_case | `auth_service.py` |
| Arquivos TypeScript/TSX | kebab-case | `formulario-login.tsx` |
| Classes Python | PascalCase | `UsuarioService` |
| Funções Python | snake_case | `verificar_senha` |
| Variáveis Python | snake_case | `saldo_creditos` |
| Componentes React | PascalCase | `FormularioLogin` |
| Colunas banco | snake_case | `criado_em` |
| Tabelas banco | snake_case (plural) | `usuarios`, `clientes` |
| APIs rotas | kebab-case | `/api/creditos/saldo` |

---

## 4. Modelos de Banco de Dados

### 4.1 `usuarios`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK, default gen | Identificador único |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | E-mail do usuário |
| `nome` | VARCHAR(255) | NOT NULL | Nome de exibição |
| `senha_hash` | VARCHAR(255) | NOT NULL | Hash Argon2id da senha |
| `email_verificado` | BOOLEAN | NOT NULL, default false | E-mail confirmado |
| `plano_id` | UUID | FK → planos.id | Plano atual |
| `mfa_ativo` | BOOLEAN | NOT NULL, default false | MFA habilitado |
| `ativo` | BOOLEAN | NOT NULL, default true | Conta ativa |
| `criado_em` | TIMESTAMPTZ | NOT NULL, default now() | Data de criação |
| `atualizado_em` | TIMESTAMPTZ | NOT NULL, default now() | Última atualização |

**Indexes:** `idx_usuarios_email` (email)

### 4.2 `planos`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `nome` | VARCHAR(50) | UNIQUE, NOT NULL | `free`, `pro`, `business` |
| `creditos_por_mes` | INTEGER | NOT NULL | Créditos mensais |
| `preco_mensal` | DECIMAL(10,2) | NOT NULL | Preço em reais |
| `cliente_limite` | INTEGER | NOT NULL | -1 = ilimitado |
| `permite_extras` | BOOLEAN | NOT NULL | Permite créditos extras |
| `ativo` | BOOLEAN | NOT NULL, default true | Plano disponível |

**Dados iniciais:**

| nome | creditos_por_mes | preco_mensal | cliente_limite | permite_extras |
|---|---|---|---|---|
| free | 50 | 0.00 | 3 | false |
| pro | 500 | 97.00 | 15 | true |
| business | 2000 | 247.00 | -1 | true |

### 4.3 `clientes`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → usuarios.id, NOT NULL | Dono |
| `nome` | VARCHAR(255) | NOT NULL | Nome do cliente |
| `site_url` | VARCHAR(500) | nullable | URL do site |
| `config_json` | JSONB | NOT NULL, default {} | Persona, palavras proibidas, instruções |
| `ativo` | BOOLEAN | NOT NULL, default true | Soft delete |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criação |
| `atualizado_em` | TIMESTAMPTZ | NOT NULL | Atualização |

**Indexes:** `idx_clientes_usuario_id` (usuario_id)

**Estrutura de `config_json`:**

```json
{
  "persona": "Redator especialista em marketing digital",
  "palavras_proibidas": ["impulsionar", "surpreendente"],
  "instrucoes": "Use tom formal mas acessível",
  "niche": "marketing digital"
}
```

### 4.4 `contas_creditos`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → usuarios.id, UNIQUE | Um registro por usuário |
| `saldo_plano` | INTEGER | NOT NULL, default 0 | Créditos do plano atual |
| `saldo_extras` | INTEGER | NOT NULL, default 0 | Créditos extras (não expiram) |
| `ciclo_inicio` | DATE | NOT NULL | Início do ciclo atual |
| `ciclo_fim` | DATE | NOT NULL | Fim do ciclo atual |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criação |
| `atualizado_em` | TIMESTAMPTZ | NOT NULL | Atualização |

**Propriedade computada:** `saldo_total = saldo_plano + saldo_extras`

### 4.5 `transacoes_creditos`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `conta_id` | UUID | FK → contas_creditos.id, NOT NULL | Conta |
| `tipo` | VARCHAR(30) | NOT NULL | `renovacao`, `debito`, `credito_extra`, `ajuste` |
| `quantidade` | INTEGER | NOT NULL | Positivo = crédito, Negativo = débito |
| `descricao` | VARCHAR(500) | NOT NULL | Descrição legível |
| `ferramenta` | VARCHAR(50) | nullable | Nome da ferramenta (se débito) |
| `execucao_id` | UUID | FK → execucoes_ferramentas.id, nullable | Relação com execução |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criação |

**Indexes:** `idx_transacoes_conta_id` (conta_id, criado_em DESC)

### 4.6 `execucoes_ferramentas`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → usuarios.id, NOT NULL | Usuário |
| `cliente_id` | UUID | FK → clientes.id, nullable | Cliente (quando aplicável) |
| `ferramenta` | VARCHAR(50) | NOT NULL | Nome da ferramenta |
| `creditos_cobrados` | INTEGER | NOT NULL | Créditos debitados |
| `status` | VARCHAR(20) | NOT NULL | `pendente`, `executando`, `concluida`, `falhou` |
| `entrada_json` | JSONB | NOT NULL | Input do usuário |
| `resultado_json` | JSONB | nullable | Output da ferramenta |
| `erro_msg` | VARCHAR(1000) | nullable | Mensagem de erro |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criação |
| `concluida_em` | TIMESTAMPTZ | nullable | Conclusão |

**Enums de ferramenta:** `gerar_artigo`, `gerar_outline`, `mapear_interlinks`, `revisar_conteudo`, `gerar_faq`, `analisar_keywords`, `gerar_schema`, `gerar_h1`, `gerar_meta_description`, `gerar_title_tag`

**Indexes:** `idx_execucoes_usuario_id` (usuario_id, criado_em DESC)

### 4.7 `mfa_dispositivos`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → usuarios.id, NOT NULL | Usuário |
| `tipo` | VARCHAR(20) | NOT NULL | `totp`, `fido2` |
| `nome` | VARCHAR(100) | NOT NULL | "iPhone do João" |
| `segredo_totp` | VARCHAR(255) | nullable (encrypted) | Segredo TOTP (criptografado) |
| `credential_id` | BYTEA | nullable | FIDO2 credential ID |
| `public_key` | BYTEA | nullable | FIDO2 public key |
| `counter` | INTEGER | nullable | FIDO2 counter |
| `ultimo_uso` | TIMESTAMPTZ | nullable | Último uso |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criação |

**Indexes:** `idx_mfa_usuario_id` (usuario_id)

### 4.8 `sessoes`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → usuarios.id, NOT NULL | Usuário |
| `token_hash` | VARCHAR(255) | UNIQUE, NOT NULL | Hash do refresh token |
| `ip` | VARCHAR(45) | NOT NULL | IP do cliente |
| `user_agent` | VARCHAR(500) | NOT NULL | User-Agent |
| `expira_em` | TIMESTAMPTZ | NOT NULL | Expiração |
| `revogada` | BOOLEAN | NOT NULL, default false | Sessão revogada |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criação |

**Indexes:** `idx_sessoes_token_hash` (token_hash), `idx_sessoes_usuario_id` (usuario_id)

### 4.9 `reset_senha_tokens`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → usuarios.id, NOT NULL | Usuário |
| `token_hash` | VARCHAR(255) | UNIQUE, NOT NULL | Hash do token |
| `usado` | BOOLEAN | NOT NULL, default false | Já foi usado |
| `expira_em` | TIMESTAMPTZ | NOT NULL | Expiração (1h) |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criação |

### 4.10 `pacotes_creditos`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `nome` | VARCHAR(50) | NOT NULL | `boost_100`, `boost_500`, `boost_1500` |
| `creditos` | INTEGER | NOT NULL | Quantidade de créditos |
| `preco` | DECIMAL(10,2) | NOT NULL | Preço em reais |
| `ativo` | BOOLEAN | NOT NULL, default true | Disponível |

**Dados iniciais:**

| nome | creditos | preco |
|---|---|---|
| boost_100 | 100 | 29.00 |
| boost_500 | 500 | 97.00 |
| boost_1500 | 1500 | 197.00 |

### 4.11 `compras`

| Coluna | Tipo | Restrição | Descrição |
|---|---|---|---|
| `id` | UUID | PK | Identificador |
| `usuario_id` | UUID | FK → usuarios.id, NOT NULL | Usuário |
| `tipo` | VARCHAR(20) | NOT NULL | `assinatura`, `addon` |
| `pacote_id` | UUID | FK → pacotes_creditos.id, nullable | Pacote (se addon) |
| `plano_id` | UUID | FK → planos.id, nullable | Plano (se assinatura) |
| `valor_pago` | DECIMAL(10,2) | NOT NULL | Valor pago |
| `gateway_id` | VARCHAR(255) | nullable | ID da transação no gateway |
| `status` | VARCHAR(20) | NOT NULL | `pendente`, `pago`, `cancelado`, `reembolsado` |
| `criado_em` | TIMESTAMPTZ | NOT NULL | Criação |

**Indexes:** `idx_compras_usuario_id` (usuario_id, criado_em DESC)

### 4.12 Diagrama ER (relações)

```
usuarios 1──1 contas_creditos
usuarios 1──N clientes
usuarios 1──N mfa_dispositivos
usuarios 1──N sessoes
usuarios 1──N reset_senha_tokens
usuarios 1──N compras
usuarios 1──N transacoes_creditos (via contas_creditos)
usuarios 1──N execucoes_ferramentas
contas_creditos 1──N transacoes_creditos
clientes 1──N execucoes_ferramentas
execucoes_ferramentas 1──1 transacoes_creditos
planos 1──N usuarios
planos 1──N compras
pacotes_creditos 1──N compras
```

---

## 5. API Endpoints (FastAPI)

### 5.1 Autenticação

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| POST | `/api/auth/cadastro` | Criar conta | Não |
| POST | `/api/auth/login` | Login (email + senha) | Não |
| POST | `/api/auth/mfa/verificar` | Verificar código MFA | Parcial* |
| POST | `/api/auth/logout` | Revogar sessão | Sim |
| POST | `/api/auth/refresh` | Renovar access token | Refresh token |
| GET | `/api/auth/me` | Dados do usuário atual | Sim |
| POST | `/api/auth/recuperar-senha` | Enviar e-mail de reset | Não |
| POST | `/api/auth/resetar-senha` | Redefinir senha com token | Token de reset |
| PUT | `/api/auth/alterar-senha` | Alterar senha (logado) | Sim |
| POST | `/api/auth/mfa/configurar` | Iniciar configuração MFA | Sim |
| POST | `/api/auth/mfa/ativar` | Ativar MFA após verificação | Sim |
| DELETE | `/api/auth/mfa/{id}` | Remover dispositivo MFA | Sim + MFA |

*Parcial = requer token temporário retornado pelo login quando MFA está ativo.

### 5.2 Clientes

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| GET | `/api/clientes` | Listar clientes do usuário | Sim |
| POST | `/api/clientes` | Criar cliente | Sim |
| GET | `/api/clientes/{id}` | Detalhes do cliente | Sim + Dono |
| PUT | `/api/clientes/{id}` | Editar cliente | Sim + Dono |
| DELETE | `/api/clientes/{id}` | Remover cliente (soft) | Sim + Dono |
| PUT | `/api/clientes/{id}/configuracoes` | Atualizar config_json | Sim + Dono |

### 5.3 Ferramentas de SEO

| Método | Rota | Descrição | Créditos |
|---|---|---|---|
| POST | `/api/ferramentas/gerar-artigo` | Gerar artigo completo | 25 |
| POST | `/api/ferramentas/gerar-outline` | Gerar outline/estrutura | 8 |
| POST | `/api/ferramentas/mapear-interlinks` | Mapear interlinks | 12 |
| POST | `/api/ferramentas/revisar-conteudo` | Revisar conteúdo SEO | 10 |
| POST | `/api/ferramentas/gerar-faq` | Gerar FAQ | 5 |
| POST | `/api/ferramentas/analisar-keywords` | Analisar palavras-chave | 6 |
| POST | `/api/ferramentas/gerar-schema` | Gerar dados estruturados | 4 |
| POST | `/api/ferramentas/gerar-h1` | Gerar H1 otimizado | 3 |
| POST | `/api/ferramentas/gerar-meta-description` | Gerar meta description | 3 |
| POST | `/api/ferramentas/gerar-title-tag` | Gerar title tag | 3 |
| GET | `/api/ferramentas/historico` | Listar execuções | — |
| GET | `/api/ferramentas/historico/{id}` | Detalhes da execução | — |
| GET | `/api/ferramentas/custos` | Tabela de custos por ação | — |

Todas as rotas POST de ferramentas seguem o mesmo padrão de request:

```json
{
  "cliente_id": "uuid (opcional)",
  "parametros": { ... }
}
```

Response:

```json
{
  "id": "uuid",
  "ferramenta": "gerar_artigo",
  "status": "concluida",
  "creditos_cobrados": 25,
  "resultado": { ... },
  "criado_em": "2026-04-19T10:00:00Z"
}
```

### 5.4 Créditos

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| GET | `/api/creditos/saldo` | Saldo detalhado | Sim |
| GET | `/api/creditos/transacoes` | Histórico de transações | Sim |

Response `/api/creditos/saldo`:

```json
{
  "saldo_plano": 350,
  "saldo_extras": 0,
  "saldo_total": 350,
  "plano": "pro",
  "ciclo_inicio": "2026-04-01",
  "ciclo_fim": "2026-05-01",
  "alerta_baixo": false,
  "alerta_zerado": false
}
```

### 5.5 Billing

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| GET | `/api/billing/plano` | Plano atual do usuário | Sim |
| PUT | `/api/billing/plano` | Alterar plano | Sim |
| GET | `/api/billing/pacotes` | Pacotes de créditos extras | Sim |
| POST | `/api/billing/comprar-pacote` | Comprar pacote | Sim |
| GET | `/api/billing/historico` | Histórico de compras | Sim |

### 5.6 Configurações do Usuário

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| GET | `/api/configuracoes/perfil` | Perfil do usuário | Sim |
| PUT | `/api/configuracoes/perfil` | Atualizar perfil | Sim |
| DELETE | `/api/configuracoes/conta` | Excluir conta (soft) | Sim |

---

## 6. Integração LangChain/LangGraph

### 6.1 Arquitetura geral

```
Router (FastAPI)
    │
    ▼
FerramentaService
    │
    ├── CreditoService.debitar (antes da execução)
    │
    ▼
Agent (LangChain/LangGraph)
    │
    ├── LLM (OpenAI/Anthropic via LangChain)
    │
    ▼
Resultado
    │
    ├── Salvar em execucoes_ferramentas
    └── Retornar response
```

### 6.2 Decisão: `create_agent` vs LangGraph direto

| Ferramenta | Abordagem | Justificativa |
|---|---|---|
| `gerar_artigo` | LangGraph direto | Workflow multi-step com branching condicional |
| `gerar_outline` | LangGraph direto | Workflow estruturado com validação |
| `mapear_interlinks` | LangGraph direto | Embeddings + similaridade + formatação |
| `revisar_conteudo` | `create_agent` | Análise com instrução única |
| `gerar_faq` | `create_agent` | Geração simples com prompt |
| `analisar_keywords` | LangGraph direto | Múltiplas chamadas + classificação |
| `gerar_schema` | `create_agent` | Template-based simples |
| `gerar_h1` | `create_agent` | Chamada única LLM |
| `gerar_meta_description` | `create_agent` | Chamada única LLM |
| `gerar_title_tag` | `create_agent` | Chamada única LLM |

### 6.3 Agente base (`agents/base.py`)

Todas as ferramentas herdam de um agente base que injeta:

- Configurações do cliente (persona, palavras proibidas, instruções)
- System prompt padrão SEO
- Validação de entrada
- Tratamento de erros
- Logging estruturado

### 6.4 Workflows LangGraph detalhados

#### 6.4.1 `gerar_artigo` (25 créditos)

```
INICIO → receber_input
    → analisar_contexto (LLM: extrair tópico, tom, público)
    → gerar_outline_interno (LLM: estrutura do artigo)
    → [branch: outline aprovada?]
        → NÃO: ajustar_outline → gerar_outline_interno
        → SIM: expandir_secoes (LLM: uma seção por chamada)
    → revisar_artigo (LLM: checar SEO, coerência, plágio)
    → [branch: revisão aprovada?]
        → NÃO: corrigir_artigo → revisar_artigo
        → SIM: formatar_saida
    → FIM
```

Nodes: 6-8 chamadas LLM dependendo dos ciclos de revisão.

#### 6.4.2 `gerar_outline` (8 créditos)

```
INICIO → receber_input
    → pesquisar_tema (LLM: extrair tópicos relevantes)
    → estruturar_topicos (LLM: organizar hierarquia H2/H3)
    → validar_outline (regras SEO: profundidade, contagem)
    → formatar_saida
    → FIM
```

Nodes: 3 chamadas LLM.

#### 6.4.3 `mapear_interlinks` (12 créditos)

```
INICIO → receber_input (lista de páginas/URLs)
    → extrair_conteudo (processar cada página)
    → gerar_embeddings (embedding model)
    → calcular_similaridade (cosine similarity)
    → filtrar_relevantes (threshold > 0.7)
    → sugerir_interlinks (LLM: contextualizar sugestões)
    → formatar_saida
    → FIM
```

Nodes: 1 embedding batch + 1 LLM call.

#### 6.4.4 `analisar_keywords` (6 créditos)

```
INICIO → receber_input (palavras-chave semente)
    → expandir_keywords (LLM: gerar variações)
    → classificar_intencao (LLM: informacional/transacional/navegacional)
    → estimar_dificuldade (LLM: alta/média/baixa)
    → formatar_saida
    → FIM
```

Nodes: 2 chamadas LLM.

### 6.5 Configuração LLM

O modelo LLM é configurável via `config.py`:

```python
# Exemplo de configuração
LLM_PROVIDER = "openai"  # ou "anthropic"
LLM_MODEL = "gpt-4o"
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 4096
EMBEDDING_MODEL = "text-embedding-3-small"
```

### 6.6 Tratamento de falhas

- Se o LLM retornar erro → status `falhou`, créditos NÃO são debitados
- Se o workflow falhar midway → status `falhou`, rollback de créditos
- Timeout de 60s por ferramenta (configurável)
- Retry automático: 1 retry com exponential backoff

---

## 7. Sistema de Créditos

### 7.1 Fluxo de consumo

```
Request POST /api/ferramentas/{slug}
    │
    ▼
middleware autenticação → identificar usuário
    │
    ▼
CreditoService.verificar_saldo(usuario, custo)
    │
    ├── saldo_total >= custo?
    │   ├── SIM → prosseguir
    │   └── NÃO → HTTP 402 (Payment Required)
    │
    ▼
FerramentaService.executar(slug, parametros)
    │
    ├── SUCESSO
    │   ├── CreditoService.debitar(usuario, custo, tipo="debito")
    │   │   ├── saldo_plano >= custo?
    │   │   │   ├── SIM → debitar de saldo_plano
    │   │   │   └── NÃO → debitar de saldo_extras (diferença)
    │   │   └── criar transacao_credito
    │   └── retornar resultado
    │
    └── FALHA
        ├── NÃO debitar créditos
        ├── status = "falhou"
        └── retornar erro
```

### 7.2 Serviço de créditos (`services/credito_service.py`)

Métodos principais:

- `obter_saldo(usuario_id)` → retorna saldo detalhado
- `verificar_saldo(usuario_id, custo)` → bool
- `debitar(usuario_id, quantidade, ferramenta, execucao_id)` → transação
- `creditar_plano(usuario_id, quantidade)` → renovação mensal
- `creditar_extras(usuario_id, quantidade, pacote)` → compra de pacote
- `renovar_ciclos()` → cron: renova ciclos vencidos

### 7.3 Renovação mensal (cron job)

Executado via APScheduler integrado ao FastAPI:

```python
@scheduler.scheduled_job("cron", hour=0, minute=0)
async def renovar_ciclos_vencidos():
    contas = await conta_repo.buscar_ciclos_vencidos(hoje)
    for conta in contas:
        plano = await plano_repo.buscar(conta.usuario.plano_id)
        conta.saldo_plano = plano.creditos_por_mes
        conta.ciclo_inicio = hoje
        conta.ciclo_fim = hoje + timedelta(days=30)
        await conta_repo.salvar(conta)
        await transacao_repo.criar(
            conta_id=conta.id,
            tipo="renovacao",
            quantidade=plano.creditos_por_mes,
            descricao=f"Renovação mensal - Plano {plano.nome}"
        )
```

### 7.4 Regras de débito

1. Sempre debitar primeiro do `saldo_plano`
2. Se `saldo_plano` for insuficiente, debitar a diferença de `saldo_extras`
3. Se `saldo_total` (soma) for insuficiente, negar a requisição (HTTP 402)
4. Créditos extras nunca expiram
5. Créditos do plano não acumulam entre ciclos

### 7.5 Alertas no frontend

| Condição | Comportamento |
|---|---|
| `saldo_total <= 20% do plano` | Banner amarelo: "Seus créditos estão acabando" |
| `saldo_total == 0` | Banner vermelho: "Créditos esgotados" + botão upgrade |
| `saldo_total > 0` | Exibição normal do saldo no header |

---

## 8. Autenticação Customizada

### 8.1 Visão geral

Autenticação própria (sem Supabase Auth), seguindo integralmente os SDDs de segurança:
- `SDD_Autenticacao_e_Seguranca.md`
- `SDD_Recuperacao_e_Reset_de_Senha.md`

### 8.2 Hash de senhas — Argon2id

Parâmetros (conforme SDD de Autenticação):
- Algoritmo: Argon2id
- Memory cost: 65536 (64 MB)
- Time cost: 3
- Parallelism: 4
- Salt length: 16 bytes
- Hash length: 32 bytes

Implementação: `argon2-cffi` com `argon2.PasswordHasher()` customizado.

### 8.3 JWT — Access + Refresh tokens

| Token | Tempo de vida | Armazenamento | Uso |
|---|---|---|---|
| Access | 15 minutos | Memória (frontend) | Auth header `Bearer` |
| Refresh | 7 dias | httpOnly cookie | Renovar access token |

Payload do access token:

```json
{
  "sub": "uuid-do-usuario",
  "email": "user@example.com",
  "mfa_ativo": false,
  "tipo": "access",
  "exp": 1234567890,
  "iat": 1234567890
}
```

### 8.4 Fluxo de login com MFA

```
POST /api/auth/login { email, senha }
    │
    ├── MFA desativado
    │   ├── Gerar access + refresh tokens
    │   ├── Criar sessão no banco
    │   └── Retornar access token + setar cookie refresh
    │
    └── MFA ativado
        ├── Gerar token temporário (5 min, não é access token)
        ├── Retornar { mfa_requerido: true, token_temporario: "..." }
        │
        ▼
POST /api/auth/mfa/verificar { token_temporario, codigo_totp }
    │
    ├── Validar código TOTP
    ├── Gerar access + refresh tokens
    ├── Criar sessão
    └── Retornar access token + setar cookie refresh
```

### 8.5 MFA — TOTP

Implementação: `pyotp` + segredo armazenado criptografado no banco.

Fluxo de configuração:
1. `POST /api/auth/mfa/configurar` → gera segredo TOTP, retorna QR code (base64)
2. Usuário escaneia QR code com app autenticador
3. `POST /api/auth/mfa/ativar` → usuário envia código gerado, sistema valida e ativa MFA
4. Requer que o usuário já esteja logado e confirme a senha atual

### 8.6 MFA — FIDO2/WebAuthn

Implementação: `webauthn` (Python library).

Fluxo de configuração:
1. `POST /api/auth/mfa/configurar` (tipo=fido2) → gera challenge + options
2. Navegador usa WebAuthn API para registrar
3. `POST /api/auth/mfa/ativar` (tipo=fido2) → valida registro, armazena credential

O FIDO2 é opcional no MVP. TOTP é obrigatório quando MFA está ativo.

### 8.7 Reset de senha

Conforme `SDD_Recuperacao_e_Reset_de_Senha.md`:

1. `POST /api/auth/recuperar-senha` → recebe e-mail
2. Sistema gera token UUID aleatório, armazena hash (SHA-256) no banco com expiração de 1 hora
3. Envia e-mail com link contendo o token (não o hash)
4. `POST /api/auth/resetar-senha` → recebe token + nova senha
5. Valida token: existe, não usado, não expirado
6. Valida nova senha contra política de força
7. Hasheia com Argon2id, atualiza banco, marca token como usado
8. Revoga todas as sessões do usuário
9. Token de reset é de uso único e não pode ser reutilizado

### 8.8 Middleware de autenticação (`core/middleware.py`)

```python
async def middleware_autenticacao(request, call_next):
    caminho = request.url.path
    if caminho.startswith("/api/auth/") and caminho not in ROTAS_PROTEGIDAS:
        return await call_next(request)
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401)
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    usuario = await usuario_repo.buscar(payload["sub"])
    if not usuario or not usuario.ativo:
        raise HTTPException(401)
    request.state.usuario = usuario
    response = await call_next(request)
    return response
```

### 8.9 Políticas de senha

- Mínimo 12 caracteres
- Pelo menos 1 letra maiúscula
- Pelo menos 1 letra minúscula
- Pelo menos 1 número
- Pelo menos 1 caractere especial
- Não pode ser igual às últimas 5 senhas (hashes armazenados)
- Verificação contra lista de senhas comuns (HaveIBeenPwned via k-anonymity API)

---

## 9. Mapeamento de Segurança

Cada um dos 12 SDDs de segurança é mapeado para componentes específicos da implementação.

### 9.1 Tabela de mapeamento

| SDD de Segurança | Arquivo | Seções SDD | Implementação no código |
|---|---|---|---|
| `SDD_Autenticacao_e_Seguranca` | Autenticação e Segurança | Argon2id, MFA, rate limiting | `core/seguranca.py`, `services/auth_service.py`, `services/mfa_service.py`, `core/middleware.py` |
| `SDD_Recuperacao_e_Reset_de_Senha` | Reset de Senha | Token seguro, expiração, uso único | `services/auth_service.py`, `models/reset_senha_token.py` |
| `SDD_Seguranca_Backend` | Backend | SSRF, CSRF, redirects seguros | `core/middleware.py` (CSRF tokens), `core/validacao.py` (validação URLs), `services/ferramenta_service.py` |
| `SDD_Seguranca_Backend_Validacao` | Backend Validação | IDOR, validação de tipos, sanitização | `core/validacao.py`, `dependencies.py` (verificação de propriedade), `routers/*.py` |
| `SDD_Seguranca_Backend_Avançado` | Backend Avançado | SQL Injection, Command Injection, desserialização, reporte de erros | SQLAlchemy ORM (parametrizado), `core/validacao.py` (input sanitization), `core/excecoes.py` (error handling), logging sem dados sensíveis |
| `SDD_Seguranca_Frontend` | Frontend | SRI, CSP, Clickjacking, Tag Manager | `main.py` (CSP headers), Next.js config, shadcn components, layout components |
| `SDD_Seguranca_HTML5` | HTML5 | LocalStorage, iFrames, WebMessaging, Tab-nabbing | Frontend components, `lib/auth.ts` (token em memória), CSP headers |
| `SDD_Seguranca_JavaScript` | JavaScript | DOM Injection, Prototype Pollution, DOM Clobbering, CSS Sniffing | Frontend components, CSP headers, shadcn (sanitizado) |
| `SDD_Seguranca_HTTP_e_Sessoes` | HTTP e Sessões | CORS, cookies, HSTS, headers | `main.py` (CORS config, security headers middleware), cookie config |
| `SDD_Seguranca_Infraestrutura` | Infraestrutura | SSH, TLS, WAF, Firewall | Docker config, reverse proxy config (nginx/Caddy), deploy docs |
| `SDD_Seguranca_Deploy_Segredos_e_Logs` | Deploy, Segredos e Logs | Secrets management, logging seguro | `.env.example`, Docker secrets, structured logging sem PII |
| `SDD_Seguranca_CI_e_Threat_Modeling` | CI e Threat Modeling | SAST, SCA, STRIDE | GitHub Actions workflows, `pyproject.toml` (dev deps), threat model doc |

### 9.2 Security headers implementados no middleware

Conforme SDD_HTTP_e_Sessoes e SDD_Frontend:

```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: frame-ancestors 'none'
```

### 9.3 Proteções por camada

**Backend (`core/validacao.py` + `core/middleware.py`):**

- Rate limiting por IP e por usuário (login: 5 tentativas/15min, geral: 100 req/min)
- CSRF tokens em rotas que modificam estado (cookies-based)
- Validação de ownership em todo acesso a recursos (IDOR prevention)
- Sanitização de input contra XSS e injection
- SQL Injection prevention via SQLAlchemy ORM parametrizado
- SSRF prevention: blocklist de IPs privados, validação de URLs
- Command Injection: nunca executar comandos shell com input do usuário
- Desserialização: nunca desserializar dados não confiáveis
- Error handling: retornar mensagens genéricas ao cliente, log detalhado sem PII

**Frontend (Next.js + React):**

- CSP headers para prevenir XSS
- SRI (Subresource Integrity) em scripts externos
- X-Frame-Options: DENY (anti-clickjacking)
- Tokens JWT em memória (nunca em localStorage)
- Sanitização de HTML renderizado via DOMPurify
- Validação de links (`rel="noopener noreferrer"`)
- Nunca renderizar user input sem sanitização

---

## 10. Frontend

### 10.1 Stack

- Next.js 16.x com App Router e `output: "export"` (build estático)
- React 19.x
- TypeScript 5.x
- Tailwind CSS 4.x
- shadcn 3.5.x (componentes)
- Zero runtime state management (React hooks + context)

### 10.2 Rotas (App Router)

| Rota | Tipo | Descrição |
|---|---|---|
| `/` | Pública | Landing page |
| `/login` | Pública | Formulário de login |
| `/cadastro` | Pública | Formulário de cadastro |
| `/recuperar-senha` | Pública | Formulário de recuperação |
| `/dashboard` | Protegida | Visão geral, saldo, ações recentes |
| `/clientes` | Protegida | Lista de clientes |
| `/clientes/[id]` | Protegida | Detalhe/editar cliente |
| `/ferramentas` | Protegida | Lista de ferramentas disponíveis |
| `/ferramentas/[slug]` | Protegida | Interface da ferramenta |
| `/creditos` | Protegida | Saldo, transações, pacotes |
| `/historico` | Protegida | Histórico de execuções |
| `/configuracoes` | Protegida | Perfil, MFA, segurança, exclusão de conta |

### 10.3 Componentes principais

**Layout:**
- `cabecalho.tsx` — Logo, navegação, saldo de créditos, menu do usuário
- `barra-lateral.tsx` — Navegação lateral (ferramentas, clientes, créditos)
- `saldo-creditos.tsx` — Exibição permanente do saldo (badge no header)

**Clientes:**
- `formulario-cliente.tsx` — Criar/editar cliente com config_json
- `card-cliente.tsx` — Card de cliente na listagem

**Ferramentas:**
- `formulario-ferramenta.tsx` — Formulário dinâmico por tipo de ferramenta
- `resultado-ferramenta.tsx` — Exibição do resultado com opção de copiar

**Auth:**
- `formulario-login.tsx` — Login com suporte a MFA
- `formulario-cadastro.tsx` — Cadastro com validação
- `formulario-mfa.tsx` — Step de verificação MFA

### 10.4 API client (`lib/api.ts`)

Client HTTP centralizado com:
- Base URL configurável
- Interceptor para incluir access token no header Authorization
- Interceptor para refresh automático (quando access expira, usa refresh token)
- Tratamento de erros (401 → redirecionar login, 402 → modal de créditos)
- Tipagem completa dos request/response

### 10.5 Hooks principais

- `use-auth.ts` — Contexto de autenticação, login/logout, dados do usuário
- `use-creditos.ts` — Saldo, transações, polling para atualização
- `use-clientes.ts` — CRUD de clientes

### 10.6 UX — Princípios

- Navegação intuitiva para não técnicos
- Feedback imediato (loading states, sucesso, erro)
- Custo em créditos exibido ANTES da execução
- Confirmação antes de ações que debitam créditos
- Seletor de cliente visível quando a ferramenta exige contexto
- Alertas de saldo baixo/zerado permanentes no header
- Histórico acessível mesmo com saldo zerado

---

## 11. Docker e Deploy

### 11.1 Dockerfile (multi-stage)

```dockerfile
FROM node:20 AS build-frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.14-slim AS backend
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install uv && uv sync --no-dev
COPY backend/ .
COPY --from=build-frontend /app/frontend/out ./static
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 11.2 docker-compose.yml

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/seo_saas
      - SECRET_KEY=${SECRET_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - FRONTEND_URL=http://localhost:3000
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: seo_saas
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

### 11.3 Variáveis de ambiente (`.env.example`)

```env
# Banco de dados
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/seo_saas

# Segurança
SECRET_KEY=gerar-uma-chave-secreta-aqui
JWT_SECRET_KEY=gerar-outra-chave-aqui
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=604800
ENCRYPTION_KEY=chave-para-criptografar-segredos-mfa

# LLM
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...

# Aplicação
FRONTEND_URL=http://localhost:3000
AMBIENTE=desenvolvimento
LOG_LEVEL=INFO

# Rate limiting
RATE_LIMIT_LOGIN=5/15min
RATE_LIMIT_GERAL=100/min
```

### 11.4 Configuração do FastAPI (`app/main.py`)

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.middleware import (
    middleware_autenticacao,
    middleware_security_headers,
    middleware_csrf,
)
from app.routers import auth, clientes, ferramentas, creditos, billing, configuracoes

app = FastAPI(title="SEO SaaS IA", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.add_middleware(middleware_security_headers)
app.add_middleware(middleware_csrf)
app.add_middleware(middleware_autenticacao)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(clientes.router, prefix="/api/clientes", tags=["clientes"])
app.include_router(ferramentas.router, prefix="/api/ferramentas", tags=["ferramentas"])
app.include_router(creditos.router, prefix="/api/creditos", tags=["creditos"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(configuracoes.router, prefix="/api/configuracoes", tags=["configuracoes"])

app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

### 11.5 Comandos de desenvolvimento

```bash
# Backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Docker (desenvolvimento)
docker compose up --build

# Migrations
uv run alembic revision --autogenerate -m "descricao"
uv run alembic upgrade head

# Testes
uv run pytest
```

### 11.6 CI/CD (GitHub Actions)

Conforme `SDD_Seguranca_CI_e_Threat_Modeling`:

Pipeline:
1. **Lint** — ruff (Python), eslint (TypeScript)
2. **Type check** — mypy (Python), tsc (TypeScript)
3. **SAST** — bandit (Python), snyk (TypeScript)
4. **SCA** — dependabot / uv audit / npm audit
5. **Testes** — pytest (backend), vitest (frontend)
6. **Build** — Docker image
7. **Deploy** — push para registry + deploy em staging/produção

---

## 12. Fluxos de Usuário

### 12.1 Cadastro

```
Usuário acessa /cadastro
    → Preenche nome, e-mail, senha
    → Frontend valida localmente (força da senha, formato do e-mail)
    → POST /api/auth/cadastro
    → Backend valida (e-mail único, senha forte)
    → Cria usuário (plano free, 50 créditos)
    → Cria conta_creditos (saldo_plano=50)
    → Gera tokens JWT
    → Cria sessão
    → Retorna access token + seta refresh cookie
    → Frontend redireciona para /dashboard
```

### 12.2 Login (sem MFA)

```
Usuário acessa /login
    → Preenche e-mail, senha
    → POST /api/auth/login
    → Backend verifica credenciais (Argon2id verify)
    → Gera access + refresh tokens
    → Cria sessão (ip, user_agent)
    → Retorna access token + seta refresh cookie
    → Frontend redireciona para /dashboard
```

### 12.3 Login (com MFA)

```
Usuário acessa /login
    → Preenche e-mail, senha
    → POST /api/auth/login
    → Backend verifica credenciais → OK
    → MFA ativo? SIM
    → Retorna { mfa_requerido: true, token_temporario: "..." }
    → Frontend exibe formulário MFA
    → Usuário digita código TOTP do app autenticador
    → POST /api/auth/mfa/verificar
    → Backend valida código TOTP
    → Gera access + refresh tokens
    → Cria sessão
    → Retorna access token + seta refresh cookie
    → Frontend redireciona para /dashboard
```

### 12.4 Uso de ferramenta

```
Usuário está no dashboard
    → Clica em uma ferramenta (ex: "Gerar Artigo")
    → Navega para /ferramentas/gerar-artigo
    → Seletor de cliente visível (obrigatório para esta ferramenta)
    → Usuário preenche parâmetros (tópico, palavras-chave, etc.)
    → Frontend exibe: "Esta ação custa 25 créditos. Saldo atual: 350"
    → Usuário clica "Gerar"
    → POST /api/ferramentas/gerar-artigo
    → Backend verifica autenticação
    → Backend verifica saldo (350 >= 25 → OK)
    → Cria execução (status=executando)
    → Executa workflow LangGraph
    → Workflow concluído com sucesso
    → Debita 25 créditos (saldo_plano: 325)
    → Cria transação_credito
    → Atualiza execução (status=concluida, resultado=...)
    → Retorna resultado
    → Frontend exibe resultado + saldo atualizado (325)
```

### 12.5 Saldo esgotado

```
Usuário tenta usar ferramenta
    → POST /api/ferramentas/gerar-artigo
    → Backend verifica saldo (0 < 25)
    → Retorna HTTP 402 { detalhe: "Saldo insuficiente", saldo_total: 0 }
    → Frontend exibe modal: "Seus créditos acabaram!"
    → Modal oferece: "Fazer upgrade de plano" / "Comprar pacote extra"
    → Usuário pode navegar livremente (histórico, dados) mas não executar ações
```

### 12.6 Renovação de ciclo

```
Scheduler verifica ciclo vencido (hoje > ciclo_fim)
    → Busca contas com ciclo vencido
    → Para cada conta:
        → Reseta saldo_plano = plano.creditos_por_mes
        → Atualiza ciclo_inicio = hoje
        → Atualiza ciclo_fim = hoje + 30 dias
        → Cria transacao_credito (tipo=renovacao)
    → Próximo login do usuário: vê saldo renovado
```

### 12.7 Recuperação de senha

```
Usuário acessa /recuperar-senha
    → Informa e-mail
    → POST /api/auth/recuperar-senha
    → Backend gera token UUID
    → Armazena hash SHA-256 do token (expiração 1h)
    → Envia e-mail com link (token no URL)
    → Usuário clica no link
    → Frontend exibe formulário de nova senha
    → Usuário preenche nova senha
    → POST /api/auth/resetar-senha
    → Backend valida token (existe, não usado, não expirado)
    → Valida força da nova senha
    → Hash da nova senha (Argon2id)
    → Atualiza senha do usuário
    → Marca token como usado
    → Revoga todas as sessões
    → Frontend exibe "Senha alterada com sucesso"
    → Redireciona para /login
```
