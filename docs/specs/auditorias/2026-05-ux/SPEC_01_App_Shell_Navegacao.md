# SPEC 01 — App Shell / Navegação

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** frontend (roteamento + layout) · **Severidade:** 🔴 Alta · **Esforço:** ~2h
**Índice:** [Auditoria UX 2026-05](README.md)

## 1. Problema

### 1.1 Perfil e Configurar-MFA estão FORA do app-shell
As rotas estão em `src/app/perfil/page.tsx` e `src/app/configurar-mfa/page.tsx` — **fora do grupo `src/app/(app)/`**, que é onde vive o layout autenticado (`(app)/layout.tsx` → `AuthGuard` → `Sidebar`).

Consequências para o usuário leigo:
- A sidebar lista **"Perfil"** (`src/components/layout/sidebar.tsx:38`, item `{ href: "/perfil" }`). Ao clicar, navega para uma página **sem sidebar** — layout centralizado tipo modal (`perfil/page.tsx`: `flex min-h-screen items-center justify-center`). O usuário **perde toda a navegação** e só tem o botão "Sair". Beco-sem-saída clássico.
- Essas rotas **não passam pelo `AuthGuard`** do `(app)`. O `perfil/page.tsx` faz seu próprio `if (!usuario) return <"Carregando...">`, que **nunca redireciona ao login** se não autenticado → fica em "Carregando..." para sempre.
- `configurar-mfa` idem: sem shell, alcançada via botão dentro do Perfil.

### 1.2 `clientes/novo` não usa o `PageHeader` compartilhado
`src/app/(app)/clientes/novo/page.tsx` renderiza `<h1 className="text-2xl font-semibold">Novo Cliente</h1>` cru, enquanto todas as outras telas usam `PageHeader` (`src/components/ui/page-header.tsx`) com título + descrição + ação. Resultado: cabeçalho destoante e **sem botão "Voltar"** (na maioria das telas há).

## 2. Objetivos
1. Perfil e MFA devem viver **dentro do app-shell** (sidebar + AuthGuard), como qualquer outra tela autenticada.
2. Padronizar o cabeçalho de `clientes/novo` com `PageHeader` + ação "Voltar".
3. Garantir que toda rota autenticada tenha caminho de volta visível.

## 3. Mudanças propostas

### 3.1 Mover Perfil e MFA para `(app)`
- Mover `src/app/perfil/` → `src/app/(app)/perfil/` e `src/app/configurar-mfa/` → `src/app/(app)/configurar-mfa/`.
- Remover o wrapper `min-h-screen items-center justify-center` do `perfil/page.tsx` e `configurar-mfa/page.tsx` — agora o conteúdo renderiza dentro do `<main>` do `(app)/layout.tsx`. Trocar o `if (!usuario) return ...Carregando...` por confiar no `AuthGuard` (que já trata loading + redirect ao login).
- Adotar `PageHeader title="Perfil"` no topo, mantendo o card de dados + ações (Alterar senha / Configurar MFA / Dispositivos / Sair).
- **Atenção (Next.js export):** o app usa `output: "export"`. Verificar que as novas rotas continuam gerando estático corretamente (sem `generateStaticParams` extra, pois não são dinâmicas). Confirmar que `main.py` (`serve_spa`) ainda resolve `/perfil` e `/configurar-mfa` — são rotas estáticas simples, o fallback de HTML já cobre.

### 3.2 `clientes/novo` com `PageHeader`
Substituir o `<h1>` por:
```tsx
<PageHeader
  title="Novo cliente"
  description="Cadastre um site/marca para gerar conteúdo e auditar performance"
  action={<Link href="/clientes" className={buttonVariants({ variant: "ghost", size: "sm" })}><ArrowLeftIcon className="size-4 mr-1" /> Voltar</Link>}
/>
```
(reutilizar `PageHeader` de `@/components/ui/page-header` e `buttonVariants` de `@/components/ui/button`, padrão já usado em `cwv-form.tsx` e `inlinks-page-unificada.tsx`).

## 4. Critérios de aceite
- [ ] Clicar em "Perfil" na sidebar mantém a **sidebar visível** e o item "Perfil" fica ativo.
- [ ] Acessar `/perfil` e `/configurar-mfa` **deslogado** redireciona para `/login` (via AuthGuard), sem ficar preso em "Carregando...".
- [ ] `clientes/novo` exibe `PageHeader` com "Voltar" funcional.
- [ ] `npm run build` (export) gera as rotas sem erro; navegação `/perfil` e `/configurar-mfa` resolvem servidas pelo backend.

## 5. Verificação E2E
Logar como `teste@seosaas.com`, clicar "Perfil" → confirmar sidebar presente (screenshot). Abrir aba anônima em `/perfil` → confirmar redirect para `/login`. Abrir `/clientes/novo` → confirmar header + Voltar.

## 6. Notas
- Não alterar a lógica de `FormularioAlterarSenha` / `FormularioListarMfa` / `configurar-mfa` form — só o invólucro de rota/layout.
- Relacionado: [[SPEC_05_Design_System_Consistencia]] (consistência de `PageHeader`).
