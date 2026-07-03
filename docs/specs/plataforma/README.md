# Plataforma — capacidades transversais

Sustentam todas as ferramentas; não pertencem a nenhuma em particular. Spec viva por tema abaixo; o
contrato de produto está em [`core/PRD.md`](../../core/PRD.md) e a arquitetura em
[`core/SDD.md`](../../core/SDD.md).

## Temas

| Tema | Estado | Spec / docs | Código |
|---|---|---|---|
| **Autenticação, sessões e MFA** | ✅ implementado | [autenticacao/SPEC_Login_e_Autenticacao](autenticacao/SPEC_Login_e_Autenticacao.md) | `routers/auth.py`, `auth_mfa_dispositivos.py`; `services/auth_service.py`, `mfa_service.py`; `core/seguranca.py` |
| **Créditos e billing** | ✅ implementado | [creditos-e-billing/README](creditos-e-billing/README.md) | `services/credito_service.py`, `billing_service.py`, `ferramenta_service.py` |
| **Multi-tenant (isolamento)** | ✅ implementado | [`core/PRD.md`](../../core/PRD.md) §regras | `dependencies.py`, `models/cliente.py`, `usuario.py` |
| **Segurança (12 SDDs)** | ✅ referência | [`docs/Security/`](../../Security/) | `core/middleware.py`, `validacao.py`, `seguranca.py`, `rate_limit.py`, `llm_guard.py` |
| **Observabilidade** | ✅ implementado | [`docs/observability.md`](../../observability.md) | `core/logging.py`, `metrics.py`, `observability/*`; `/metrics`, `/health` |

## Autenticação (resumo)

Auth própria (sem Supabase Auth): senha **Argon2id**, **JWT** access (curto) + refresh token em cookie
httpOnly, sessões revogáveis no banco, **MFA TOTP** (segredo criptografado), reset de senha por token de
uso único, política de senha + histórico (`models/historico_senha.py`). Detalhes e as 25 regras
invioláveis: [autenticacao/SPEC_Login_e_Autenticacao.md](autenticacao/SPEC_Login_e_Autenticacao.md) e os
SDDs de [`docs/Security/`](../../Security/).

## Multi-tenant (resumo)

Todo dado é vinculado ao **usuário** que o criou e, quando há contexto, ao **cliente**. Uma ferramenta só
acessa clientes do usuário autenticado. Verificação de ownership (anti-IDOR) em `dependencies.py`. Regra
completa no PRD ("O Que É Proibido").

## Observabilidade (resumo)

Logs JSON estruturados (sem PII/conteúdo), métricas Prometheus em `/metrics`, health em `/health` e
`/health/worker`, tracing opcional LangSmith por run nomeado, Sentry opcional. Guia:
[`docs/observability.md`](../../observability.md).
