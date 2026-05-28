# SPEC — Dashboard Histórico por URL (Core Web Vitals)

**Status:** a aplicar · **Escopo:** UI Next.js (página, componentes, hooks) + 1 nova dep (`recharts` via shadcn chart) · **Backend:** consome endpoints já especificados em [[SPEC_Ferramenta_Core_Web_Vitals]]
**Spec mãe:** [[SPEC_Ferramenta_Core_Web_Vitals]] (define endpoints e modelo de dados)
**Por que separada:** UX do dashboard tem complexidade própria (chart, accordion, comparador, re-análise) que merece detalhamento isolado, sem inflar a spec arquitetural

## 1. Visão geral

Para cada URL analisada, o usuário precisa de uma tela única que permita:

1. **Ver o estado atual** das métricas CWV (score, LCP, CLS, INP)
2. **Acompanhar evolução** ao longo do tempo (chart de linha das últimas N análises)
3. **Entender problemas pendentes** organizados por prioridade (accordion com documentação rica)
4. **Comparar com análise anterior** (diff de métricas + diff de problemas resolvidos/novos)
5. **Disparar nova análise** sem voltar pro formulário

Essa tela é o "destino final" do trabalho do usuário — onde ele volta repetidamente conforme aplica correções.

## 2. Rota e estrutura de arquivo

```
frontend/src/app/(app)/ferramentas/core-web-vitals/
├── page.tsx                                     # formulário inicial (spec mãe §4.1)
├── execucao/[id]/page.tsx                       # polling (spec mãe §4.2)
├── historico/[clienteId]/page.tsx               # lista de URLs (spec mãe §4.3)
└── url/[analiseId]/page.tsx                     # ← ESTA SPEC: dashboard por URL
```

Por que `url/[analiseId]` e não `url/[urlEncoded]`: a partir de uma análise específica conseguimos buscar `cliente_id + url_canonica` e listar todas as análises da mesma URL. Mais robusto que codificar/decodificar URL no path (encoding em URLs vira pesadelo com query strings).

## 3. Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Voltar ao histórico                                                         │
│                                                                                │
│ https://loja.exemplo.com.br/produto/tenis-x                  [Re-analisar →] │
│ Plataforma: VTEX · Template: produto · Estratégia: Mobile                     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  Score atual                                                                   │
│  ┌────────┐  ┌──────┬──────┬──────┬──────┐                                   │
│  │   78   │  │ LCP  │ CLS  │ INP  │ TBT  │                                   │
│  │  / 100 │  │ 2.1s │ 0.05 │ 180  │ 320  │                                   │
│  │  🟡    │  │  🟢  │  🟢  │  🟡  │  🟡  │                                   │
│  └────────┘  └──────┴──────┴──────┴──────┘                                   │
│                                                                                │
│  vs. análise anterior (há 3 dias):  Score +12  LCP -800ms  CLS =  INP -40ms  │
│                                                                                │
├──────────────────────────────────────────────────────────────────────────────┤
│  Evolução                                          Comparar com: [há 3 dias ▾]│
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                                                                          │  │
│  │  100 ┤                                                                   │  │
│  │   80 ┤                              ●─────●           (score)            │  │
│  │   60 ┤              ●─────●                                              │  │
│  │   40 ┤     ●                                                             │  │
│  │   20 ┤                                                                   │  │
│  │    0 ┤                                                                   │  │
│  │       01/05  05/05  10/05  15/05  20/05  25/05                          │  │
│  │                                                                          │  │
│  │  Tabs: [Score] [LCP] [CLS] [INP] [Todas]                                │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
├──────────────────────────────────────────────────────────────────────────────┤
│  Plano de ação · 7 problemas · 2 críticos · ordenado por prioridade           │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ #1 🔴 Imagem do LCP muito grande            [LCP] [crítico]      ▾ │    │
│  ├──────────────────────────────────────────────────────────────────────┤    │
│  │ ## Problema                                                          │    │
│  │ O maior elemento visível na primeira dobra (LCP) está demorando ... │    │
│  │ **Valor medido:** 2.1 s (deveria ser <2.5s)                          │    │
│  │ **Elementos afetados:**                                              │    │
│  │ - `/arquivos/ids/123456/banner-hero.jpg` (2.4 MB)                    │    │
│  │                                                                       │    │
│  │ ## Solução                                                            │    │
│  │ **Para sua plataforma (VTEX):**                                       │    │
│  │ No VTEX IO:                                                           │    │
│  │ 1. Use o componente `<img-vtex>` ...                                  │    │
│  │                                                                       │    │
│  │ **Solução geral:** ...                                                │    │
│  │                                                                       │    │
│  │ 📚 Referências:                                                       │    │
│  │ - web.dev — Optimize LCP                                              │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ #2 🔴 Scripts de terceiros bloqueando      [TBT] [crítico]       ▸ │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ #3 🟡 Imagens sem dimensões declaradas     [CLS]                 ▸ │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│  ...                                                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4. Componentes

