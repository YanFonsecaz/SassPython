# SPEC — Distribuir Inlinks: integrar resultado na UI (3 correções bloqueantes)

**Status:** ✅ implementado · **Escopo:** apenas frontend · **Crédito:** não muda · **Depende de:** SPECs backend de Distribuir Inlinks aplicadas
**Contexto:** Smoke test em `localhost:8000/ferramentas/historico/35a27ef7-...` (E2E Mundo Cristão concluído com sucesso no backend) revelou que o componente `DistribuirInlinksResultado` existe mas **nunca é importado/renderizado**. O fluxo após submit redireciona para a página de histórico, que tem branch só para `inlinks_automaticos` — qualquer outra ferramenta cai em `PreviewArtigo` (visualização de artigo único). Resultado: a execução de Distribuir Inlinks aparece como **um artigo** (a primeira candidata aplicada), com aba "Versões (8)" listando as outras como se fossem revisões do mesmo artigo. As 10 candidatas com status (aplicado/sugestão/sem_match/falhou), scores, âncoras e justificativas ficam invisíveis para o usuário.

Para SaaS destinado a não-técnicos, isso é regressão de UX inaceitável: a ferramenta entrega valor no backend mas o valor não chega ao usuário.

## 1. Causas-raiz

### 1.1 Componente órfão

`frontend/src/components/ferramentas/distribuir-inlinks-resultado.tsx` foi criado durante o desenvolvimento da ferramenta mas nenhuma página o importa. `grep -rn "DistribuirInlinksResultado"` retorna apenas a própria declaração.

### 1.2 Branch único em `execucao-detalhe-conteudo.tsx`

`execucao-detalhe-conteudo.tsx:282-301` decide o que renderizar usando ternário binário:

```tsx
{(isAguardando || execucao.status === "concluida") && artigoConteudo && (
  execucao.ferramenta === "inlinks_automaticos" ? (
    <ComparadorPilarInlinks ... />
  ) : (
    <PreviewArtigo ... />
  )
)}
```

`distribuir_inlinks` cai no `else` e vai para `PreviewArtigo`. `artigoConteudo` vem da última versão do `versoes`, que é o markdown de uma das candidatas modificadas (Inseridor grava cada candidata modificada como uma versão do "artigo").

### 1.3 Sem indicador visual de `alvo_modo=slug_only`

O resultado vem com `alvo_modo: "slug_only"` e `titulo_alvo: "Arquivo de Mulheres"` (derivado do slug `/categoria-produto/livros/mulheres`). Sem aviso na UI, o usuário não-técnico vai pensar que o título é literal da página, quando na verdade é uma reconstrução heurística para páginas sem conteúdo redacional. Para a confiança no produto, é importante explicar.

### 1.4 Título duplicado no formulário

`formulario-distribuir-inlinks.tsx:168-173` repete "Distribuir Inlinks" + descrição que **já existem** no `PageHeader` da rota (`distribuir-inlinks/page.tsx:13-15`). Aparece como dois headers empilhados na tela.

## 2. Solução

### 2.1 Wirear `DistribuirInlinksResultado` em `execucao-detalhe-conteudo.tsx`

Transformar o ternário binário (`inlinks_automaticos` vs. todo o resto) em encadeamento de 3 branches, e suprimir a aba "Versões" para `distribuir_inlinks` (cada versão é uma candidata diferente, não há comparação de revisões).

**Antes (linha 282-301):**

```tsx
{(isAguardando || execucao.status === "concluida") && artigoConteudo && (
  execucao.ferramenta === "inlinks_automaticos" ? (
    <ComparadorPilarInlinks ... />
  ) : (
    <PreviewArtigo titulo={artigoTitulo} conteudo={artigoConteudo} ... />
  )
)}
```

**Depois:**

```tsx
{execucao.status === "concluida" && execucao.ferramenta === "distribuir_inlinks" && resultado && (
  <DistribuirInlinksResultado resultado={resultado as unknown as ResultadoDistribuirInlinks} />
)}

{(isAguardando || execucao.status === "concluida") &&
  execucao.ferramenta !== "distribuir_inlinks" &&
  artigoConteudo && (
    execucao.ferramenta === "inlinks_automaticos" ? (
      <ComparadorPilarInlinks ... />
    ) : (
      <PreviewArtigo ... />
    )
  )}
```

Também suprimir o bloco de aba "Versões" para `distribuir_inlinks` (linha 325):

```tsx
{(isAguardando || execucao.status === "concluida") &&
  execucao.ferramenta !== "distribuir_inlinks" &&
  versoes.length > 1 && (
    <Tabs>...</Tabs>
  )}
```

