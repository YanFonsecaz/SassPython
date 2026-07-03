# SPEC — <Título da capacidade ou mudança>

> Copie este arquivo para `ferramentas/<slug>/SPEC_<Tema>.md` (ou `plataforma/<tema>/`) e preencha.
> Apague esta linha e as instruções `<...>`. Mantenha o **header de status** sempre atualizado.

**Status:** 📋 planejado · 🚧 parcial · ✅ implementado · 🗄️ histórico
**Capacidade:** `<gerar-artigo | inlinks-automaticos | inlinks-reversos | core-web-vitals | parecer-tecnico | plataforma/...>`
**Escopo:** `<backend | frontend | ambos>` — `<rotas/arquivos tocados>`
**Código:** `<backend/app/...py, frontend/src/...>`  ·  **Rota:** `<slug do frontend>`
**Créditos:** `<custo ou "não cobra">`  ·  **Commit/Data:** `<hash · AAAA-MM-DD>`
**Depende de:** `<[[OutraSpec]] ou —>`

---

## 1. Contexto (por quê)

<Qual problema ou necessidade motiva isto? O que muda no produto? Em 1–3 parágrafos. Para usuário
não técnico, lembre o público-alvo (ver PRD).>

## 2. Requisitos / Critérios de aceite

<Lista verificável. Cada item é testável (objetivamente "feito" ou "não feito").>

- [ ] Dado `<contexto>`, quando `<ação>`, então `<resultado observável>`.
- [ ] ...

## 3. Design (mapeado ao código)

<Como funciona. Cite **arquivos e símbolos reais** (`app/agents/...py::funcao`). Diagramas/fluxos se
ajudar. Esta seção deve permitir a um agente de IA achar e alterar o código certo.>

## 4. Decisões & alternativas

<Decisões travadas e o porquê. O que foi descartado e por quê. Reuso de infra existente.>

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| | | |

## 5. Verificação

<Como provar que funciona: testes (`backend/tests/...`), E2E local, MCP/browser, comandos.>

```bash
# ex.: pytest backend/tests/... ; rota; passos de E2E
```

## 6. Não-objetivos

<O que esta spec deliberadamente NÃO faz (evita escopo infinito).>

## 7. Histórico

<Mudanças relevantes desde a v1. Ao aplicar uma correção, registre aqui em vez de reescrever o corpo.>

| Data | Mudança | Commit |
|---|---|---|
| | | |
