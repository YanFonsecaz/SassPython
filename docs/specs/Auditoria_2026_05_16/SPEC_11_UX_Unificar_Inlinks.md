# SPEC 11 — UX: unificar Inlinks Automáticos + Distribuir Inlinks numa rota

**Status:** a aplicar · **Escopo:** apenas frontend Next.js · **Severidade:** Média-Alta (UX/discoverability)
**Cobre:** discoverability quebrada da ferramenta Distribuir, nomes não-comunicativos no sidebar, copy genérica nos cards, cognição confusa para usuário não-técnico, duplicação de form (~80% idêntico).

**Não afeta backend.** Endpoints `/api/ferramentas/inlinks-automaticos` e `/api/ferramentas/distribuir-inlinks` permanecem; frontend passa a chamar ambos a partir da mesma rota.

---

## 1. Objetivo

Transformar duas rotas separadas (`/ferramentas/inlinks` e `/ferramentas/distribuir-inlinks`) em **uma única rota `/ferramentas/inlinks`** com dois modos selecionáveis. Ao acessar, o usuário vê:

1. Hero explicando o conceito de inlinks
2. Dois **cards-modo** lado a lado mostrando claramente a diferença e quando usar cada um
3. Wizard do modo selecionado (o form muda dinamicamente)

URLs antigas redirecionam via 301 para preservar bookmarks.

---

## 2. Arquitetura

### 2.1 Rotas

```
/ferramentas/inlinks                    ← rota unificada (Next.js page)
  ?modo=receber                         ← default (era /ferramentas/inlinks)
  ?modo=distribuir                      ← era /ferramentas/distribuir-inlinks

/ferramentas/inlinks-automaticos        → 301 redirect → /inlinks?modo=receber
/ferramentas/distribuir-inlinks         → 301 redirect → /inlinks?modo=distribuir
```

`modo` é um query param controlado por estado React (`useState` + `useRouter` para sync com URL). Permite deep-link e Back-button funcional.

### 2.2 Estrutura de arquivos (após mudança)

```
frontend/src/app/(app)/ferramentas/
├── page.tsx                            # dashboard (atualizado: stat 3, cards 3)
├── inlinks/
│   └── page.tsx                        # ROTA UNIFICADA (substitui inlinks/ + distribuir-inlinks/)
├── distribuir-inlinks/
│   └── page.tsx                        # mantido como REDIRECT
├── gerar-artigo/page.tsx
└── historico/...

frontend/src/components/ferramentas/
├── inlinks-seletor-modo.tsx            # NOVO: hero + 2 cards de modo
├── inlinks-page-unificada.tsx          # NOVO: orquestra seletor + form via modo
├── formulario-inlinks.tsx              # mantido (modo "receber")
├── formulario-distribuir-inlinks.tsx   # mantido (modo "distribuir")
└── ...
```

### 2.3 Fluxo do componente

```
inlinks-page-unificada.tsx
├─ lê ?modo da URL (default: "receber")
├─ se há modo na URL: render formulário direto
├─ se não há modo: render <InlinksSeletorModo />
│   └─ onSelecionar(modo) → setSearchParams({modo}) → re-render com form
└─ render <FormularioInlinks /> ou <FormularioDistribuirInlinks />
```

---

## 3. Componentes a criar

### 3.1 `inlinks-seletor-modo.tsx`

Cards lado a lado com claridade máxima sobre **direção do fluxo**:

