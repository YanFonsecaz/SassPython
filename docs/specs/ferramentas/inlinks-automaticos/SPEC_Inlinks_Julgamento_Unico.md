# SPEC — Inlinks: julgamento único pelo LLM (cosine deixa de decidir)

**Status:** ✅ implementado
**Escopo:** backend (`inseridor.py`, `workflow_inlinks.py`, `workflow_inlinks_reversos.py`,
`revisor.py`, `cleaner.py`, `formatador.py`, `config.py`, `schemas/inlinks.py`) + frontend
(`formulario-inlinks.tsx`, `types/ferramenta.ts`)
**Crédito:** não muda (nenhuma função de cobrança é alterada)
**Depende de:** [SPEC_Inlinks_Eval_Golden_Set](SPEC_Inlinks_Eval_Golden_Set.md) (gate de merge)

---

## Contexto

Dados reais do banco (205 sugestões): execução típica do Receber termina com **0–1 aplicado**; 32%
viram `sugestao_manual` numa ferramenta cuja decisão travada é "100% IA, sem aprovação humana". A
inversão-chave: sugestões **rejeitadas** têm score semântico médio **0.74**, maior que as aplicadas
(0.66) — o cosine não prevê o julgamento, mas é a base de ~9 portões em série. As specs anteriores já
tinham medido o problema do sinal (âncora forçada 0.49 > âncora boa 0.44; sinônimo de domínio 0.26) e
responderam adicionando portões compensatórios — que colapsaram o funil.

O julgamento hoje está **fatiado entre 4 juízes** que veem pedaços diferentes: reranker (metadados,
sem âncora), inseridor (parágrafo, mas travado por match lexical — a regra 7 do prompt manda retornar
`{}` se o conceito não está nas keywords do enriquecedor), pisos de cosine (sem semântica) e revisor
(que julga "relação com o destino" vendo **só a URL**). Quando a ferramenta funciona (Mundo Cristão,
8/10 no Distribuir), é porque o bypass de âncora preferida **contornou** os portões: as âncoras
aplicadas mediram cosine 0.39–0.59, todas abaixo do threshold 0.6.

## Decisão de arquitetura

**Um único juiz semântico** — o LLM do inseridor (gpt-4.1, temp 0, structured output) decide
`{aplicar | sugerir | descartar}` com contexto completo e rubrica explícita, uma vez por candidato.
O cosine vira **pré-ranking e sinal registrado** (nunca muda status). Continuam **portões duros**
apenas as validações determinísticas: trecho literal existe no texto (anti-alucinação, inegociável),
não-heading/lista/código, link duplicado, densidade `min_distance` (agora com 1 retry).

## Mudanças

### 1. `inseridor.py` — o juiz

- `PropostaInsercaoSchema` → `DecisaoInsercaoSchema`: `decisao: Literal["aplicar","sugerir","descartar"]`,
  `paragrafo_idx`, `trecho_original` (2–6 palavras literais), `anchor_text`, `conector_antes/depois`,
  `confianca: float`, `motivo: str` (1 frase legível, SEMPRE preenchido).
- Prompt novo (`_build_prompt_focado`): rubrica explícita — *aplicar* exige âncora natural + relação
  direta/complementar, e **sinônimo/termo do mesmo domínio é válido mesmo fora da lista de keywords**
  (ex.: "revenda sem estoque" → destino dropshipping); *sugerir* diz o que o autor deve ajustar;
  *descartar* nunca força link (exemplo real marketplace/CNAE). Blocos ANCORAS PREFERIDAS/REGRA ZERO
  e OBJETIVO preservados. Removidas a regra 7 (keyword obrigatória) e a "REGRA DE DECISÃO" lexical.
- **Portões → sinais**: pisos `_MIN_INSERCAO_SEMANTICA` (0.50) / `_MIN_INSERCAO_SEMANTICA_KW_VALIDA`
  (0.35) / `_MIN_ANCORA_TITULO` (0.35) e a validação lexical `_validar_palavra_chave_destino` +
  `_STOPWORDS_GENERICAS` deixam de mudar status. Cosines continuam calculados e anexados como
  `sinal_cos_contexto`/`sinal_cos_ancora` + `sinal_ancora_contem_termo_destino` (funil/telemetria).
- **Flag de rollback do Distribuir**: `inserir_inlinks(aplicar_pisos_legado=False)`; os pisos ficam
  encapsulados em `_aplicar_portoes_legado()`, acionados só quando
  `settings.inlinks_pisos_legado_distribuir=True` (default False). Upstream do Distribuir
  (filtro cosine alvo↔candidata, slug_only, keyword override) **não muda**.
