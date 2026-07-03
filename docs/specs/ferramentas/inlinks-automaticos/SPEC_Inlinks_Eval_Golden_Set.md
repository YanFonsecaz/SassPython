# SPEC — Inlinks: harness de avaliação com golden set

**Status:** ✅ implementado
**Escopo:** backend (`scripts/eval_inlinks.py` + `tests/eval/`) — nada de produção
**Crédito:** não muda
**Depende de:** nada (deve rodar ANTES da SPEC_Inlinks_Julgamento_Unico para gerar o baseline)

---

## Contexto

~30 specs de inlinks ajustaram thresholds e prompts **sem métrica** — cada correção movia o problema
de lugar. Este harness fecha o ciclo: um golden set pequeno e rotulado, executável offline, que mede
precisão/recall do funil e vira **gate de merge** para qualquer mudança de prompt/portão.

## Mudanças

### 1. Fixtures — `backend/tests/eval/fixtures/inlinks_golden/*.json`

~10 casos rotulados, com conteúdo (markdown) gravado nos próprios JSONs (sem rede):

```json
{
  "nome": "cnae_agilize",
  "ferramenta": "receber",
  "pilar": {"url": "...", "titulo": "...", "conteudo_md": "..."},
  "candidatas": [{"url": "...", "titulo": "...", "conteudo_md": "..."}],
  "params": {"ancoras_preferidas": [], "objetivo_linkagem": null},
  "rotulos": {"url": "deve_aplicar" | "aceitavel_sugestao" | "nao_linkar"}
}
```

Casos derivados de execuções reais documentadas nas specs:
- pilar CNAE varejista + 4 candidatas Agilize (`d7b50a52`): cnae-prestacao=deve_aplicar,
  contratacao-pj=nao_linkar, contabilidade-MEI=aceitavel_sugestao, marketplace=nao_linkar;
- dropshipping → loja-virtual (deve_aplicar; cosine real 0.26 — testa sinônimo de domínio);
- "tipo de negócio" → imobiliária (nao_linkar; cosine real 0.49 — testa anti-forçagem);
- Mundo Cristão com `ancoras_preferidas` (Distribuir);
- Distribuir slug_only (alvo de categoria).

### 2. Runner — `backend/scripts/eval_inlinks.py`

- CLI: `python -m scripts.eval_inlinks [--caso NOME] [--llm real|cache]`.
- Compõe as funções públicas do pipeline **sem DB nem scraper**: `enriquecer_metadados`,
  `rerank_candidatos`, `inserir_inlinks`, `revisar_inlinks`, embeddings reais (Redis do `make infra`
  para cache).
- `--llm cache`: record/replay em `tests/eval/cache/` (keyed por sha256 do prompt) monkeypatching
  `BaseAgent.invoke_structured`/`_invoke_llm` — iterar prompt sem custo e determinístico.
- Saída: funil por caso + agregado, precisão/recall vs rótulos, checagem de **alucinação** (todo
  `trecho_original` aplicado é encontrado no texto ORIGINAL) e de **motivo vazio**.

### 3. Gate de merge (critério de aceite)

- ≥70% dos `deve_aplicar` → `aplicado`
- **0** `nao_linkar` → `aplicado`
- **0** alucinações · **0** itens sem motivo
- Distribuir mantém ≥8/10 no caso de referência

### 4. `backend/tests/eval/test_eval_smoke.py`

Wrapper pytest com `@pytest.mark.eval` — skip por default (sem `OPENAI_API_KEY` ou fixtures); CI
intacto.

## Verificação

1. `python -m scripts.eval_inlinks --llm real` contra o código ATUAL → baseline "antes" arquivado no
   próprio relatório.
2. Repetir após a SPEC_Inlinks_Julgamento_Unico → gate de aceite atingido.

## Riscos

- Custo de `--llm real`: ~10 casos × poucas chamadas gpt-4.1 — centavos; o modo cache elimina custo
  nas iterações.
- Fixtures sintéticas (reconstruídas das specs) aproximam os casos reais; enriquecer com scrapes do
  domínio do usuário quando conveniente.