### 4.1 Hierarquia

```
DashboardUrlPage  (Server Component, busca dados iniciais)
└── DashboardUrlClient  (Client Component, gerencia estado interativo)
    ├── DashboardHeader  (URL + meta + botão re-analisar)
    ├── MetricasResumo  (score + cards de métrica + delta vs anterior)
    ├── EvolucaoChart  (chart com tabs por métrica + seletor de comparação)
    ├── PlanoAcaoAccordion  (lista expansível de problemas)
    │   └── ProblemaAccordionItem  (1 item com markdown renderizado)
    └── ReanalisarDialog  (confirm + status de polling)
```

### 4.2 `DashboardUrlPage` (Server Component)

`app/(app)/ferramentas/core-web-vitals/url/[analiseId]/page.tsx`

```tsx
import { buscarAnalise, buscarHistoricoUrl } from "@/lib/api/cwv"
import { DashboardUrlClient } from "@/components/cwv/dashboard-url-client"

export default async function Page({ params }: { params: Promise<{ analiseId: string }> }) {
  const { analiseId } = await params
  const analiseAtual = await buscarAnalise(analiseId)
  const historico = await buscarHistoricoUrl({
    clienteId: analiseAtual.cliente_id,
    urlCanonica: analiseAtual.url_canonica,
  })

  return (
    <DashboardUrlClient
      analiseAtual={analiseAtual}
      historico={historico}
    />
  )
}
```

### 4.3 `DashboardHeader`

Props: `url`, `plataforma`, `template`, `estrategia`, `onReanalisar`.

Visual:
- Linha 1: link "← Voltar ao histórico" + breadcrumb
- Linha 2: URL truncada com tooltip mostrando completa + botão `Re-analisar` à direita
- Linha 3: chips com plataforma (badge colorido por plataforma), template, estratégia (mobile/desktop ícone)

Botão `Re-analisar` abre `ReanalisarDialog`.

### 4.4 `MetricasResumo`

Props: `analiseAtual`, `analiseAnterior?`.

Layout: grid de 5 cards:
1. **Score grande**: número 0-100 + cor (verde >=90, amarelo 50-89, vermelho <50)
2. **LCP**: valor em segundos + cor (verde <2.5s, amarelo 2.5-4s, vermelho >4s)
3. **CLS**: valor decimal + cor (verde <0.1, amarelo 0.1-0.25, vermelho >0.25)
4. **INP**: valor em ms + cor (verde <200, amarelo 200-500, vermelho >500)
5. **TBT**: valor em ms + cor (verde <200, amarelo 200-600, vermelho >600)

Abaixo dos cards: linha "vs. análise anterior (há X dias):" com deltas coloridos:
- Score: `+N` verde ou `-N` vermelho
- Latências (LCP/INP/TBT): `-Nms` verde, `+Nms` vermelho (menor é melhor)
- CLS: igual (menor é melhor)
- Mostra `=` quando delta absoluto está dentro de threshold (ex: <5% mudança)

