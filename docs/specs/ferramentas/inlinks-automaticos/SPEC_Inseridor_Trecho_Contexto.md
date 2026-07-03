# SPEC — `trecho_contexto`/`offset_chars` corretos no inseridor

**Status:** ✅ implementado
**Escopo:** backend (`app/agents/inlinks/inseridor.py`, limpeza em `injector.py`)
**Crédito:** não muda
**Esforço:** ~2h
**Depende de:** nada (pode ir em paralelo)

## 1. Resumo

Em `_aplicar_insercoes`, o `trecho_contexto` (snippet "onde o link entrou", **persistido** em `InlinkSugerido.trecho_contexto` e exibido na UI) é extraído usando o **offset original** do trecho contra o **texto já modificado**. Como cada link inserido desloca todas as posições seguintes, só o inlink de **menor** offset fica correto; os demais mostram um trecho deslocado/garbled. O `offset_chars` persistido sofre do mesmo problema.

Aproveita-se a SPEC para remover a 2ª engine de inserção morta (`injector.injetar_inlinks`) e corrigir 2 itens de limpeza no inseridor.

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | `trecho_contexto` errado para 2º+ inlink | `inseridor.py:918-922` | usa `offset` original em `texto` modificado; `_extrair_trecho_contexto` fatia por offset (`injector.py`) |
| 2 | `offset_chars` persistido não bate com o texto final | `inseridor.py:926` | mesmo offset original |
| 3 | Código morto: 2ª engine de inserção | `injector.injetar_inlinks` (sem callers) | só os helpers do `injector` são usados |
| 4 | Anotação de tipo malformada | `inseridor.py:184` `dict[str, Any][str, Any]` | typo de `dict[str, Any] | None` |
| 5 | Offsets assumem `\n\n` exato | `inseridor.py:871,785` | `sum(len(p)+2 …)` quebra com espaçamento irregular |

## 3. Decisão de arquitetura

As inserções já são aplicadas **descendente** por offset (`:892-914`), o que é correto. O bug está só na **segunda passada** (extração de contexto). A correção: computar o **offset final** de cada link acumulando o deslocamento das inserções à sua esquerda.

```
offset_final(v) = offset_original(v) + Σ (link_md_len_j − len(trecho_original_j))  para j com offset_original_j < offset_original(v)
```

Itera-se ascendente acumulando `shift`. É O(n), determinístico, sem re-busca por âncora (que falharia com âncoras repetidas).

### Alternativas descartadas
- **Re-localizar a âncora no texto final** (`texto.find(link_md)`): falha com âncoras/URLs repetidas e é O(n·m).
- **Extrair contexto durante a passada descendente**: o lado esquerdo ainda não teria os links inseridos depois → contexto inconsistente.

> Caveat documentado: após `node_revisar`/`node_formatar` o texto é reescrito, então `offset_chars` é **best-effort** (snapshot do estágio de inserção). O `trecho_contexto` continua válido como snippet (âncora + entorno), que é seu propósito.

## 4. Mudanças

### 4.1 `inseridor.py` — offset final acumulado (`_aplicar_insercoes`, `:916-945`)

Trocar o bloco que monta `inseridos` a partir de `validas`:

```python
inseridos: list[InlinkInserido] = []

shift = 0
for v in sorted(validas, key=lambda x: x["global_offset"]):
    c = v["candidato"]
    final_start = v["global_offset"] + shift
    final_end = final_start + v["link_md_len"]
    trecho_ctx = _extrair_trecho_contexto(texto, final_start, final_end)

    inseridos.append(InlinkInserido(
        url_destino=v["url"],
        anchor_text=v["anchor_text"],
        paragrafo_idx=v["paragrafo_idx"],
        offset_chars=final_start,                 # antes: offset original
        score_total=c.get("score_total", 0),
        score_semantico=c.get("score_semantico", 0),
        score_contexto=c.get("score_contexto", 0),
        trecho_contexto=trecho_ctx,
        titulo_destino=c.get("titulo", "") or None,
        motivo_contexto=v.get("justificativa") or c.get("motivo_contexto", "") or None,
        categoria_match=_categoria_match(c.get("score_semantico", 0), c.get("score_contexto", 0), c.get("score_total", 0)),
        trecho_original=v["trecho_original"],
        conector_antes=v["conector_antes"] or None,
        conector_depois=v["conector_depois"] or None,
        ancora_preferida_usada=bool(ancoras_preferidas and _ancora_preferida_match(v["anchor_text"], ancoras_preferidas)),
    ))
    shift += v["link_md_len"] - len(v["trecho_original"])
```

