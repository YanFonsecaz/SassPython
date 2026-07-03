# Auditoria de UX 2026-05 — Front-end para usuário não técnico

Auditoria de **todo o front-end** (Next.js, `frontend/src`) com foco no público-alvo do produto: **usuários não técnicos** (gestores/donos de site, redatores). Avaliação feita por leitura das rotas/componentes + navegação logada real (`teste@seosaas.com`, 27 análises CWV).

**Veredito:** o front é visualmente competente e tem exemplos de excelência (ver "Padrão-ouro" abaixo), mas há **becos-sem-saída de navegação, ausência de telas de erro/vazio amigáveis e inconsistências** que confundem quem não é técnico. 8 SPECs agrupam as correções por tema.

> **Cobertura:** SPECs 01–07 = **UX** (fluxo/IA/conteúdo/a11y/consistência de UI). SPEC 08 = **UI visual** (cor/contraste/marca/efeitos/data-viz) — inclui um **bug visual verificado** (utilitários CSS "assinatura" silenciosamente quebrados).

> Escopo desta leva de SPECs: **frontend only** (salvo notas pontuais de backend para humanizar mensagens). Nenhuma muda o comportamento dos agentes/IA.

## Ordem recomendada de aplicação

| Ordem | SPEC | Severidade | Esforço | Por que importa p/ leigo |
|---|---|---|---|---|
| 1 | [01 — App Shell / Navegação](SPEC_01_App_Shell_Navegacao.md) | 🔴 Alta | ~2h | Perfil/MFA tiram a sidebar → usuário fica preso |
| 2 | [02 — Erro / Vazio / Carregamento](SPEC_02_Error_Empty_Loading_Boundaries.md) | 🔴 Alta | ~3h | Crash = tela branca; vazio silencioso parece "quebrado" |
| 3 | [03 — Onboarding / Primeiros passos](SPEC_03_Onboarding_Primeiros_Passos.md) | 🔴 Alta | ~4h | Dead-end de persona trava o Gerar Artigo |
| 4 | [04 — Microcopy / Acentos / Jargão](SPEC_04_Microcopy_Acentos_Jargao.md) | 🟡 Média | ~4h | Acentos faltando + jargão sem explicação |
| 5 | [05 — Consistência do Design-System](SPEC_05_Design_System_Consistencia.md) | 🟡 Média | ~3h | Selects e erros inconsistentes |
| 6 | [06 — Acessibilidade base](SPEC_06_Acessibilidade_Base.md) | 🟡 Média | ~2h | Botões só-ícone sem rótulo, foco em wizard |
| 7 | [07 — Mobile e Descoberta](SPEC_07_Mobile_e_Descoberta.md) | 🟢 Baixa | ~2h | Tabelas largas no celular; registrar descoberta já feita |
| 8 | [08 — UI / Visual](SPEC_08_UI_Visual.md) | 🔴 Alta | ~4h | `glass-card`/glow/dot-pattern quebrados; contraste de CTA < AA; gráficos monocromáticos |

**Total estimado:** ~24h.

> Sugestão de ordem real: aplicar **08 §3.1 (utilitários quebrados)** junto com a leva P0 (01–03), pois é bug objetivo de baixo custo e alto impacto visual.

## Mapa achado → SPEC

| # | Achado | Evidência | SPEC |
|---|---|---|---|
| 1 | Perfil/MFA fora do grupo `(app)` (sem sidebar, sem guard) | `src/app/perfil/page.tsx`, `src/app/configurar-mfa/page.tsx` | 01 |
| 2 | `clientes/novo` sem `PageHeader` | `src/app/(app)/clientes/novo/page.tsx` | 01 |
| 3 | Sem `error.tsx`/`global-error.tsx`/`not-found.tsx`/`loading.tsx` | (ausência em todo `src/app`) | 02 |
| 4 | `catch {}` silenciosos deixam tela vazia | `cwv-historico-client.tsx:77`, hub `ferramentas/page.tsx`, `use-execucao.ts` | 02 |
| 5 | Dead-end de persona (persona obrigatória) | `formulario-gerar-artigo.tsx:77,218-231` | 03 |
| 6 | Form de cliente denso/jargão + erro cru | `formulario-cliente.tsx:93-97,124-201` | 03 |
| 7 | Sem fio condutor de primeiro uso (sem clientes) | hub + forms | 03 |
| 8 | Acentuação ausente disseminada (~20 arquivos) | `execucao-detalhe-conteudo.tsx` (50), `formulario-gerar-artigo.tsx` (18)… | 04 |
| 9 | Jargão sem explicação (LCP/CLS/INP, template, persona…) | CWV, forms | 04 |
| 10 | Mensagens de erro com `detalhe` cru do backend | forms | 04 |
| 11 | `<select>` nativo x `ui/select` (Radix) morto | 4 forms; `ui/select.tsx` nunca importado | 05 |
| 12 | Exibição de erro inconsistente (caixa x `<p>` cru) | auth + cliente | 05 |
| 13 | "Primeira análise" duplicada no CWV | `cwv-metricas-resumo.tsx` + `cwv-dashboard-client.tsx` | 05 |
| 14 | a11y baixa (2 `alt`, botões só-ícone sem rótulo, label sem `htmlFor`) | `formulario-cliente.tsx:240`, `formulario-gerar-artigo.tsx:200,277` | 06 |
| 15 | Tabelas largas / responsividade | `tabela-execucoes.tsx`, tabela de problemas CWV | 07 |
| 16 | Descoberta do CWV/histórico (CWV no hub, rótulos+filtro, entrada histórico, redirect) | **feito nesta sessão — pendente commit** | 07 |
| 17 | `glass-card`/`glow`/`bg-dot-pattern` quebrados (sintaxe `#hex / %` inválida) — **verificado no DOM** | `globals.css:135,138,160,164,168` | 08 |
| 18 | Contraste do CTA primário < WCAG AA (branco sobre #A3968D ≈ 2,9:1) | `globals.css` `.gradient-bg` | 08 |
| 19 | Paleta de gráfico monocromática (chart-1..5 todos taupe) | `globals.css` `--chart-*` | 08 |
| 20 | Classes `dark:*` órfãs (sem dark mode real) | espalhado | 08 |
| 21 | Caixa-alta pervasiva reduz legibilidade | `text-xs uppercase` em vários | 08 |

## Padrão-ouro de UX (referência a replicar)

`src/components/ferramentas/inlinks-seletor-modo.tsx` é o melhor exemplo do app para público leigo:
- Bloco **"O que são inlinks?"** explicando o conceito antes de pedir decisão.
- Dois cards com **"Use quando"**, **exemplo concreto** e **custo** visível.
- Linguagem simples, totalmente acentuada.

As SPECs 03 e 04 pedem para **replicar esse padrão** (explicar antes de exigir) nas demais ferramentas e no onboarding.

## Como validar (após implementação — PR futuro)

Subir backend no host (a stack `make up` não conecta ao DB — ver memória do projeto):
```bash
cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Logar `teste@seosaas.com` / `Teste@12345678` em `http://localhost:8000` e percorrer os fluxos de cada SPEC (Playwright/screenshots).