Se não houver análise anterior: linha "Primeira análise — registre mais para acompanhar evolução."

### 4.5 `EvolucaoChart`

Props: `historico: AnaliseResumoResposta[]` (já ordenado desc; reverte pra plotar asc).

Dep nova: `recharts` (via `npx shadcn@latest add chart`).

Implementação:

```tsx
"use client"
import { useState } from "react"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { ChartContainer, ChartTooltip } from "@/components/ui/chart"
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from "recharts"

const METRICAS = [
  { id: "score", label: "Score", campo: "score_performance", unidade: "", cor: "var(--chart-1)" },
  { id: "lcp", label: "LCP", campo: "lcp_ms", unidade: "ms", cor: "var(--chart-2)" },
  { id: "cls", label: "CLS", campo: "cls", unidade: "", cor: "var(--chart-3)" },
  { id: "inp", label: "INP", campo: "inp_ms", unidade: "ms", cor: "var(--chart-4)" },
] as const

export function EvolucaoChart({ historico }: Props) {
  const dados = [...historico].reverse().map(a => ({
    data: new Date(a.criado_em).toLocaleDateString("pt-BR"),
    score_performance: a.score_performance,
    lcp_ms: a.lcp_ms,
    cls: a.cls,
    inp_ms: a.inp_ms,
  }))

  return (
    <Tabs defaultValue="score">
      <TabsList>
        {METRICAS.map(m => <TabsTrigger key={m.id} value={m.id}>{m.label}</TabsTrigger>)}
        <TabsTrigger value="todas">Todas</TabsTrigger>
      </TabsList>
      {METRICAS.map(m => (
        <TabsContent key={m.id} value={m.id}>
          <ChartContainer config={{ [m.campo]: { label: m.label, color: m.cor } }}>
            <LineChart data={dados}>
              <CartesianGrid />
              <XAxis dataKey="data" />
              <YAxis />
              <ChartTooltip />
              <Line dataKey={m.campo} stroke={m.cor} strokeWidth={2} dot />
            </LineChart>
          </ChartContainer>
        </TabsContent>
      ))}
      <TabsContent value="todas">
        {/* 4 linhas no mesmo chart com normalização (0-100 base) */}
      </TabsContent>
    </Tabs>
  )
}
```

Comportamento:
- Tabs alternam métrica visualizada (default: Score)
- Tab "Todas" plota as 4 métricas normalizadas (0-100 escala)
- Tooltip mostra data + valor formatado + delta vs ponto anterior
- Eixo X: data formatada em PT-BR (dd/MM)
- Pontos clicáveis: ao clicar em um ponto, mostra modal/popover com link "Abrir essa análise" (navega pra `url/{analiseId_clicado}`)

### 4.6 `PlanoAcaoAccordion`

Props: `problemas: ProblemaResposta[]` (já ordenado por `prioridade_ordem`).

Implementação usa `Accordion` do shadcn (base-ui via shadcn).

```tsx
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

export function PlanoAcaoAccordion({ problemas }: Props) {
  if (problemas.length === 0) {
    return (
      <div className="rounded-lg border bg-green-50 p-6 text-center">
        <p className="text-green-900 font-medium">🎉 Nenhum problema identificado nessa análise.</p>
        <p className="text-sm text-green-700 mt-1">Continue monitorando re-analisando periodicamente.</p>
      </div>
    )
  }

  return (
    <Accordion type="multiple">
      {problemas.map((p) => (
        <AccordionItem key={p.id} value={p.id}>
          <AccordionTrigger>
            <div className="flex items-center gap-3 text-left">
              <span className="text-sm text-muted-foreground font-mono">#{p.prioridade_ordem}</span>
              <SeveridadeIcon severidade={p.severidade} />
              <span className="font-medium flex-1">{p.titulo}</span>
              <div className="flex gap-1">
                {p.metricas_afetadas.map(m => <Badge key={m} variant="outline">{m}</Badge>)}
                {p.severidade >= 4 && <Badge variant="destructive">crítico</Badge>}
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="prose prose-sm max-w-none dark:prose-invert">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {p.documentacao_md}
              </ReactMarkdown>
            </div>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  )
}

function SeveridadeIcon({ severidade }: { severidade: number }) {
  if (severidade >= 4) return <span aria-label="crítico">🔴</span>
  if (severidade >= 3) return <span aria-label="alto">🟠</span>
  if (severidade >= 2) return <span aria-label="médio">🟡</span>
  return <span aria-label="baixo">🔵</span>
}
```