> Para CTA (`_modo_cta`), `trecho_original=""` → `shift += link_md_len` (inserção pura). Coerente.

### 4.2 `inseridor.py:184` — anotação correta

```python
propostas_por_candidato: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
```

### 4.3 `inseridor.py` — offsets robustos a espaçamento (opcional, defensivo)

O `pilar_markdown.split("\n\n")` (`:173`) e o rejoin `sum(len(p)+2 …)` (`:871,785`) divergem se houver `\n\n\n+`. Mitigação mínima: normalizar blank-lines antes de dividir:

```python
import re
pilar_markdown = re.sub(r"\n{3,}", "\n\n", pilar_markdown)
paragrafos = pilar_markdown.split("\n\n")
```

(Manter o `pilar_markdown` normalizado consistente no retorno/aplicação.)

### 4.4 `injector.py` — remover engine morta

Remover a função `injetar_inlinks` e o que for exclusivo dela (ex.: `InlinkInjetado`, `_find_paragraph_index` se não usados por mais ninguém). **Manter** os helpers usados pelo inseridor/revisor: `_categoria_match`, `_esta_em_cabecalho`, `_extrair_trecho_contexto`, `_strip_accents`, `remover_links_rejeitados`.

> Antes de remover, rodar `grep -rn "injetar_inlinks\|InlinkInjetado\|_find_paragraph_index" backend/app` para confirmar zero callers (exceto definições).

## 5. Verificação

### 5.1 Unit — offset final com 2+ links

```python
def test_trecho_contexto_alinhado_multiplos_links():
    # pilar com 2 parágrafos, 2 candidatos casando termos distintos
    texto, inseridos = await inserir_inlinks(pilar_md, candidatos, "u", max_inlinks=2)
    aplicados = [i for i in inseridos if i.status == "aplicado"]
    assert len(aplicados) == 2
    for il in aplicados:
        # a âncora deve aparecer DENTRO do trecho_contexto (entre « »)
        assert il.anchor_text.split()[0].lower() in (il.trecho_contexto or "").lower()
        # offset_chars deve apontar para o link no texto final
        assert texto[il.offset_chars: il.offset_chars + 1] in ("[", )  # inicio do markdown do link (ou conector)
```

(Ajustar a asserção de `offset_chars` ao caso com conector_antes; o ponto central é que a âncora apareça no `trecho_contexto`.)

### 5.2 Regressão — 1 link

Com um único inlink, comportamento idêntico ao atual (shift=0 no primeiro).

### 5.3 Limpeza não quebra imports

`python -c "import app.agents.inlinks.inseridor, app.agents.inlinks.injector, app.agents.workflow_inlinks"` sem erro após remover `injetar_inlinks`.

## 6. Riscos

- **`offset_chars` ainda aproximado pós-formatação**: aceitável (documentado). Se algum consumidor depender de offset exato no texto final, recomputar após `formatar` (fora de escopo).
- **Remoção de código morto**: confirmar zero callers antes (inclui `workflow_inlinks_reversos.py`).

## 7. Fora de escopo

- Recomputar offsets após `node_formatar`.
- Unificar as duas engines (a morta já será removida).

## 8. Arquivos alterados

- `backend/app/agents/inlinks/inseridor.py` — offset final acumulado; anotação `:184`; normalização de blank-lines.
- `backend/app/agents/inlinks/injector.py` — remover `injetar_inlinks` (e símbolos órfãos), manter helpers.
- `backend/tests/unit/` — alinhamento de `trecho_contexto`.