```tsx
"use client";

import { ArrowDownIcon, ArrowUpIcon, CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type ModoInlinks = "receber" | "distribuir";

interface Props {
  modo?: ModoInlinks;
  onSelecionar: (modo: ModoInlinks) => void;
}

export function InlinksSeletorModo({ modo, onSelecionar }: Props) {
  return (
    <div className="space-y-6">
      {/* Hero explicativo */}
      <div className="rounded-2xl border border-brand/20 bg-gradient-to-br from-brand/5 to-transparent p-6">
        <h2 className="font-heading text-lg font-semibold tracking-tight">
          O que são inlinks?
        </h2>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
          Inlinks são links entre páginas do <em>mesmo site</em>. Melhoram SEO
          (Google entende a estrutura), facilitam a navegação e mantêm o leitor
          mais tempo. Escolha a <strong>direção</strong> que quer aplicar:
        </p>
      </div>

      {/* Dois cards-modo */}
      <div className="grid gap-4 sm:grid-cols-2">
        <CardModo
          modo="receber"
          ativo={modo === "receber"}
          onClick={() => onSelecionar("receber")}
          icone={ArrowDownIcon}
          titulo="Receber links"
          subtitulo="1 artigo + N candidatas"
          descricao="Tenho um artigo principal e quero adicionar links de outros artigos do meu blog dentro dele."
          quando="Use quando você acabou de publicar um guia/pilar e quer enriquecer com referências internas."
          exemplo='Ex.: artigo "Guia completo de CNAE" recebe links de artigos relacionados sobre tributação, contratação PJ, etc.'
          custo="15-60 créditos"
        />
        <CardModo
          modo="distribuir"
          ativo={modo === "distribuir"}
          onClick={() => onSelecionar("distribuir")}
          icone={ArrowUpIcon}
          titulo="Distribuir um link"
          subtitulo="1 URL alvo + N candidatas"
          descricao="Tenho uma página e quero que outras páginas do meu site linkem para ela."
          quando="Use quando você lançou uma landing/produto/serviço e precisa que páginas existentes apontem para ela."
          exemplo='Ex.: nova página "/categoria/sapatos-femininos" precisa de tráfego — outras páginas do blog recebem o link.'
          custo="15-115 créditos"
        />
      </div>
    </div>
  );
}

function CardModo({
  ativo, onClick, icone: Icone, titulo, subtitulo,
  descricao, quando, exemplo, custo,
}: {
  modo: ModoInlinks;
  ativo: boolean;
  onClick: () => void;
  icone: React.ElementType;
  titulo: string;
  subtitulo: string;
  descricao: string;
  quando: string;
  exemplo: string;
  custo: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "text-left rounded-2xl border bg-card p-5 transition-all duration-200",
        "hover:border-brand/40 hover:shadow-md",
        ativo ? "border-brand ring-2 ring-brand/20 shadow-md" : "border-border",
      )}
    >
      <div className="flex items-start gap-3">
        <div className={cn(
          "flex items-center justify-center size-10 rounded-xl shrink-0",
          ativo ? "gradient-bg shadow-sm" : "bg-surface-light border border-border",
        )}>
          <Icone className={cn("size-5", ativo ? "text-white" : "text-brand-dark")} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-heading font-semibold text-base">{titulo}</h3>
            {ativo && (
              <span className="inline-flex items-center gap-1 rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand-dark">
                <CheckIcon className="size-3" /> Selecionado
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{subtitulo}</p>
        </div>
      </div>

      <div className="mt-4 space-y-2.5 text-sm">
        <p className="text-foreground">{descricao}</p>
        <div className="rounded-lg bg-surface-light px-3 py-2 border border-border/50">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1">
            Use quando
          </p>
          <p className="text-xs text-foreground/90 leading-relaxed">{quando}</p>
        </div>
        <p className="text-xs text-muted-foreground italic leading-relaxed">{exemplo}</p>
      </div>

      <div className="mt-4 pt-3 border-t border-border/50 flex items-center justify-between">
        <span className="text-xs font-medium text-brand-dark">{custo}</span>
        {!ativo && (
          <span className="text-xs text-muted-foreground">Clique para selecionar →</span>
        )}
      </div>
    </button>
  );
}
```

### 3.2 `inlinks-page-unificada.tsx`

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeftIcon, ChevronLeftIcon } from "lucide-react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { FormularioInlinks } from "@/components/ferramentas/formulario-inlinks";
import { FormularioDistribuirInlinks } from "@/components/ferramentas/formulario-distribuir-inlinks";
import { InlinksSeletorModo, type ModoInlinks } from "@/components/ferramentas/inlinks-seletor-modo";

const MODOS_VALIDOS: ModoInlinks[] = ["receber", "distribuir"];