Comportamento:
- `type="multiple"` — usuário pode abrir vários ao mesmo tempo (útil pra comparar problemas)
- Hover no item de prioridade alta destaca em vermelho suave
- Markdown renderizado com `react-markdown` + `remark-gfm` (já no projeto)
- Tipografia via `prose` do Tailwind Typography (verificar se está habilitado)
- Code blocks dentro do markdown ganham syntax highlighting via `react-markdown` config (se não estiver, V2)

### 4.7 `ReanalisarDialog`

Props: `analiseId`, `onSucesso`.

Comportamento:
1. Click no botão "Re-analisar" abre dialog modal
2. Mostra resumo: "Será criada nova análise para esta URL usando os mesmos parâmetros (template, estratégia). Custo: 5 créditos."
3. Botões: Cancelar / Confirmar
4. Ao confirmar: POST `/api/ferramentas/cwv/reanalisar/{analiseId}`
5. Recebe `execucao_id`, fecha dialog, redireciona pra `/ferramentas/core-web-vitals/execucao/{execucao_id}` (tela de polling padrão)
6. Após polling concluir (já existe), usuário é redirecionado pra dashboard da **nova** análise

Erros:
- Créditos insuficientes → mostra mensagem com link pra `/creditos`
- Cliente sem permissão → mensagem padrão de erro

## 5. Estados da página

### 5.1 Sem histórico (primeira análise)

- `MetricasResumo` mostra os números sem linha de delta
- `EvolucaoChart` mostra 1 ponto único + mensagem "Faça outra análise para começar a ver evolução"
- Demais componentes normais

### 5.2 Com 2-3 análises

- Chart funciona mas com poucos pontos
- Delta vs anterior visível

### 5.3 Com 10+ análises

- Chart pode ficar denso — V1 limita a últimas 30 análises (paginação V2)
- Eixo X com `interval` automático do recharts

### 5.4 Análise com falha PSI

Quando `analiseAtual.status === "falhou_psi"`:
- `MetricasResumo` mostra placeholder "Métricas não disponíveis"
- Mensagem destacada: "Esta análise falhou ao consultar o PageSpeed Insights. Erro: {erro_msg}"
- Botão "Tentar de novo" (= re-analisar)
- Chart e accordion não renderizam (ou renderizam só histórico antigo se existir)

### 5.5 Análise em andamento

Se o usuário acessar `analiseId` que ainda não terminou (race condition raro):
- Detecta via `status === 'em_progresso'`
- Redireciona pra tela de polling automaticamente

## 6. Hooks e API client

### 6.1 `lib/api/cwv.ts`

