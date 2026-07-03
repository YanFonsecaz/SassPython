# SPEC 02 — Telas de Erro / Vazio / Carregamento

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** frontend (boundaries + estados) · **Severidade:** 🔴 Alta · **Esforço:** ~3h
**Índice:** [Auditoria UX 2026-05](README.md)

## 1. Problema

### 1.1 Não existe nenhum boundary de erro/carregamento/404
Busca em `src/app/**` confirma: **zero** `error.tsx`, `global-error.tsx`, `not-found.tsx` ou `loading.tsx`. Para um usuário não técnico isso significa:
- Qualquer exceção não tratada em um componente cliente → **tela branca** ou o overlay de erro padrão do Next (em prod, tela em branco). Nenhuma mensagem "algo deu errado, tente novamente".
- Transições de rota que carregam dados não têm fallback de carregamento padronizado (cada página improvisa um skeleton ou nada).
- URL inválida → 404 padrão do Next, sem identidade visual nem link de volta.

### 1.2 Erros de fetch engolidos em silêncio
Vários `catch {}` deixam a tela **vazia sem explicar**, e o leigo conclui que "o app quebrou":
- `src/components/cwv/cwv-historico-client.tsx:71-83` — `catch {}` vazio: se a API falha, a lista fica vazia e cai no empty state "Nenhuma análise ainda" (mensagem **errada** — não é que não há análises, é que a busca falhou).
- `src/hooks/use-execucao.ts` — `listar()` tem `catch { /* silent */ }`; o hub (`(app)/ferramentas/page.tsx`) e o `/ferramentas/historico` mostram vazio em caso de falha de rede.
- `src/components/cwv/cwv-dashboard-client.tsx` — comparação captura erro em `erroComparacao` mas **não exibe** (comentário "Ignorar erros").

## 2. Objetivos
1. Garantir que **todo crash** vira uma tela amigável com "Tentar novamente" e link para o início.
2. Padronizar **carregamento** e **404**.
3. Diferenciar **"vazio de verdade"** de **"falha ao carregar"** (com retry) nos fetches que hoje silenciam.

## 3. Mudanças propostas

### 3.1 Componente reutilizável `ErrorState`
Criar `src/components/ui/error-state.tsx` (espelhando `empty-state.tsx`): ícone (`AlertTriangleIcon`), título, descrição e ação (botão "Tentar novamente"). Reutilizável tanto em boundaries quanto em estados inline de fetch.

### 3.2 Boundaries de rota (Next App Router)
- `src/app/(app)/error.tsx` — `"use client"`, recebe `{ error, reset }`, renderiza `ErrorState` com "Tentar novamente" (`reset()`) e link "Ir para o início" (`/ferramentas`). Cobre todo o app autenticado.
- `src/app/global-error.tsx` — fallback de último recurso (precisa renderizar `<html><body>`).
- `src/app/not-found.tsx` — 404 com identidade visual + link para `/ferramentas` (logado) / `/login`.
- `src/app/(app)/loading.tsx` — skeleton/spinner padrão para transições (reutilizar o spinner do `AuthGuard`).
- **Export estático:** `output: "export"` suporta `error/loading/not-found`. Validar no `npm run build`. Confirmar que `main.py` serve `/404` ou o fallback (o `serve_spa` já retorna `index.html` como fallback — avaliar servir `not-found` corretamente; aceitável manter fallback SPA).

### 3.3 Trocar `catch {}` silenciosos por estado de erro
Padrão sugerido nos hooks/componentes de fetch: além de `dados`/`carregando`, expor `erro: string | null`. Ex. em `cwv-historico-client.tsx`:
- `try/catch` seta `setErro("Não foi possível carregar o histórico.")`.
- Render: se `erro` → `ErrorState` com botão "Tentar novamente" (refaz o `load`); senão se vazio → empty state atual.
- Aplicar o mesmo a `use-execucao.listar` (propagar erro para hub e histórico) e exibir o `erroComparacao` no `cwv-dashboard-client` (inline discreto, não bloqueante).

## 4. Critérios de aceite
- [ ] Forçar exceção em uma página do `(app)` → aparece `ErrorState` com "Tentar novamente", **não** tela branca.
- [ ] Acessar URL inexistente → `not-found.tsx` com link de volta.
- [ ] Com backend desligado, abrir `/ferramentas/core-web-vitals/historico/<id>` → mensagem "Não foi possível carregar… Tentar novamente" (não "Nenhuma análise ainda").
- [ ] `npm run build` (export) sem erros; boundaries presentes no output.

## 5. Verificação E2E
Com backend no ar, navegar normalmente (sem regressões). Depois **desligar o backend** e reabrir histórico CWV/hub → confirmar `ErrorState` + retry (screenshot). Reabrir com backend → "Tentar novamente" recarrega.

## 6. Notas
- Não trocar toasts existentes de ações (aprovar/cancelar) — eles já funcionam; o foco é **carregamento de tela**.
- Relacionado: [[SPEC_04_Microcopy_Acentos_Jargao]] (texto das mensagens), [[SPEC_05_Design_System_Consistencia]] (`ErrorState` entra no design-system ao lado de `EmptyState`).