export function InlinksPageUnificada() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [modo, setModo] = useState<ModoInlinks | null>(null);

  // Lê ?modo da URL
  useEffect(() => {
    const m = searchParams.get("modo") as ModoInlinks | null;
    setModo(m && MODOS_VALIDOS.includes(m) ? m : null);
  }, [searchParams]);

  const trocarModo = useCallback((novoModo: ModoInlinks) => {
    setModo(novoModo);
    const params = new URLSearchParams(searchParams.toString());
    params.set("modo", novoModo);
    router.replace(`/ferramentas/inlinks?${params.toString()}`, { scroll: false });
  }, [router, searchParams]);

  const limparModo = useCallback(() => {
    setModo(null);
    router.replace("/ferramentas/inlinks", { scroll: false });
  }, [router]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inlinks Internos"
        description="Links entre páginas do seu site que melhoram SEO e a leitura"
        action={
          <Link href="/ferramentas" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeftIcon className="size-4 mr-1" />
            Voltar
          </Link>
        }
      />

      {modo === null ? (
        <InlinksSeletorModo onSelecionar={trocarModo} />
      ) : (
        <div className="space-y-4">
          {/* Resumo do modo + botao trocar */}
          <div className="flex items-center justify-between rounded-xl border bg-surface-light p-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex items-center justify-center size-9 rounded-lg gradient-bg shrink-0">
                <span className="text-white text-sm font-bold">
                  {modo === "receber" ? "↓" : "↑"}
                </span>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">
                  {modo === "receber" ? "Receber links" : "Distribuir um link"}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {modo === "receber"
                    ? "Um artigo recebe links de várias páginas"
                    : "Uma URL é linkada em várias páginas"}
                </p>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={limparModo}>
              <ChevronLeftIcon className="size-4 mr-1" />
              Trocar modo
            </Button>
          </div>

          {modo === "receber" ? <FormularioInlinks /> : <FormularioDistribuirInlinks />}
        </div>
      )}
    </div>
  );
}
```

### 3.3 Atualizar `app/(app)/ferramentas/inlinks/page.tsx`

```tsx
import { Suspense } from "react";
import { InlinksPageUnificada } from "@/components/ferramentas/inlinks-page-unificada";

export default function InlinksPage() {
  return (
    <Suspense fallback={null}>
      <InlinksPageUnificada />
    </Suspense>
  );
}
```

(O `Suspense` é necessário porque `useSearchParams` exige boundary no Next 14.)

### 3.4 Substituir `distribuir-inlinks/page.tsx` por redirect

```tsx
// frontend/src/app/(app)/ferramentas/distribuir-inlinks/page.tsx
import { redirect } from "next/navigation";

export default function DistribuirInlinksRedirect() {
  redirect("/ferramentas/inlinks?modo=distribuir");
}
```

Como Next.js gera `out/` estático, esse redirect só funciona em runtime. Para sites estáticos, criar página com `<meta http-equiv="refresh">` + JS:

```tsx
"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DistribuirInlinksRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/ferramentas/inlinks?modo=distribuir");
  }, [router]);
  return (
    <div className="text-center py-12 text-sm text-muted-foreground">
      Redirecionando para a nova rota unificada...
    </div>
  );
}
```

---

## 4. Mudanças em arquivos existentes

### 4.1 Sidebar — remover item "Distribuir Inlinks"

`frontend/src/components/layout/sidebar.tsx:30-39`:

```diff
 const NAV_ITEMS: NavItem[] = [
   { href: "/ferramentas", label: "Dashboard", icon: LayoutDashboardIcon },
   { href: "/ferramentas/gerar-artigo", label: "Gerar Artigo", icon: PenToolIcon },
   { href: "/ferramentas/inlinks", label: "Inlinks", icon: Link2Icon },
-  { href: "/ferramentas/distribuir-inlinks", label: "Distribuir Inlinks", icon: Share2Icon },
   { href: "/ferramentas/historico", label: "Histórico", icon: ClockIcon },
   { href: "/clientes", label: "Clientes", icon: UsersIcon },
   { href: "/creditos", label: "Créditos", icon: CreditCardIcon },
   { href: "/perfil", label: "Perfil", icon: SettingsIcon },
 ];
```

Também remover import `Share2Icon` se não for usado em outro lugar.

### 4.2 Dashboard — manter 3 cards, atualizar copy

`frontend/src/app/(app)/ferramentas/page.tsx:43-60` (StatCard):

```diff
 <StatCard
   label="Ferramentas ativas"
-  value="2"
+  value="2"   // OK depois da unificação: gerar_artigo + inlinks (unificado)
   icon={SparklesIcon}
 />
```

Confirma que `value="2"` está correto pós-unificação (gerar_artigo + inlinks unificado).

`frontend/src/app/(app)/ferramentas/page.tsx:82-99` (card Inlinks):

```diff
 <Link
   href="/ferramentas/inlinks"
   ...
 >
   <div className="flex items-start gap-4">
     <div className="flex items-center justify-center size-12 rounded-xl gradient-bg shadow-md shrink-0">
       <LinkIcon className="size-6 text-white" />
     </div>
     <div className="flex-1 min-w-0">
-      <h3 className="font-heading font-semibold text-base tracking-tight">Inlinks Automáticos</h3>
+      <h3 className="font-heading font-semibold text-base tracking-tight">Inlinks Internos</h3>
       <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
-        Insira links internos automaticamente no seu artigo pilar com IA semântica.
+        Crie links entre páginas do seu site. Receba links em um artigo OU distribua uma URL para várias páginas.
       </p>
