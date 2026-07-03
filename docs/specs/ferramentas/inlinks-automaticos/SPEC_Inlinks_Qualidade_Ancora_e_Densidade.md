# SPEC — Inlinks: filtro de âncora genérica + diversidade de parágrafos + proximidade adaptativa

**Status:** ✅ implementado
**Escopo:** backend (inseridor + revisor + workflow)
**Crédito:** não muda
**Depende de:** `SPEC_Inlinks_Refinamentos_Finais.md` aplicada

---

## Contexto

Teste E2E real (`39b2a020`, 13/05/2026) com pilar "O que montar para ganhar dinheiro?" (2317 palavras) e 4 candidatas Agilize expôs 3 problemas restantes:

| Candidata | Status | Anchor | Problema |
|---|---|---|---|
| loja-virtual | ✅ aplicado | "Negócios digitais, consultorias, serviços por demanda ou revenda sem estoque" | OK |
| imobiliária | ❌ aplicado **forçado** | "que tipo de negócio devo abrir" | Âncora genérica/retórica casada com URL específica |
| restaurante | ⚠️ sugestao_manual | "estrutura física, o investimento" | Caiu por proximidade |
| agência-viagens | recusado | (LLM `{}`) | Correto |

**Densidade alvo dinâmica**: ~10 (2317/222) com teto user 8. **Entregue**: 2 aplicados (25%).

### Diagnóstico

1. **Âncoras retóricas/genéricas passam todos os filtros**: "que tipo de negócio devo abrir" → imobiliária. Reranker dá `score_contexto=0.85` porque "imobiliária é tipo de negócio". Inseridor propõe. Validação D cosine passa (ambos textos falam de "tipo de negócio"). Revisor aprova. Nenhum dos 4 filtros pega que **âncora curta + genérica + sem termo específico do destino = link ruim**.
2. **Concentração de propostas em parágrafos vizinhos**: 2 de 3 candidatos propostos caíram nos parágrafos P71/P73. Como Inseridor é chamado 1× por candidato sem visão dos parágrafos já usados, ele converge para "o melhor parágrafo absoluto" — que tende a ser o mesmo. Resultado: heurística de proximidade derruba 1 bom link.
3. **`_MIN_DISTANCE_WORDS=100` fixo**: pilares de 2300 palavras com densidade alvo 8 deveriam ter ~290 palavras por link. 100 está conservador demais quando os parágrafos elegíveis estão concentrados.

### Resultado esperado

- Âncoras genéricas/retóricas viram `sugestao_manual` (não forçadas como `aplicado`).
- Inseridor sabe quais parágrafos já foram usados e prefere distribuir.
- Proximidade adaptativa: `max(50, palavras_pilar / (max_inlinks * 2))`.
- Em pilares longos com candidatas relevantes, densidade real se aproxima do alvo dinâmico.

---

## 1. Resumo

Três entregas. Pode ser 1 PR com 3 commits.

| # | Entrega | Arquivos | Esforço |
|---|---|---|---|
| **1** | Validação semântica âncora-só vs título-destino (cosine baixo → sugestao_manual) | `inseridor.py` | 10 min |
| **2** | Inseridor recebe `paragrafos_ja_usados` e exclui do contexto | `inseridor.py` | 10 min |
| **3** | `_MIN_DISTANCE_WORDS` adaptativo por densidade | `inseridor.py` | 5 min |

Total ~25 min.

---

## 2. Entrega 1 — Validação semântica âncora-só

### Problema

A validação D atual compara `(trecho + parágrafo[:200])` contra `(título + resumo[:300])`. Como o **parágrafo** carrega contexto rico, o cosine fica alto mesmo quando a **âncora pura** ("que tipo de negócio devo abrir") não menciona termo central do destino ("imobiliária").

### Solução

Adicionar 2º cosine: âncora-só vs título-só do destino. Se **ambos** os cosines (D original + âncora-só) ficarem baixos, vira `sugestao_manual`.

### `backend/app/agents/inlinks/inseridor.py`

Adicionar constante:

```python
_MIN_ANCORA_TITULO = 0.35
```

(Threshold mais frouxo que `_MIN_INSERCAO_SEMANTICA=0.50` porque âncora vs título é comparação mais curta e ruidosa.)

Em `inserir_inlinks`, ampliar o batch de embeddings para incluir o par âncora-vs-título por candidato:

