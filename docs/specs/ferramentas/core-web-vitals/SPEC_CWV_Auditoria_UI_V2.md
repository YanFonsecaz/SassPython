# SPEC — Auditoria UI V2: donuts de health, checklist estilo Excel e before/after por URL

**Status:** 📋 planejado
**Capacidade:** `core-web-vitals`
**Escopo:** `frontend` — página `auditoria/[auditoriaId]`
**Código:** `frontend/src/components/cwv/auditoria/*` (novos), `frontend/src/components/cwv/cwv-auditoria-client.tsx` (vira orquestrador), `frontend/src/lib/api/cwv.ts`
**Rota:** `ferramentas/core-web-vitals/auditoria/[auditoriaId]`
**Créditos:** não cobra
**Depende de:** [[SPEC_CWV_Auditoria_Comparativo_API]] · [[SPEC_CWV_Auditoria_Ciclo_De_Vida]] (S5)
**Commit/Data:** — · 2026-07-15

---

## 1. Contexto (por quê)

A página da auditoria hoje (`cwv-auditoria-client.tsx`, 19.7K — grande demais, sinal de
responsabilidades misturadas) mostra o checklist em cards agrupados por origem e o health score
**só como número**. O público-alvo é não técnico (PRD) e vem da planilha NPBR — espera:

1. **Gráfico de health score** — a capa da planilha tem 2 pizzas Pass/Fail (antes/depois).
2. **Tabela estilo Excel** — a aba Checklist da planilha: linhas por item, colunas
   Before/After/Implementação/Prioridade, edição direta na célula.
3. **Before/after por URL** — evolução visível das métricas de cada página após implementar.

Decisões do brainstorming (2026-07-15): editável = implementação + notas + **prioridade**
(Pass/Fail nunca — vem da análise); gráfico = donuts before/after **+ evolução**; before/after =
métricas **+ problemas**; layout = **abas numa página**.

## 2. Requisitos / Critérios de aceite

- [ ] Dada auditoria carregada, então header fixo mostra título, badge de fase, 2 donuts
      compactos (before/after) com % central e delta em p.p. quando ambos existem.
- [ ] Dada a aba Visão Geral, então donuts grandes Pass/Fail (contadores visíveis), gráfico de
      linha da evolução do health entre auditorias do cliente e top-5 consolidados (causa raiz +
      esforço + link para a aba Checklist).
- [ ] Dada a aba Checklist, então tabela com grupos por origem colapsáveis (PSI/CrUX/Page
      Experience), colunas Item · Before · After · Implementação · Métricas · Prio · Esforço ·
      Notas; filtros Todos/Reprovados/Aprovados/Implementados e busca por texto; ordenação por
      clique no header.
- [ ] Dado clique no dropdown de Implementação, então PATCH otimista com rollback + toast em erro
      (padrão existente `handleAtualizarItem`).
- [ ] Dado edição de Prio (input numérico) ou Notas (popover nota cliente + nota SEO), então
      salvas via `atualizarItemChecklistCwv`; valor inválido (<0) bloqueado no input.
- [ ] Dada a aba Before/After em fase `after`, então 1 card por URL×estratégia com tabela
      Score/LCP/CLS/INP/TBT (before, after, Δ com seta verde=melhora/vermelha=piora) e chips
      resolvidos/persistentes/novos expandíveis (títulos).
- [ ] Dada fase `before`, então aba Before/After mostra baseline + empty state "aguardando
      re-auditoria" (CTA de re-auditar se fase permitir); donut after do header fica vazio com hint.
- [ ] Dada troca de aba, então `?tab=` na URL (deep-link) — voltar do navegador preserva a aba.
- [ ] Dado item com status `na`, então badge cinza "n/a" (nunca conta como reprovado no filtro).

## 3. Design (mapeado ao código)

### 3.1 Componentes (novos em `frontend/src/components/cwv/auditoria/`)

| Arquivo | Responsabilidade |
|---|---|
| `auditoria-header.tsx` | título/fase/donuts compactos/Δ + ações existentes (re-auditar, consolidar, relatório, DOCX) movidas do client atual |
| `auditoria-tabs.tsx` | shadcn `Tabs`; aba ativa sincronizada com `?tab=` via `useSearchParams`/`router.replace` |
| `visao-geral-tab.tsx` | composição: 2× `health-donut` + `health-evolucao-chart` + top-5 consolidados (`buscarConsolidadosCwv`) |
| `checklist-grid.tsx` | tabela Excel: estado de filtro/busca/sort/grupos local; recebe `checklist` + callback de PATCH |
| `before-after-tab.tsx` | consome `buscarComparativoAuditoria` (client novo em `lib/api/cwv.ts`); cards por par |
| `health-donut.tsx` | recharts `PieChart` dentro de `ChartContainer` (padrão de `cwv-evolucao-chart.tsx:5-7`); props `{pass, fail, label, size}`; % central via `<text>` |
| `health-evolucao-chart.tsx` | `LineChart` com pontos = auditorias do cliente (`listarAuditoriasCwv` — `AuditoriaResumo` já tem `health_score_before/after` + `criado_em`; **zero backend novo**) |

