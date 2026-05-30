# SPEC 06 — Acessibilidade Base

**Status:** a aplicar · **Escopo:** frontend (a11y) · **Severidade:** 🟡 Média · **Esforço:** ~2h
**Índice:** [Auditoria UX 2026-05](README.md)

## 1. Problema

A densidade de acessibilidade é baixa em todo o app: **2** `alt=`, **44** `aria-*`, **16** `role=`. Pontos concretos que afetam leitores de tela e navegação por teclado (e usuários com baixa visão):

- **Botões só-ícone sem rótulo**: remover persona em `formulario-cliente.tsx:240-248` (`&times;`), remover palavra-chave secundária em `formulario-gerar-artigo.tsx:277` (`&times;`), botão de menu mobile da sidebar. Sem `aria-label`, o leitor anuncia "botão" sem dizer o quê.
- **`Label` sem `htmlFor`**: passo 0 do Gerar Artigo (`formulario-gerar-artigo.tsx:200,219`) — labels "Cliente"/"Persona" não associadas aos `<select>`.
- **Status só por cor**: bolinhas de status (ex.: hub `(app)/ferramentas/page.tsx` `bg-success/bg-destructive`, cards) sem texto/`aria-label` equivalente.
- **Imagens sem `alt`**: revisar `preview-artigo.tsx` (imagem do artigo) e ícones decorativos (devem ter `aria-hidden`).
- **Foco em wizards**: ao trocar de passo (Gerar Artigo, CWV form), o foco não vai para o novo conteúdo; navegação por teclado fica perdida.

## 2. Objetivos
Atingir um piso de acessibilidade que beneficia todos (inclusive leigos com leitor de tela ou só teclado), sem reescrever o design.

## 3. Mudanças propostas
- **`aria-label` em todo botão só-ícone**: ex. `aria-label="Remover persona"`, `aria-label="Remover palavra-chave"`, `aria-label="Abrir menu"`. (Botão de remover já existe em `sidebar.tsx` mobile — auditar.)
- **Associar labels**: dar `id` aos `<select>` e `htmlFor` aos `Label` no passo 0 do Gerar Artigo (e onde mais faltar). Se migrar para `ui/select` ([[SPEC_05_Design_System_Consistencia]]), garantir `aria-label`/label associado.
- **Status com texto**: onde houver apenas cor, adicionar texto visível ou `aria-label` ("Concluída", "Falhou"). O histórico já mostra label textual — replicar nos pontos que só têm bolinha.
- **Imagens**: `alt` descritivo na imagem do artigo (`preview-artigo.tsx`); `aria-hidden` em ícones decorativos.
- **Foco em wizard**: ao avançar/voltar passo, mover foco para o container do passo (ex.: `ref` + `focus()` em `useEffect([step])`) nos wizards de `formulario-gerar-artigo.tsx` e `cwv-form.tsx`.
- **Checagem**: rodar Lighthouse/axe nas telas principais como baseline.

## 4. Critérios de aceite
- [ ] Nenhum botão só-ícone sem `aria-label`.
- [ ] Todos os campos de formulário têm label associada (clicar no label foca o campo).
- [ ] Status de execução é perceptível sem depender só de cor.
- [ ] Imagem do artigo tem `alt`; ícones decorativos `aria-hidden`.
- [ ] Lighthouse "Accessibility" ≥ 90 nas telas hub, histórico, Gerar Artigo e dashboard CWV.

## 5. Verificação E2E
Rodar `mcp__chrome-devtools__lighthouse_audit` (categoria accessibility) nas telas principais logado; navegar um wizard só por teclado (Tab/Enter) e confirmar foco visível e ordem lógica.

## 6. Notas
- Manter o visual; a11y aqui é aditiva (atributos + foco), não redesenho.
- Relacionado: [[SPEC_05_Design_System_Consistencia]] (migração de select afeta a11y dos campos).