```python
pares_para_validar: list[tuple[dict, dict]] = []
textos_batch: list[str] = []
for c, proposta in propostas_por_candidato:
    if not proposta:
        continue
    p_idx = proposta.get("paragrafo_idx", -1)
    trecho = proposta.get("trecho_original", "")
    anchor = proposta.get("anchor_text") or trecho
    paragrafo = paragrafos[p_idx] if 0 <= p_idx < len(paragrafos) else ""
    contexto = f"{trecho} {paragrafo[:200]}"
    destino = _texto_destino(c)
    titulo = c.get("titulo", "") or ""

    pares_para_validar.append((c, proposta))
    textos_batch.append(contexto)    # i*4
    textos_batch.append(destino)     # i*4 + 1
    textos_batch.append(anchor)      # i*4 + 2
    textos_batch.append(titulo)      # i*4 + 3

embs_batch: list = []
if textos_batch:
    embs_batch = await gerar_embeddings_batch(textos_batch, usuario_id)
```

E na validação após o batch:

```python
for i, (c, proposta) in enumerate(pares_para_validar):
    emb_ctx = embs_batch[i * 4] if i * 4 < len(embs_batch) else None
    emb_dst = embs_batch[i * 4 + 1] if i * 4 + 1 < len(embs_batch) else None
    emb_anc = embs_batch[i * 4 + 2] if i * 4 + 2 < len(embs_batch) else None
    emb_tit = embs_batch[i * 4 + 3] if i * 4 + 3 < len(embs_batch) else None

    cosine_contexto = cosine_seguro(emb_ctx, emb_dst) if emb_ctx is not None and emb_dst is not None else 1.0
    cosine_ancora = cosine_seguro(emb_anc, emb_tit) if emb_anc is not None and emb_tit is not None else 1.0

    if cosine_contexto < _MIN_INSERCAO_SEMANTICA:
        proposta["forcar_sugestao_manual"] = True
        proposta["motivo_sugestao"] = "Baixa relação semântica entre âncora e destino."
    elif cosine_ancora < _MIN_ANCORA_TITULO:
        proposta["forcar_sugestao_manual"] = True
        proposta["motivo_sugestao"] = "Âncora genérica — não menciona termo específico do destino."
    todas_insercoes.append(proposta)
```

### Validação no caso real

- âncora "que tipo de negócio devo abrir" vs título "Como abrir uma imobiliária" → embeddings de strings sem overlap léxico real ("imobiliária" não aparece na âncora). Cosine esperado: 0.25-0.35. Deve cair abaixo de `_MIN_ANCORA_TITULO=0.35` e virar sugestao_manual. ✓
- âncora "Negócios digitais... dropshipping" vs título "Como abrir uma loja virtual" → "dropshipping" e "loja virtual" são semanticamente próximas. Cosine esperado: 0.45-0.60. Passa. ✓

### Por que não usar o Revisor?

Revisor já tem regra textual; gpt-4.1 deixou passar por interpretar "tipo de negócio" como genérico-mas-relacionado. Filtro determinístico via cosine âncora-só é **previsível e barato** (já tem o batch de embeddings).

---

## 3. Entrega 2 — Inseridor evita parágrafos já usados

### Problema

`inserir_inlinks` chama `_propor_insercao_para_candidato` sequencialmente por candidato. Cada chamada vê os top-5 parágrafos por similaridade, mas **não sabe quais parágrafos já receberam proposta em iterações anteriores**. Resultado: convergência para mesmos parágrafos "ricos".

### Solução

Manter `paragrafos_ja_propostos: set[int]` durante o loop. Passar ao `_selecionar_paragrafos_relevantes` para excluir esses parágrafos do contexto entregue ao LLM.

### `backend/app/agents/inlinks/inseridor.py`

Modificar assinatura:

```python
async def _selecionar_paragrafos_relevantes(
    paragrafos: list[str],
    candidato: dict,
    paragrafos_embeddings: list,
    usuario_id: str,
    excluidos: set[int] | None = None,    # novo
    top_n: int = _TOP_N_PARAGRAFOS,
) -> list[tuple[int, str]]:
    excluidos = excluidos or set()
    consulta = _texto_destino(candidato)[:1500]
    emb_consulta_lst = await gerar_embeddings_batch([consulta], usuario_id)
    emb_consulta = emb_consulta_lst[0] if emb_consulta_lst else None

    if emb_consulta is None:
        elegiveis = [
            (i, p) for i, p in enumerate(paragrafos)
            if _paragrafo_elegivel(p) and i not in excluidos
        ]
        return elegiveis[:top_n]

    scored: list[tuple[int, str, float]] = []
    for i, (p, emb_p) in enumerate(zip(paragrafos, paragrafos_embeddings)):
        if emb_p is None or not _paragrafo_elegivel(p) or i in excluidos:
            continue
        cosine = cosine_seguro(emb_consulta, emb_p)
        scored.append((i, p, float(cosine)))

    scored.sort(key=lambda x: x[2], reverse=True)
    return [(i, p) for i, p, _ in scored[:top_n]]
```