- **Densidade com retry**: `_aplicar_insercoes` retorna também as colisões de `min_distance`; o
  inseridor re-julga 1 vez com os parágrafos ocupados excluídos ("escolha OUTRO parágrafo ou
  descarte") antes de rebaixar para `sugestao_manual` (11 perdas no banco por rebaixamento direto).
- **Pré-seleção**: `_TOP_N_PARAGRAFOS` 5→8 + união com parágrafos com match lexical de keyword
  (cap 12); índice do prompt vira range dinâmico.
- **CTA fallback sem âncoras preferidas**: com `permitir_cta_fallback=True` e sem âncoras, usa o
  título do destino (≤60 chars) como âncora do "> Leia também:"; gate `cos ≥ 0.55` mantido.
- Mapeamento decisão→status: `aplicar` → portões duros → `aplicado`; `sugerir` → `sugestao_manual`;
  `descartar` → `rejeitado_juiz` (Receber) / `sem_match` (Distribuir), sempre com `motivo`.

### 2. `workflow_inlinks.py` — entrada e paridade

- `node_match_rerank`: o filtro `score_total≥0.6 E score_semantico≥0.40` (+fallback ×0.85) vira
  **piso único de ruído** `score_semantico ≥ 0.25` (o caso legítimo "dropshipping" media 0.26; o piso
  só corta domínio claramente alheio). Reranker continua como ordenação + sinal. `threshold_score`
  permanece na API como parâmetro informativo (sem quebra de contrato).
- `node_inserir` passa `ancoras_preferidas`/`permitir_cta_fallback`/`objetivo_linkagem` do estado
  (paridade com o Distribuir — hoje código morto no Receber). `EstadoInlinks` ganha os 3 campos.
- Volume continua limitado por `max_inlinks` dinâmico. Billing intocado (cobrança usa
  `n_candidatas_validas` de scrape).

### 3. `schemas/inlinks.py` + frontend

- `InlinksRequest` ganha `ancoras_preferidas` (≤10, 2–50 chars), `permitir_cta_fallback` (default
  False) e `objetivo_linkagem` (≤300), validators iguais aos de `inlinks_reversos.py`.
- `formulario-inlinks.tsx`: chips de âncoras + textarea de objetivo + switch CTA, replicados do
  formulário do Distribuir. `types/ferramenta.ts` atualizado.

### 4. `revisor.py` — re-escopo para lint final

- Mantém 1 chamada batch (vê o texto FINAL montado, que o juiz não vê), mas rubrica **só objetiva**:
  quebra gramatical/sentido, texto duplicado/truncado/corrompido. Critérios semânticos saem (eram a
  origem das 11 rejeições "âncora soa artificial" — julgar semântica 2× produz ruído); distância é
  determinística no inseridor. Inclui `titulo_destino` na lista revisada.
- Exceção do LLM → **fail-open** (mantém `aplicado`, loga): juiz + portões duros já garantiram; o
  lint é cosmético.

### 5. Determinismo + limpeza

- `config.py`: `inlinks_cleaner_temperature=0.0`, `inlinks_formatador_temperature=0.0`,
  `inlinks_formatador_ativo=True` (kill-switch), `inlinks_pisos_legado_distribuir=False`.
- `_CleanerAgent`/`_FormatadorAgent` ganham `__init__` com temperatura explícita (hoje herdam 0.7).
- Guard do formatador reforçado: pares `(anchor, url)` em sequência idêntica + diff de tokens do
  texto (sem headings) ≤ ~2%; senão mantém o original.
- Deletar `agents/inlinks/ancorador.py` (100% morto). Remover `_MIN_SEMANTIC_FALLBACK` (inseridor) e
  `_MIN_SEMANTIC_SCORE` do **reversos** (o do `workflow_inlinks.py` é substituído pelo piso 0.25).

## Verificação

- Unit: `test_inlinks_juiz.py` (decisão→status; trecho inexistente → manual; retry de colisão; flag
  legado; CTA com título; motivo nunca vazio), `test_inlinks_paridade.py`,
  `test_inlinks_formatador_guard.py`. Existentes (`test_inlinks_injector.py`,
  `test_inlinks_correcoes.py`) seguem verdes.
- **Gate de merge**: `python -m scripts.eval_inlinks` (golden set) — ≥70% dos `deve_aplicar` →
  `aplicado`; **0** `nao_linkar` → `aplicado`; **0** alucinações; **0** itens sem motivo; Distribuir
  mantém ≥8/10 no caso de referência.

## Riscos

- **Juiz leniente** → casos `nao_linkar` no golden set com tolerância zero; exemplos negativos reais
  no prompt; temp 0.
- **Juiz severo** → recall ≥70% no gate; iterar só o prompt (modo `--llm cache` do harness).
- **Regressão no Distribuir** → `inlinks_pisos_legado_distribuir=True` é rollback de 1 linha.
- **Execuções em voo no deploy** → novas chaves de estado lidas com `estado.get(...)` e default.
