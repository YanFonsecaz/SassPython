# SPEC 05 — Consistência do Design-System

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** frontend (componentes/UI) · **Severidade:** 🟡 Média · **Esforço:** ~3h
**Índice:** [Auditoria UX 2026-05](README.md)

## 1. Problema

### 1.1 `<select>` nativo x `ui/select` (componente morto)
Existe `src/components/ui/select.tsx` (wrapper Radix estilizado), mas **nunca é importado** em lugar nenhum. Os formulários usam `<select>` **nativo** estilizado à mão:
- `src/components/ferramentas/formulario-gerar-artigo.tsx` (Cliente, Persona, Tipo de conteúdo)
- `src/components/ferramentas/formulario-inlinks.tsx`
- `src/components/ferramentas/formulario-distribuir-inlinks.tsx`
- `src/components/ferramentas/comparador-versoes.tsx`

Resultado: aparência divergente entre selects, dropdown nativo (pior no mobile/estética) e um componente do design-system sem uso (código morto).

### 1.2 Exibição de erro inconsistente
- Caixa destacada (`bg-destructive/10 border …`) em `cwv-form.tsx`, `formulario-gerar-artigo.tsx`.
- `<p className="text-sm text-destructive">` cru em `formulario-cliente.tsx:93-97`, `formulario-persona.tsx:68-72`, forms de auth.

### 1.3 Outras inconsistências
- `PageHeader` ausente em `clientes/novo` (ver [[SPEC_01_App_Shell_Navegacao]]).
- Mensagem **"primeira análise / registre mais para acompanhar evolução"** aparece **duas vezes** no dashboard CWV: em `cwv-metricas-resumo.tsx` (bloco `!analiseAnterior`) e em `cwv-dashboard-client.tsx` (bloco `!comparacao && historico.length >= 1`). Redundante.

## 2. Objetivos
1. **Uma** forma de fazer select (design-system) ou remover o componente morto.
2. **Uma** forma de exibir erro de formulário.
3. Remover redundâncias visuais.

## 3. Mudanças propostas

### 3.1 Unificar selects
Decisão recomendada: **adotar `ui/select.tsx`** (Radix) nos 4 formulários, para estética consistente e melhor toque no mobile.
- Migrar os `<select>` nativos para `Select/SelectTrigger/SelectContent/SelectItem`.
- Manter `value`/`onChange` equivalentes; revisar acessibilidade (Radix já trás roles).
- **Alternativa de menor esforço:** se a migração Radix for cara, extrair um componente `SelectNativo` único estilizado e usá-lo nos 4 lugares, e **remover** `ui/select.tsx` (não deixar componente morto). Escolher uma das duas — não manter as duas.

### 3.2 Padronizar erro de formulário
- Criar `FormError` (pequeno) ou reutilizar um padrão único: caixa `rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2` com `role="alert"`.
- Aplicar em `formulario-cliente.tsx`, `formulario-persona.tsx`, forms de auth e demais — substituindo os `<p>` crus. (Casa com [[SPEC_04_Microcopy_Acentos_Jargao]] §3.3.)

### 3.3 Remover duplicação "primeira análise"
- Manter a mensagem em **um** lugar (preferência: `cwv-dashboard-client.tsx`, que controla o bloco de comparação) e remover do `cwv-metricas-resumo.tsx` (ou vice-versa), evitando o texto duplicado quando há só 1 análise.

## 4. Critérios de aceite
- [ ] Todos os selects do app usam o mesmo componente; `ui/select.tsx` está **em uso** ou **removido** (sem código morto).
- [ ] Todo erro de formulário usa o mesmo componente/estilo (caixa com `role="alert"`).
- [ ] Dashboard CWV de 1 análise mostra a mensagem "primeira análise" **uma única vez**.
- [ ] `npm run build` e `tsc --noEmit` limpos.

## 5. Verificação E2E
Abrir Gerar Artigo e Inlinks → selects com a mesma cara (screenshot, inclusive mobile). Submeter form de cliente inválido → caixa de erro padrão. Abrir um dashboard CWV com 1 análise → uma só mensagem de "primeira análise".

## 6. Notas
- Migração de select é puramente de UI; cuidar para não quebrar os formulários (testar cada um).
- Relacionado: [[SPEC_01_App_Shell_Navegacao]], [[SPEC_02_Error_Empty_Loading_Boundaries]] (`ErrorState` x `EmptyState` x `FormError` formam a família de estados), [[SPEC_06_Acessibilidade_Base]].