### `inserir_inlinks` (mesmo arquivo)

```python
todas_insercoes: list[dict] = []
propostas_por_candidato: list[tuple[dict, dict | None]] = []
paragrafos_ja_propostos: set[int] = set()    # novo

for c in candidatos_top:
    contexto_paragrafos = await _selecionar_paragrafos_relevantes(
        paragrafos,
        c,
        paragrafos_embeddings,
        usuario_id,
        excluidos=paragrafos_ja_propostos,    # novo
    )
    if not contexto_paragrafos:
        logger.info("Inseridor: candidato %s sem parágrafos elegíveis", c.get("url"))
        propostas_por_candidato.append((c, None))
        continue

    proposta = await _propor_insercao_para_candidato(c, contexto_paragrafos, usuario_id)
    if not proposta:
        propostas_por_candidato.append((c, None))
        continue

    # Marca o parágrafo escolhido como usado para próximos candidatos
    idx = proposta.get("paragrafo_idx", -1)
    if isinstance(idx, int) and 0 <= idx < len(paragrafos):
        paragrafos_ja_propostos.add(idx)

    propostas_por_candidato.append((c, proposta))
```

### Fallback quando `excluidos` esvazia o contexto

Se todos os top-5 parágrafos elegíveis já foram usados, `contexto_paragrafos == []` e o candidato é pulado. Aceitável — significa que não há onde inserir sem amontoar.

Mitigação: se `len(contexto_paragrafos) < 3` após exclusão, **re-incluir** os parágrafos excluídos (ainda penalizando, mas permitindo) — opcional para v2. Por enquanto, simplicidade primeiro.

---

## 4. Entrega 3 — Proximidade adaptativa

### Problema

`_MIN_DISTANCE_WORDS = 100` fixo é apertado demais para pilares longos onde os parágrafos elegíveis estão concentrados. Pilar de 2317 palavras com max_inlinks=8 deveria ter ~290 palavras de espaçamento médio — 100 derruba bons candidatos por proximidade.

### Solução

Calcular dinamicamente baseado no tamanho do pilar e densidade alvo.

### `backend/app/agents/inlinks/inseridor.py`

Substituir uso direto de `_MIN_DISTANCE_WORDS` por cálculo dinâmico:

```python
_MIN_DISTANCE_WORDS_BASE = 100  # piso quando pilar é curto

def _calcular_min_distance(pilar_markdown: str, max_inlinks: int) -> int:
    n_palavras = len(pilar_markdown.split())
    if max_inlinks <= 0:
        return _MIN_DISTANCE_WORDS_BASE
    # alvo de espacamento = palavras / (2 * max_inlinks) — metade do espacamento natural
    # garante piso de 50 e teto de 200 para evitar extremos
    distancia = max(50, min(200, n_palavras // (max_inlinks * 2)))
    return distancia
```

Em `_aplicar_insercoes`, receber o valor calculado:

```python
def _aplicar_insercoes(
    pilar_markdown: str,
    paragrafos: list[str],
    candidatos: list[dict],
    insercoes_raw: list[dict],
    min_distance_words: int = _MIN_DISTANCE_WORDS_BASE,    # novo
) -> tuple[str, list[InlinkInserido]]:
    ...
    too_close = any(abs(word_pos - wp) < min_distance_words for wp in accepted_word_positions)
```

E em `inserir_inlinks`, passar o valor:

```python
min_dist = _calcular_min_distance(pilar_markdown, max_inlinks)
logger.info("Inseridor: min_distance_words=%d (palavras=%d, max=%d)",
            min_dist, len(pilar_markdown.split()), max_inlinks)
return _aplicar_insercoes(pilar_markdown, paragrafos, candidatos_top, todas_insercoes, min_distance_words=min_dist)
```

### Exemplos