```ts
import { apiFetch } from "@/lib/api"

export type AnaliseResposta = {
  id: string
  url: string
  url_canonica: string
  template_tipo: string
  plataforma_detectada: string
  estrategia: "mobile" | "desktop"
  score_performance: number | null
  lcp_ms: number | null
  cls: number | null
  inp_ms: number | null
  fcp_ms: number | null
  ttfb_ms: number | null
  tbt_ms: number | null
  status: string
  erro_msg: string | null
  criado_em: string
  problemas: ProblemaResposta[]
  cliente_id: string
}

export type ProblemaResposta = {
  id: string
  kb_codigo: string
  titulo: string
  severidade: number
  prioridade_ordem: number
  metricas_afetadas: string[]
  contexto_especifico: Record<string, unknown>
  documentacao_md: string
}

export type AnaliseResumoResposta = {
  id: string
  url_canonica: string
  template_tipo: string
  score_performance: number | null
  lcp_ms: number | null
  cls: number | null
  inp_ms: number | null
  n_problemas: number
  n_problemas_alta_severidade: number
  criado_em: string
}

export type HistoricoUrlResposta = {
  url_canonica: string
  template_tipo: string
  plataforma_detectada: string
  analises: AnaliseResumoResposta[]
}

export async function buscarAnalise(id: string): Promise<AnaliseResposta> {
  return apiFetch(`/api/ferramentas/cwv/analise/${id}`)
}

export async function buscarHistoricoUrl(params: {
  clienteId: string
  urlCanonica: string
}): Promise<HistoricoUrlResposta> {
  const qs = new URLSearchParams({ cliente_id: params.clienteId, url: params.urlCanonica })
  return apiFetch(`/api/ferramentas/cwv/historico-url?${qs}`)
}

export async function reanalisar(analiseId: string): Promise<{ execucao_id: string }> {
  return apiFetch(`/api/ferramentas/cwv/reanalisar/${analiseId}`, { method: "POST" })
}
```

> Nota: a spec mãe especifica `GET /historico?cliente_id=` retornando lista agrupada por URL. Para o dashboard, precisamos de uma variante focada `GET /historico-url?cliente_id=&url=` retornando só uma URL. Adicionar essa rota na implementação.

### 6.2 `useReanalisar` hook

```ts
"use client"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { reanalisar } from "@/lib/api/cwv"
import { toast } from "sonner"

export function useReanalisar(analiseId: string) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)

  const executar = async () => {
    setLoading(true)
    try {
      const { execucao_id } = await reanalisar(analiseId)
      router.push(`/ferramentas/core-web-vitals/execucao/${execucao_id}`)
    } catch (e) {
      toast.error(extrairMensagemErro(e))
      setLoading(false)
    }
  }

  return { executar, loading }
}
```

## 7. Acessibilidade

- Cards de métrica: cor + ícone + valor (não só cor — daltonismo)
- Accordion: navegável por teclado (shadcn já dá), Enter/Space abre/fecha, setas movem entre itens
- Chart: tabela alternativa acessível via screen reader (`recharts` tem `<table>` modo invisible)
- Markdown renderizado: usa headings semânticos (`h2`, `h3`), não só visuais
- Foco visível em todos os botões e links
- Cor de severidade tem texto/aria-label correspondente

## 8. Mobile

- Layout em grid responsivo (Tailwind `grid-cols-1 md:grid-cols-2 lg:grid-cols-5`)
- Cards de métrica empilham em mobile (1 coluna), score sozinho no topo
- Chart com altura fixa 280px, scroll horizontal se eixo X estourar
- Accordion: largura total, padding ajustado
- Badges de métrica/severidade: ficam em linha separada do título em telas <640px

## 9. Performance

- SSR busca dados iniciais (analise + historico) em paralelo
- `EvolucaoChart` lazy-loaded com `dynamic(() => import(...), { ssr: false })` — recharts é pesado
- Markdown renderizado apenas quando accordion item é aberto (component permanece montado mas markdown só ocupa CPU se visível) — opcional V1, fácil V2
- Cache de histórico no client: revalidação ao re-analisar bem-sucedida invalida e refaz fetch

## 10. Dep nova

```bash
cd frontend
npx shadcn@latest add chart
npx shadcn@latest add accordion
npx shadcn@latest add tabs
npx shadcn@latest add dialog
npx shadcn@latest add badge
```

Isso instala `recharts` como peer + componentes shadcn locais. Tailwind Typography (`@tailwindcss/typography`) precisa estar habilitado pra `prose` funcionar — verificar no boot e adicionar se faltar.

