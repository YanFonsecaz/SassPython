# Especificações (Spec-Driven Development) — SEO SaaS IA

> **Porta de entrada das specs.** Comece por aqui. Este diretório é a **fonte da verdade viva** do
> produto: cada capacidade tem uma pasta com um `README.md` que descreve **o estado atual** (o que
> existe hoje no código) + as specs detalhadas que registram o **design e as decisões**.

Documentos-âncora do produto (leitura de contexto): [`core/PRD.md`](../core/PRD.md) (o quê/por quê) ·
[`core/SDD.md`](../core/SDD.md) (arquitetura) · [`Security/`](../Security/) (segurança) ·
[`observability.md`](../observability.md) · [`operacao/`](../operacao/) · [`deploy.md`](../deploy.md).

---

## Como o SDD funciona neste repositório

Este é um projeto **vibecode** (construído majoritariamente com IA). As specs servem tanto para
humanos quanto para **agentes de IA** que vão ler, manter e estender o código. Por isso:

1. **1 capacidade = 1 pasta.** Toda funcionalidade de produto vive em `ferramentas/<slug>/` e todo
   tema transversal em `plataforma/<tema>/`. O `slug` casa com a rota do frontend.
2. **O `README.md` da pasta é a spec viva.** Ele responde, no presente: *o que é*, *estado atual*,
   *mapa spec→código*, *decisões travadas*, *não-objetivos* e *índice das specs*. É o primeiro arquivo
   a ler/atualizar.
3. **As `SPEC_*.md` são o registro de design.** Detalham requisitos, arquitetura, alternativas e
   verificação. Preservadas como história — não se reescreve o passado, marca-se o **status** no topo.
4. **Histórico fica separado.** PLANOs de correção (`_historico/`) e campanhas de auditoria
   (`auditorias/`) são pontuais e **encerrados**; não confundir com spec viva.
5. **Spec nova segue o [`_template/TEMPLATE_SPEC.md`](_template/TEMPLATE_SPEC.md).** Regras em
   [`_template/CONVENCOES.md`](_template/CONVENCOES.md).

**Vocabulário de status** (no topo de cada spec e nas tabelas abaixo):

| Marca | Significado |
|---|---|
| ✅ implementado | No código e em uso. A spec descreve o que existe. |
| 🚧 parcial | Parte no código; resto é backlog descrito na própria spec. |
| 📋 planejado | Ainda não implementado; spec é proposta. |
| 🗄️ histórico | Pontual e encerrado (correção aplicada, auditoria, postmortem). |

---

## Mapa de capacidades — ferramentas

Cinco ferramentas de IA, todas no padrão **async** (worker ARQ + reserva/confirma/refund de créditos +
SSE de progresso). Custos reais vêm de `backend/app/services/ferramenta_service.py`
(`calcular_custo_*`) — **substituem a tabela fixa antiga do PRD**.

| Capacidade | Estado | Rota frontend | Créditos (modelo real) | Spec viva |
|---|---|---|---|---|
| **Gerar Artigo** | ✅ implementado | `/ferramentas/gerar-artigo` | `15` base `+3`/revisão `+5` imagem | [ferramentas/gerar-artigo](ferramentas/gerar-artigo/README.md) |
| **Inlinks Automáticos** | ✅ implementado | `/ferramentas/inlinks` | `15 + 1·N_urls` (teto 60) | [ferramentas/inlinks-automaticos](ferramentas/inlinks-automaticos/README.md) |
| **Distribuir Inlinks** (reversos) | ✅ implementado | `/ferramentas/distribuir-inlinks` | `15 + 1·N_candidatas` (teto 115) | [ferramentas/inlinks-reversos](ferramentas/inlinks-reversos/README.md) |
| **Core Web Vitals** | ✅ implementado | `/ferramentas/core-web-vitals` | `15 + 1·N_urls` (teto 100; mede mobile+desktop) | [ferramentas/core-web-vitals](ferramentas/core-web-vitals/README.md) |
| **Parecer Técnico** | ✅ implementado | `/ferramentas/parecer` | `10 + 3·N_imagens` (teto 90) | [ferramentas/parecer-tecnico](ferramentas/parecer-tecnico/README.md) |
| **Auditoria de SEO Técnico** | 📋 planejado | `/ferramentas/auditoria-seo-tecnico` | `30` before · `15` after (proposta) | [ferramentas/auditoria-seo-tecnico](ferramentas/auditoria-seo-tecnico/README.md) |

### Mapa capacidade → código (rastreabilidade)