`cwv-auditoria-client.tsx` mantém: fetch da auditoria, polling de consolidação/relatório, estado
global e handlers de PATCH — passa dados para as abas. Meta: cada arquivo novo < 300 linhas.

### 3.2 Tabela Excel (`checklist-grid.tsx`)

- `<table>` Tailwind: `sticky top-0` no thead, zebra, linha tingida suave pelo `status_before`
  (verde/vermelho/cinza a 5-8% de opacidade — legibilidade primeiro).
- Grupo por `origem` = `<tr>` de seção com contadores (`✔ n · ✖ n`) e chevron de colapso
  (estado local `Record<string, boolean>`).
- Células editáveis: Implementação = `Select` shadcn inline; Prio = `<input type="number" min=0>`
  com débito no blur; Notas = `Popover` com 2 `Textarea` (cliente/SEO) + botão salvar; ícone 📝
  com contador de notas preenchidas.
- Sort/filtro/busca client-side (≤ ~60 linhas, sem virtualização, sem lib de grid).
- Badges Before/After somente leitura: ✔ pass verde, ✖ fail vermelho, n/a cinza.

### 3.3 API client (`lib/api/cwv.ts`)

- Novo: `buscarComparativoAuditoria(auditoriaId): Promise<ComparativoResposta>` + tipos.
- `atualizarItemChecklistCwv`: tipo do payload ganha `prioridade?: number`.

### 3.4 Avisos ao implementador

1. `output: "export"` — `usePathname()`/`useSearchParams()`, **nunca** `useParams()`;
   `generateStaticParams` placeholder já existe na rota.
2. `?tab=` via `router.replace` (não `push`) para não poluir histórico a cada troca.
3. Não reimplementar diff de problemas no front — vem pronto do endpoint comparativo.
4. Estados da auditoria: reaproveitar guards existentes do client (fase, `health_score_after ==
   null` em fase after = execução ainda rodando → skeleton/polling).
5. Charts: seguir `ChartContainer` + `ChartTooltipContent` de `cwv-evolucao-chart.tsx` (tema/cores
   da casa); cores pass/fail das mesmas usadas nos badges do checklist.
6. Testes em `frontend/src/components/cwv/__tests__/` (padrão dos existentes).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Grid | Tabela própria HTML+Tailwind | TanStack Table — dep nova e overkill para ≤60 linhas (decisão do brainstorming, opção B) |
| Gráficos | recharts (já no projeto, `package.json:31`) | Lib nova de gauge — desnecessária, donut recharts resolve |
| Layout | 3 abas numa página com `?tab=` | Página única rolável (scroll infinito confunde leigo) e rotas separadas (mais navegação) |
| Pass/Fail | Somente leitura | Override manual — divergiria da análise real e exigiria recálculo de health (descartado no brainstorming) |
| Evolução | Por auditoria do cliente (dados existentes) | Por execução — exigiria endpoint novo de listagem com health; auditoria é a unidade que o cliente acompanha |
| Edição | Otimista + rollback | Modal de confirmação por célula — fricção alta, anti-Excel |

## 5. Verificação

```bash
cd frontend && pnpm test -- --run src/components/cwv/__tests__/
cd frontend && pnpm build   # output export tem que passar
```

- Testes: render do grid (grupos, contadores), filtro Reprovados, edição de dropdown dispara
  PATCH otimista e faz rollback em erro mockado, donut renderiza % correto, aba via `?tab=`.
- E2E manual (dev): auditoria real → editar implementação/prio/notas → recarregar página →
  valores persistidos; fase before → empty states corretos.

## 6. Não-objetivos

- Virtualização/paginação da tabela (≤ ~60 itens).
- Export CSV/Sheets da tabela (roadmap V3 — layout NPBR no Google Sheets).
- Drag-and-drop de prioridade.
- Mudanças nas páginas de execução/análise/histórico existentes.
- Editar Pass/Fail ou health score manualmente.

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-15 | Spec criada (brainstorming: donuts+evolução, tabela Excel editável impl/notas/prio, before/after métricas+problemas, layout em abas) | — |