**Imports a adicionar no topo:**

```tsx
import { DistribuirInlinksResultado } from "@/components/ferramentas/distribuir-inlinks-resultado";
import type { ResultadoDistribuirInlinks } from "@/types";
```

#### Mensagem de sucesso

Linha 256-261 ("Artigo concluído com sucesso") — texto específico de artigo. Trocar por mensagem genérica baseada na ferramenta:

```tsx
{execucao.status === "concluida" && (
  <div className="rounded-xl border border-success/30 bg-success/5 px-4 py-3 flex items-center gap-2.5">
    <CircleCheckIcon className="size-5 text-success" />
    <p className="text-sm font-medium text-success">
      {execucao.ferramenta === "distribuir_inlinks"
        ? "Distribuição concluída com sucesso"
        : execucao.ferramenta === "inlinks_automaticos"
          ? "Inlinks aplicados com sucesso"
          : "Artigo concluído com sucesso"}
    </p>
  </div>
)}
```

#### Header da execução

Linha 87 (visto no smoke test) mostra `<heading>distribuir_inlinks</heading>` cru. Procurar onde `execucao.ferramenta` vira título e mapear para label amigável:

```tsx
function labelFerramenta(f: string): string {
  switch (f) {
    case "gerar_artigo": return "Gerar artigo";
    case "inlinks_automaticos": return "Inlinks automáticos";
    case "distribuir_inlinks": return "Distribuir inlinks";
    default: return f;
  }
}
```

Aplicar onde o título da execução é renderizado (verificar `execucao-detalhe-conteudo.tsx` no bloco do header).

### 2.2 Banner `alvo_modo=slug_only` em `DistribuirInlinksResultado`

Adicionar dentro do componente, **acima** do card "URL alvo" (linha 177), um banner condicional:

```tsx
{resultado.alvo_modo === "slug_only" && (
  <div className="rounded-xl border border-warning/30 bg-warning/5 p-3 flex items-start gap-2.5 text-sm">
    <InfoIcon className="size-4 text-warning shrink-0 mt-0.5" />
    <div className="space-y-0.5">
      <p className="font-medium text-warning-dark">Página de categoria/produto sem conteúdo redacional</p>
      <p className="text-xs text-muted-foreground">
        A URL alvo é uma listagem (categoria, produto ou arquivo) e não tem texto suficiente para análise.
        Usamos os termos do slug da URL para identificar o tema e encontrar candidatas relacionadas.
        Resultados nesse modo podem ter scores menores — o sistema relaxa o filtro automaticamente.
      </p>
    </div>
  </div>
)}
```

**Import:** `InfoIcon` do `lucide-react`.

**Justificativa do texto:** Linguagem para não-técnicos. Não usa "embedding", "cosine", "threshold". Explica:
1. O que aconteceu (página sem conteúdo).
2. Como o sistema lidou (usou slug).
3. O que esperar (scores menores são normais nesse modo).

### 2.3 Remover título duplicado em `formulario-distribuir-inlinks.tsx`

Deletar linhas 167-173 (o bloco `<div className="mb-8">` com `<h2>Distribuir Inlinks</h2>` + descrição). O `PageHeader` da rota já entrega esse título. Manter a div externa `<div className="max-w-2xl animate-slide-up">` e o stepper logo abaixo (`<div className="flex items-center gap-0 mb-8">`).

**Antes:**
```tsx
return (
  <div className="max-w-2xl animate-slide-up">
    <div className="mb-8">
      <h2 className="text-xl font-bold">Distribuir Inlinks</h2>
      <p className="text-sm text-muted-foreground mt-1">
        Encontre paginas do seu site para receber links apontando para uma URL especifica
      </p>
    </div>

    <div className="flex items-center gap-0 mb-8">
```

**Depois:**
```tsx
return (
  <div className="max-w-2xl animate-slide-up">
    <div className="flex items-center gap-0 mb-8">
```

## 3. Mudanças por arquivo

| Arquivo | Mudança |
|---|---|
| `frontend/src/components/ferramentas/execucao-detalhe-conteudo.tsx` | Importar `DistribuirInlinksResultado` + `ResultadoDistribuirInlinks`; novo branch para `distribuir_inlinks` antes do ternário existente; suprimir bloco de "Versões" para `distribuir_inlinks`; helper `labelFerramenta` no header; mensagem de sucesso por ferramenta. |
| `frontend/src/components/ferramentas/distribuir-inlinks-resultado.tsx` | Adicionar banner condicional `alvo_modo=slug_only` acima do card URL alvo; importar `InfoIcon`. |
| `frontend/src/components/ferramentas/formulario-distribuir-inlinks.tsx` | Remover bloco `<div className="mb-8">` com h2 + descrição duplicados. |