| Capacidade | Workflow / agentes | Router | Modelos | Slug interno |
|---|---|---|---|---|
| Gerar Artigo | `agents/workflow.py`, `pesquisador.py`, `redator.py`, `revisor.py`, `criador_brief.py`, `gerador_imagem.py`, `analisador.py` | `routers/ferramentas.py` | `versao_artigo` | `gerar_artigo` |
| Inlinks Automáticos | `agents/workflow_inlinks.py` + `agents/inlinks/*` (extrator, cleaner, enriquecedor_metadados, reranker, inseridor, ancorador, injector, revisor, formatador) | `routers/ferramentas_inlinks.py` | `inlink_sugerido`, `conteudo_vetor` | `inlinks` |
| Distribuir Inlinks | `agents/workflow_inlinks_reversos.py` (reusa `agents/inlinks/*`) | `routers/ferramentas_inlinks_reversos.py` | reusa `inlink_sugerido`, `conteudo_vetor` | `distribuir_inlinks` |
| Core Web Vitals | `agents/cwv/*` (workflow, analisador, pesquisador, priorizador, documentador) | `routers/ferramentas_cwv.py`, `routers/admin_cwv.py` | `cwv_analise`, `cwv_problema` | `core_web_vitals` |
| Parecer Técnico | `agents/parecer/*` (workflow, analisador, documentador, modelos) | `routers/ferramentas_parecer.py` | `parecer` (migrations `0020`/`0021`) | `parecer_tecnico` |
| Auditoria de SEO Técnico (📋) | `agents/seotec/*` (previsto) + conector local `sf-connector` (Screaming Frog MCP) | `routers/ferramentas_seo_tecnico.py` (previsto) | `seo_auditoria`, `seo_crawl`, `seo_item_resultado` (previstos) | `auditoria_seo_tecnico` |

Serviços de apoio compartilhados: `services/ferramenta_service.py` (lifecycle de execução + custos),
`services/credito_service.py` (reserva/confirma/refund), `core/workflow_events.py` (SSE via Redis
pubsub), `core/llm_guard.py` (retry/semáforo/backoff 429), `agents/checkpointer.py`
(AsyncPostgresSaver). Worker: `app/worker.py`.

---

## Plataforma — capacidades transversais

Não pertencem a uma ferramenta; sustentam todas. Ver [plataforma/](plataforma/README.md).

| Tema | Estado | Onde |
|---|---|---|
| Autenticação, sessões e MFA | ✅ implementado | [plataforma/autenticacao](plataforma/autenticacao/) · `routers/auth*.py`, `services/auth_service.py`, `mfa_service.py` |
| Créditos e billing | ✅ implementado | [plataforma/creditos-e-billing](plataforma/creditos-e-billing/README.md) · `services/credito_service.py`, `billing_service.py` |
| Segurança (12 SDDs) | ✅ referência | [`docs/Security/`](../Security/) |
| Observabilidade (LangSmith, Sentry, `/metrics`, logs) | ✅ implementado | [`docs/observability.md`](../observability.md) |
| Multi-tenant (isolamento por usuário/cliente) | ✅ implementado | `dependencies.py`, `models/cliente.py` + regra em [`core/PRD.md`](../core/PRD.md) |

---

## Auditorias — campanhas pontuais (histórico)

Revisões de qualidade num momento específico. **Encerradas**; o produto já evoluiu além delas. Ver
[auditorias/](auditorias/README.md).

| Campanha | Foco | Estado |
|---|---|---|
| [2026-05-16 — codebase](auditorias/2026-05-16-codebase/README.md) | 48 issues (P0, créditos, multi-tenant, worker, LangGraph, segurança, observabilidade) | 🗄️ aplicada |
| [2026-05 — UX](auditorias/2026-05-ux/README.md) | Front para usuário não técnico (navegação, estados de erro/vazio, onboarding, a11y, UI visual) | 🗄️ aplicada |

---

## Estrutura do diretório

```
docs/specs/
├── README.md                  ← você está aqui (registry mestre)
├── _template/                 TEMPLATE_SPEC.md · CONVENCOES.md
├── ferramentas/
│   ├── gerar-artigo/          README + specs + _historico/
│   ├── inlinks-automaticos/   README + specs + _historico/
│   ├── inlinks-reversos/      README + specs
│   ├── core-web-vitals/       README + specs + POSTMORTEM + _historico/
│   └── parecer-tecnico/       README + specs
├── plataforma/
│   ├── README.md
│   ├── autenticacao/
│   └── creditos-e-billing/
└── auditorias/
    ├── 2026-05-16-codebase/
    └── 2026-05-ux/
```

## Criando ou atualizando uma spec

1. Mudança de comportamento de uma capacidade → atualize **primeiro** o `README.md` da pasta dela
   (estado atual + mapa→código).
2. Feature/refactor não-trivial → crie `SPEC_<Tema>.md` a partir do [template](_template/TEMPLATE_SPEC.md),
   preenchendo o header de status.
3. Correção pontual já aplicada → mantenha a spec, marque `🗄️ histórico` com o hash do commit; PLANOs
   vão para `_historico/` da capacidade.
4. Regras completas: [`_template/CONVENCOES.md`](_template/CONVENCOES.md).