| Pilar (palavras) | max_inlinks | Distância calculada | Comentário |
|---|---|---|---|
| 800 | 4 | 100 (piso) | Pilar curto, mantém conservador |
| 2317 | 8 | 144 | Caso real do teste |
| 4000 | 10 | 200 (teto) | Pilar muito longo, não vira spam |
| 1500 | 2 | 200 (teto) | Densidade baixa, espaça bem |

---

## 5. Verificação ponta a ponta

### 5.1 Sanidade de import

```bash
grep -n "_MIN_ANCORA_TITULO\|paragrafos_ja_propostos\|_calcular_min_distance\|excluidos" backend/app/agents/inlinks/inseridor.py | head -10
```

### 5.2 Restart

```bash
pkill -f "arq app.worker"
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
ps aux | grep "arq app.worker" | grep -v grep | head -1
```

### 5.3 Re-rodar o mesmo teste E2E

Pilar: `https://agilize.com.br/blog/abrir-sua-empresa/o-que-montar-para-ganhar-dinheiro/`
Satélites: agencia-viagens, restaurante, loja-virtual, imobiliaria.

**Expectativas**:

1. **imobiliaria deve cair em sugestao_manual** com motivo "Âncora genérica — não menciona termo específico do destino." (ou trocar de âncora para algo com "imobiliária" explícito — depende do LLM).
2. **restaurante deve aplicar** se o Inseridor distribuir em parágrafo diferente do da loja-virtual (P73). Possível P71 sobre orçamento.
3. **Distância mínima ~144 palavras** no log: `Inseridor: min_distance_words=144`.
4. **Densidade final**: 2-3 aplicados (vs. 2 do baseline), idealmente 3 (loja-virtual + restaurante + um outro).

### 5.4 SQL de auditoria

```sql
SELECT url_destino, anchor_text, status, score_total, motivo_rejeicao
FROM inlinks_sugeridos
WHERE execucao_id = '<eid>'
ORDER BY score_total DESC;
```

---

## 6. Fora de escopo

- **Re-prompt completo do Inseridor** com instrução "use termo central do destino" — Entrega 1 já cobre via filtro determinístico, mais robusto.
- **Diversidade por similaridade** (penalizar parágrafos *próximos* ao já-usado, não só o exato) — escalonamento futuro.
- **Calibração de threshold** `_MIN_ANCORA_TITULO` em produção — começar com 0.35, ajustar via medição.
- **Reprocessar candidato que virou sugestao_manual** com novo prompt forçando termo do título — adiciona 1 LLM call extra.

---

## 7. Riscos

- **`_MIN_ANCORA_TITULO=0.35` pode ser severo demais** para títulos longos com palavras genéricas (ex.: "Como abrir [tipo] em 2026"). Mitigação: comparação usa embedding completo, palavras genéricas têm menor peso. Se em produção for falso-positivo recorrente, baixar para 0.30.
- **`paragrafos_ja_propostos` esgota contexto em pilares curtos** — fix natural: o LLM recusa proposta e candidato vira sugestao_manual com motivo claro.
- **Proximidade muito relaxada (até 200)** pode permitir 2 links no mesmo parágrafo grande — improvável porque `_aplicar_insercoes` ordena candidatos por score, e o melhor parágrafo é "pego" primeiro pelo mais relevante.

---

## 8. Arquivos críticos

### Backend — alterados
- `backend/app/agents/inlinks/inseridor.py`:
  - Adicionar `_MIN_ANCORA_TITULO`, `_calcular_min_distance`.
  - `inserir_inlinks`: batch 4 textos por candidato, set de `paragrafos_ja_propostos`, distância dinâmica.
  - `_selecionar_paragrafos_relevantes`: parâmetro `excluidos`.
  - `_aplicar_insercoes`: parâmetro `min_distance_words`.

### Backend — sem mudança
- Reranker, Revisor, Workflow não mudam — toda a lógica fica no Inseridor.

### Frontend
- Nenhuma alteração.

---

## 9. Verificação (sumário)

1. Grep confirma novas constantes e helpers.
2. Restart sem erro.
3. Re-rodar E2E com pilar "o-que-montar-para-ganhar-dinheiro": `imobiliária` deve cair em sugestao_manual; densidade real ≥ baseline.
4. Log mostra `min_distance_words` calculado dinamicamente.
5. Inserir log de "Âncora genérica" e "parágrafo já usado" ajuda debug.
