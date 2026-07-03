# SPEC — Inlinks: UX da verdade (progresso real + motivos visíveis)

**Status:** ✅ implementado
**Escopo:** frontend apenas (4 componentes) — vale para as DUAS ferramentas (Receber + Distribuir)
**Crédito:** não muda
**Depende de:** nada

---

## Contexto

Auditoria de 02/07/2026 (dados reais do banco + leitura do código) mostrou que a UI **esconde** o que
as ferramentas de inlinks fazem:

1. **Barra de progresso morta/errada.** Nenhum workflow de inlinks grava `etapa_atual` (só o decorator
   `workflow_node` do gerar-artigo faz isso) → a linha de % fica em 0 nas duas ferramentas. Pior: para
   `distribuir_inlinks`, `barra-progresso-workflow.tsx:173` não reconhece a ferramenta e usa as etapas
   de **gerar artigo** ("Pesquisar, Redigir..."); e `ETAPAS_ORDER_INLINKS` contém nós fantasma
   `gerar_ancoras`/`injetar` (fósseis do `ancorador.py` morto) que o workflow nunca emite — os nós
   reais são `inserir` e `formatar`.
2. **Soft-fail vira "sucesso" verde.** O backend grava motivos bons em `erro_msg`/`motivo_alvo`
   ("Nenhum link orgânico cabe neste pilar...", "URL alvo não tem conteúdo redacional...") com
   `status="concluida"` (`ferramenta_service.py:366-415`, `workflow_inlinks.py:856-878`), mas a UI só
   mostra `erro_msg` quando `status==="falhou"` e exibe banner verde "concluída com sucesso" + abas
   zeradas. `alvo_invalido`/`motivo_alvo` existem em `types/ferramenta.ts:170-171` e **nunca** são
   renderizados.
3. **Estado vazio inalcançável.** `InlinksResultado` só monta com `inlinks.length > 0`
   (`execucao-detalhe-conteudo.tsx:351-354`) → a mensagem "Nenhum inlink foi aplicado" é código morto.
4. **"Tentar novamente" errado.** O bloco de falha aponta sempre para `/ferramentas/gerar-artigo`
   (`execucao-detalhe-conteudo.tsx:285`), mesmo em execuções de inlinks.

## Mudanças

### 1. `frontend/src/components/ferramentas/barra-progresso-workflow.tsx`

- Reconhecer `distribuir_inlinks`: novo `ETAPAS_ORDER_DISTRIBUIR = ["validar_urls", "extrair_alvo",
  "extrair_candidatas", "enriquecer", "filtrar_similaridade", "inserir_em_cada", "persistir"]`
  (nós de `criar_workflow_distribuir`).
- `ETAPAS_ORDER_INLINKS`: trocar `gerar_ancoras`/`injetar` por `inserir`/`formatar` (nós reais de
  `criar_workflow_inlinks`).
- `NODE_LABELS`: adicionar `inserir`, `formatar`, `extrair_alvo`, `extrair_candidatas`,
  `filtrar_similaridade`, `inserir_em_cada`, `falha_pilar`, `persistir_falha_alvo`.
- **Derivar a etapa ativa do `nodeHistory`** quando `etapaAtual` for null ou não estiver em
  `ETAPAS_ORDER` (o SSE de inlinks emite `node_start`/`node_complete`, mas `etapa_atual` não é
  persistida). O % avança por `max(últimoCompletado+1, índiceDerivado+0.5)`.

### 2. `frontend/src/components/ferramentas/execucao-detalhe-conteudo.tsx`

- `isSoftFail`: `status==="concluida"` E (Distribuir: `alvo_invalido` OU `n_aplicadas+n_sugestoes===0`;
  Receber: `n_aplicadas===0`). Nesse caso, banner **âmbar** ("Execução concluída sem links aplicados")
  com `motivo_alvo || erro_msg`, em vez do banner verde.
- Renderizar a seção "Inlinks aplicados" sempre que Receber+concluída (sem gate `.length > 0`),
  passando `motivoGeral={execucao.erro_msg}`.
- "Tentar novamente" da falha aponta para a rota da ferramenta da execução.

### 3. `frontend/src/components/ferramentas/distribuir-inlinks-resultado.tsx`

- Card âmbar dedicado quando `alvo_invalido` (com `motivo_alvo` + URL alvo), sem tabs zeradas.
- Aba inicial = primeira com `count > 0` (fallback "aplicadas").
- Prop opcional `motivoGeral` exibida quando todas as abas estão zeradas com alvo válido.

### 4. `frontend/src/components/ferramentas/inlinks-resultado.tsx`

- Nova prop `motivoGeral`; estado vazio real (0 itens) exibe motivo; caso "há itens mas 0 aplicados"
  ganha linha destacada "Nenhum aplicado — veja os motivos abaixo".

## Verificação

1. Execução do Distribuir: barra mostra as 7 etapas próprias (não "Pesquisar/Redigir") e % avança.
2. Execução do Receber: 9 etapas reais, sem "Gerar Âncoras/Injetar".
3. Distribuir com alvo inválido → card âmbar com motivo; sem banner verde.
4. Receber com 0 aplicadas → banner âmbar + estado vazio com `erro_msg`.
5. Regressão: execução de gerar-artigo mantém barra intacta.

## Riscos

- Heurística de derivação usa o último evento do `nodeHistory` — não depende do sufixo "..." do
  `isStart`; não alterar mensagens dos nós nesta spec.
- Caminho default (`ETAPAS_ORDER_ARTIGO`) intocado.