Nenhuma mudança em backend, types ou rotas.

## 4. Verificação

### 4.1 Visual via Playwright (`localhost:8000`)

1. Login com `teste@seosaas.com` / `Teste@12345678`.
2. Navegar para `/ferramentas/distribuir-inlinks` — confirmar **um único** título "Distribuir Inlinks" (sem duplicação).
3. Navegar para `/ferramentas/historico/35a27ef7-cf48-4ed7-ad0f-4d7b376df150` (execução slug_only existente):
   - Banner amarelo no topo explicando modo slug_only.
   - Card URL alvo com "Arquivo de Mulheres" + URL.
   - 4 abas com contagem: Aplicadas (8) · Sugestões (2) · Sem match (0) · Falhas (0).
   - Acordeão clicável em cada candidata, mostrando âncora + trecho + justificativa.
   - **Sem** preview de artigo único, **sem** aba "Versões".
4. Navegar para `/ferramentas/historico/955baf8d-c0d5-4ca2-8087-5e93ad10f5c3` (execução Hashtag pleno):
   - **Sem** banner slug_only.
   - Dashboard de 4 candidatas.
5. Navegar para uma execução de `gerar_artigo` qualquer no histórico — confirmar que continua renderizando `PreviewArtigo` (sem regressão).
6. Navegar para uma execução de `inlinks_automaticos` — confirmar que continua renderizando `ComparadorPilarInlinks` + `InlinksResultado` (sem regressão).

### 4.2 Build

```bash
cd frontend && npm run build
cp -r out/* ../backend/static/
```

Sem erros TypeScript. Rota `/ferramentas/historico/[id]` continua estática (SSG).

### 4.3 Critério de pronto

- [ ] Página de histórico de execução Distribuir Inlinks mostra dashboard de candidatas com tabs e acordeão (não mostra preview de artigo).
- [ ] Banner slug_only aparece quando `alvo_modo === "slug_only"` e desaparece em `pleno`.
- [ ] Formulário `/ferramentas/distribuir-inlinks` mostra um único título no topo.
- [ ] Execuções de `gerar_artigo` e `inlinks_automaticos` continuam idênticas (sem regressão).
- [ ] Header da execução mostra "Distribuir inlinks" em vez de `distribuir_inlinks` cru.
- [ ] Mensagem de sucesso diz "Distribuição concluída com sucesso" para essa ferramenta.

## 5. Riscos

| Risco | Mitigação |
|---|---|
| `resultado as unknown as ResultadoDistribuirInlinks` força tipo | O backend já serializa nesse shape; tipos já estão alinhados em `types/ferramenta.ts`. Alternativa: tipar `useExecucao` por ferramenta (v2). |
| Banner slug_only pode confundir usuários com cor warning | Texto é informativo (não erro). Cor `warning` é mais leve que `destructive`. Pode ser tunado para `accent` se feedback indicar. |
| Suprimir aba "Versões" remove acesso a histórico de revisões | Para `distribuir_inlinks` não há revisões reais — cada "versão" é uma candidata diferente, melhor representada pelo dashboard. |
| `labelFerramenta` precisa ser atualizada quando novas ferramentas surgirem | Aceitável — fallback retorna o slug cru, então não quebra. |

## 6. Não-objetivos

- Refatorar tipagem de `useExecucao` para discriminated union por ferramenta (v2).
- Polir ícone da ferramenta na lista de histórico (`historico/page.tsx`) — fora do escopo destes 3 fixes.
- Acessibilidade do acordeão (já tem `<button>` com toggle; auditoria a11y é tarefa separada).
- Internacionalização do banner.

## 7. Plano de execução

1. Editar `distribuir-inlinks-resultado.tsx`: importar `InfoIcon`, adicionar bloco do banner condicional.
2. Editar `formulario-distribuir-inlinks.tsx`: remover bloco duplicado `<div className="mb-8">`.
3. Editar `execucao-detalhe-conteudo.tsx`:
   - Adicionar imports de `DistribuirInlinksResultado` e `ResultadoDistribuirInlinks`.
   - Adicionar helper `labelFerramenta`.
   - Aplicar `labelFerramenta` onde `execucao.ferramenta` aparece como título.
   - Trocar mensagem de sucesso por switch por ferramenta.
   - Adicionar branch `distribuir_inlinks` antes do ternário existente.
   - Suprimir bloco "Versões" para `distribuir_inlinks`.
4. `npm run build` no frontend; `cp -r out/* ../backend/static/`.
5. Smoke test via Playwright nas 4 navegações descritas em §4.1.
6. Marcar SPEC como aplicada.