## 11. Testes E2E (Playwright)

`frontend/e2e/cwv-dashboard.spec.ts`:

```ts
test("dashboard renderiza após análise concluída", async ({ page }) => {
  // setup: login + análise mock (ou usar análise real de fixture seed)
  await page.goto(`/ferramentas/core-web-vitals/url/${analiseId}`)

  // header
  await expect(page.getByText("loja.exemplo.com.br")).toBeVisible()
  await expect(page.getByRole("button", { name: /Re-analisar/i })).toBeVisible()

  // métricas
  await expect(page.getByText(/Score atual/i)).toBeVisible()

  // chart
  await expect(page.locator("svg.recharts-surface")).toBeVisible()

  // accordion
  const primeiro = page.getByRole("button").filter({ hasText: "#1" })
  await primeiro.click()
  await expect(page.getByText(/Para sua plataforma/i)).toBeVisible()
})


test("re-analisar redireciona pra polling", async ({ page }) => {
  await page.goto(`/ferramentas/core-web-vitals/url/${analiseId}`)
  await page.getByRole("button", { name: /Re-analisar/i }).click()
  await page.getByRole("button", { name: /Confirmar/i }).click()
  await expect(page).toHaveURL(/\/execucao\//)
})
```

## 12. Plano de execução

### Fase D1 — Setup deps + componentes shadcn (0.5 dia)

1. `npx shadcn@latest add chart accordion tabs dialog badge`
2. Verificar `@tailwindcss/typography` habilitado; se não, adicionar
3. Smoke test: chart simples renderiza com dados fake

### Fase D2 — Hooks + API client (0.5 dia)

1. `lib/api/cwv.ts` com tipos + funções
2. `useReanalisar` hook
3. Backend: adicionar rota `/historico-url` (variante específica para dashboard)

### Fase D3 — Componentes (1.5 dias)

1. `DashboardHeader` + `MetricasResumo` (0.5 dia)
2. `EvolucaoChart` com tabs (0.5 dia)
3. `PlanoAcaoAccordion` com markdown (0.25 dia)
4. `ReanalisarDialog` (0.25 dia)

### Fase D4 — Página + integração (0.5 dia)

1. `url/[analiseId]/page.tsx` server component
2. `DashboardUrlClient` montando tudo
3. Estados vazios/erro
4. Teste E2E em fixture real

### Fase D5 — Polimento (0.5 dia)

1. Mobile responsivo
2. Acessibilidade (focus, aria, contraste)
3. Loading states (skeleton no SSR)

**Esforço total: ~3.5 dias de frontend** (assumindo dev fluente em shadcn/Tailwind).

## 13. Não-objetivos (V1)

- Exportar dashboard como PDF (V2)
- Comparar 3+ análises simultâneas (V2 — V1 só compara com 1 anterior)
- Anotações do usuário ("apliquei correção X em DD/MM") — V2
- Markar problemas como "resolvido manualmente" — V2 (resolução vem da próxima análise)
- Compartilhar dashboard via link público — V2
- Notificação push quando re-análise concluir — V2 (toast suficiente)

## 14. Critério de pronto

- Página `url/[analiseId]` renderiza sem erro para análise concluída
- `MetricasResumo` mostra 5 cards com cores corretas por threshold
- `MetricasResumo` mostra deltas quando há análise anterior, oculta quando primeira
- `EvolucaoChart` plota corretamente com tabs funcionais (Score, LCP, CLS, INP, Todas)
- `PlanoAcaoAccordion` lista todos os problemas, ordem correta, markdown renderiza
- Accordion permite múltiplos itens abertos simultaneamente
- Botão "Re-analisar" abre dialog, cria nova execução, redireciona pra polling
- Estado vazio (sem problemas) mostra mensagem positiva
- Estado de falha PSI mostra mensagem clara e botão tentar novamente
- Mobile: layout não quebra em viewport 360px
- E2E Playwright passa
