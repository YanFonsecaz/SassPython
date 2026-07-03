# SPEC — Inlinks: remover o reranker LLM redundante (cosine ordena, juiz decide)

**Status:** ⚙️ preparada (2026-07-03) — kill-switches `inlinks_reranker_ativo`/`inlinks_revisor_ativo`
implementados com default **True** (comportamento atual preservado). O flip para False em produção e a
remoção definitiva de `reranker.py`/`revisor.py` continuam condicionados ao §Gatilho — **não antecipar**
**Escopo:** backend (`workflow_inlinks.py`, `reranker.py`, `config.py`) + testes/eval
**Crédito:** não muda (remove ~1 chamada LLM por execução — margem melhora)
**Depende de:** [SPEC_Inlinks_Julgamento_Unico](SPEC_Inlinks_Julgamento_Unico.md) aplicada + **dados de produção do funil** (ver §Gatilho)

---

## Contexto

Após o julgamento único, o pipeline do Receber tem **duas chamadas LLM julgando relevância**:
o reranker (`rerank_candidatos`, 1 chamada em lote antes do corte) e o juiz do inseridor
(1 chamada por candidato, que é quem decide). O reranker sobrou da era em que
`score_total = 0.5·cosine + 0.5·ctx` filtrava — hoje ele só **ordena** e produz `score_contexto`,
que nenhuma decisão usa. Custo: 1 chamada gpt-4.1 com o pilar + até 15 candidatas por execução,
mais latência, mais um número na UI (`ctx`) que não corresponde a nada acionável.

O mesmo raciocínio, mais fraco, vale para o **revisor-lint**: desde o re-escopo ele só pega
defeitos objetivos de texto e raramente muda um resultado. Antes de remover, medir.

## Gatilho (não implementar antes disso)

Coletar ~2 semanas de funil em produção e confirmar:
- `n_rejeitados_revisor` ≈ 0 nas execuções (lint não está pegando nada) → remoção segura do revisor;
- a ordenação por `score_total` (com ctx) não diverge da ordenação por `score_semantico` puro no
  corte de `max_inlinks` (comparar nos logs) → remoção segura do reranker.

## Mudanças

### 1. `node_match_rerank` → `node_match` (ordenação por cosine puro)
- Remover a chamada `rerank_candidatos`; manter top-15 por cosine + piso de ruído 0.25.
- `score_total = score_semantico` e `score_contexto = score_semantico` (mesma semântica que o
  Distribuir já usa — `workflow_inlinks_reversos.py` comenta "sem reranker, score_total =
  score_semantico"). Campos preservados no schema/DB para compatibilidade.
- Deletar `app/agents/inlinks/reranker.py` + settings `reranker_llm_model`/`inlinks_reranker_temperature`.
- Nó continua emitindo `match_rerank` no SSE (não quebrar a barra de progresso) OU renomear e
  atualizar `ETAPAS_ORDER_INLINKS`/`NODE_LABELS` juntos — decidir na implementação (preferir renomear).

### 2. Revisor-lint atrás de kill-switch, remoção condicionada a dados
- `config.py`: `inlinks_revisor_ativo: bool = True`; `node_revisar` curto-circuita quando False
  (mesmo padrão do `inlinks_formatador_ativo`).
- Se o gatilho confirmar `n_rejeitados_revisor ≈ 0`, flip para False em produção; remoção
  definitiva do `revisor.py` em release seguinte.

### 3. UI
- `inlinks-resultado.tsx`: ocultar o sufixo "· ctx N" quando `score_contexto === score_semantico`
  (execuções novas), mantendo exibição para execuções antigas.

## Verificação

- `python -m scripts.eval_inlinks --llm real` — gate integral (≥70% deve_aplicar, 0 nao_linkar
  aplicados, 0 alucinações). O golden set é o guarda-corpo desta remoção.
- Unit: ordenação por cosine no node; kill-switch do revisor; ajustar `test_inlinks_funil` se o
  nó for renomeado.
- E2E manual: 1 execução do Receber com 4+ candidatas → mesmos aplicados de antes, ~5-10s mais rápida.

## Riscos

- **Perda de sinal de ordenação em pilares com muitas candidatas parecidas**: o cosine ordena pior
  que o reranker em empates — mas o corte é largo (max_inlinks dinâmico) e o juiz vê cada uma;
  o efeito prático é ordem de avaliação, não inclusão. Golden set cobre.
- **Badge/`ctx` histórico**: execuções antigas mantêm os valores gravados; nada migra.