-      <p className="text-xs font-medium text-brand-dark mt-3">15–60 créditos</p>
+      <p className="text-xs font-medium text-brand-dark mt-3">15–115 créditos</p>
     </div>
     ...
```

### 4.3 Formulários: remover headers próprios (PageHeader cuida)

`formulario-inlinks.tsx:152-158` — remover o header interno (já está no PageHeader):

```diff
   return (
     <div className="max-w-2xl animate-slide-up">
-      <div className="mb-8">
-        <h2 className="text-xl font-bold">Inlinks Automaticos</h2>
-        <p className="text-sm text-muted-foreground mt-1">
-          Insira links internos automaticamente no seu artigo pilar usando IA
-        </p>
-      </div>
       <div className="flex items-center gap-0 mb-8">
```

`formulario-distribuir-inlinks.tsx` — verificar se tem header próprio similar e remover.

### 4.4 Status labels mais amigáveis em `distribuir-inlinks-resultado.tsx`

Mapa de status para texto user-friendly:

```diff
 const statusConfig: Record<string, { icon: React.ElementType; label: string; classe: string }> = {
-  aplicado: { icon: CheckCircleIcon, label: "Aplicado", classe: "text-success" },
-  sugestao_manual: { icon: AlertTriangleIcon, label: "Sugestao manual", classe: "text-warning" },
-  sem_match: { icon: XCircleIcon, label: "Sem match", classe: "text-muted-foreground" },
-  falhou_extracao: { icon: XCircleIcon, label: "Falhou", classe: "text-destructive" },
+  aplicado: { icon: CheckCircleIcon, label: "Aplicado", classe: "text-success" },
+  sugestao_manual: { icon: AlertTriangleIcon, label: "Revisar antes de aplicar", classe: "text-warning" },
+  sem_match: { icon: XCircleIcon, label: "Sem relação suficiente", classe: "text-muted-foreground" },
+  falhou_extracao: { icon: XCircleIcon, label: "Erro ao ler URL", classe: "text-destructive" },
 };
```

### 4.5 Tooltips em configs avançadas

Em `formulario-inlinks.tsx:350-400` (configs "Teto de inlinks", "Score mínimo", "Rel attribute") e equivalente em distribuir-inlinks:

```tsx
import { InfoIcon } from "lucide-react";

<div className="space-y-2">
  <div className="flex items-center gap-1.5">
    <Label htmlFor="threshold" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
      Score mínimo
    </Label>
    <span title="Quanto mais alto, mais rigoroso. Valores entre 0.5 e 0.7 funcionam para a maioria. Abaixo de 0.4 = links pouco relacionados.">
      <InfoIcon className="size-3 text-muted-foreground/60" />
    </span>
  </div>
  <Input ... />
</div>
```

Mesma ideia para `"Teto de inlinks"` e `"Rel attribute"`.

---

## 5. Plano de execução

### Fase 1 — Componentes novos (30 min)

1. Criar `inlinks-seletor-modo.tsx`
2. Criar `inlinks-page-unificada.tsx`
3. Atualizar `app/(app)/ferramentas/inlinks/page.tsx` para usar `InlinksPageUnificada`

### Fase 2 — Redirects (10 min)

4. Substituir `app/(app)/ferramentas/distribuir-inlinks/page.tsx` por redirect client-side
5. Verificar se há outras referências hardcoded a `/distribuir-inlinks` no codebase frontend
   ```bash
   grep -rn "distribuir-inlinks" frontend/src
   ```

### Fase 3 — Limpeza UX (20 min)

6. Sidebar: remover item "Distribuir Inlinks"
7. Dashboard: ajustar copy + URL do card Inlinks
8. Formulários: remover headers próprios (PageHeader cuida)
9. Status labels: distribuir-inlinks-resultado.tsx
10. Tooltips em configs avançadas (Score, Teto, Rel)

### Fase 4 — Validação (10 min)

11. `npm run build` — sem erros
12. `cp -r out/* ../backend/static/`
13. Smoke test via Playwright:
    - Acessar `/ferramentas/inlinks` → ver seletor de modo
    - Clicar "Receber links" → ver form com URL `?modo=receber`
    - Voltar com "Trocar modo" → ver seletor de novo
    - Acessar `/ferramentas/distribuir-inlinks` direto → redirecionar para `?modo=distribuir`
    - Bookmark de URL antiga ainda funciona
    - Dashboard mostra 3 cards corretos

**Total: ~70 min**

---

## 6. Verificação (E2E)

### Cenário 1: Usuário novo descobre a ferramenta

1. Acessa `/ferramentas` (dashboard).
2. Vê 3 cards: Gerar Artigo, Inlinks Internos, Histórico.
3. Clica em "Inlinks Internos".
4. Vê hero + 2 cards de modo lado a lado, com descrição clara.
5. Lê os exemplos, decide qual usar, clica no card.
6. Form aparece com wizard step 1.
7. URL ficou `/ferramentas/inlinks?modo=receber` (ou `?modo=distribuir`).

### Cenário 2: Usuário antigo com bookmark de `/distribuir-inlinks`

1. Acessa `/ferramentas/distribuir-inlinks`.
2. Página de loading aparece brevemente ("Redirecionando...").
3. URL muda para `/ferramentas/inlinks?modo=distribuir`.
4. Form do modo distribuir aparece.

### Cenário 3: Usuário muda de ideia no meio

1. Está em `/ferramentas/inlinks?modo=receber`, wizard step 0.
2. Clica em "Trocar modo".
3. Volta para seletor.
4. Escolhe "Distribuir um link".
5. Form do modo distribuir abre.

### Cenário 4: Estado preservado por sessão (opcional)

`localStorage["inlinks-ultimo-modo"]`: ao acessar `/ferramentas/inlinks` sem `?modo`, pré-seleciona o último modo usado.

**Não fazer agora** — pode confundir usuários que querem ver o seletor toda vez. Avaliar depois de 1-2 semanas.

---

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Redirects estáticos podem não funcionar em alguns hosts | Implementar redirect client-side com `<meta refresh>` como fallback |
| `useSearchParams` exige Suspense em Next 14 | Wrap em `<Suspense fallback={null}>` na page.tsx |
| Bookmarks externos quebram | 301 redirect preserva SEO + funcionalidade |
| Usuários antigos confusos com nova UI | A unificação clarifica, não complica. Se feedback negativo, podemos adicionar um banner "Renovamos: agora os dois modos ficam juntos" por 30 dias |
| Build estático Next.js perde query params | Query params são parseados no client (`useSearchParams`); ok para SPA |
| `formulario-inlinks` e `formulario-distribuir-inlinks` têm headers internos duplicados | Remover (PageHeader externo cuida) |

---

## 8. Não-objetivos

- **Mesclar os formulários num componente único** — eles têm fluxos diferentes (URL alvo vs URL pilar; rel_attr vs threshold). Manter separados, só compartilhar o invólucro.
- **Renomear backend endpoints** — fica como está (`/inlinks-automaticos` e `/distribuir-inlinks`). Frontend usa o endpoint certo baseado no modo.
- **Renomear sidebar para "Inlinks Internos"** — manter "Inlinks" (mais curto, escaneável).
- **Pré-seleção via localStorage** — analisar depois.
- **Refatorar para LCEL/Pydantic structured outputs** — backend não muda nesta SPEC.

---

## 9. Critério de pronto

- [ ] Rota `/ferramentas/inlinks` mostra seletor de modo quando sem `?modo`
- [ ] Clicar num card-modo navega para `?modo=<modo>` e mostra form
- [ ] Botão "Trocar modo" volta para o seletor
- [ ] `/ferramentas/distribuir-inlinks` redireciona para `/ferramentas/inlinks?modo=distribuir`
- [ ] Sidebar tem só "Inlinks" (sem "Distribuir Inlinks" separado)
- [ ] Dashboard mostra card "Inlinks Internos" com nova copy
- [ ] Tooltips presentes nas configs avançadas (Score, Teto, Rel)
- [ ] Status labels amigáveis em `distribuir-inlinks-resultado`
- [ ] `npm run build` passa sem erro
- [ ] Smoke test E2E (4 cenários acima) passa
- [ ] Nenhum link hardcoded para `/distribuir-inlinks` que não seja a página de redirect

---

## 10. Métrica de sucesso (acompanhar pós-deploy)

- **Discovery**: % de usuários que clicam em "Distribuir Inlinks" subir de ~ø para 10-20% das execuções de inlinks (estimativa).
- **Tempo até primeira execução**: reduzir 30-50% (hipótese: hero explicativo elimina dúvida inicial).
- **Taxa de abandono no wizard step 0**: estável ou cair (hero + seleção de modo torna intenção mais clara).

Se possível, adicionar evento analytics:
- `inlinks.modo_selecionado`: `{modo: "receber" | "distribuir"}`
- `inlinks.trocar_modo`: contagem de cliques em "Trocar modo"

Útil para futura decisão de simplificar (se 95% escolhem 1 modo, talvez voltar a ter 2 rotas).
