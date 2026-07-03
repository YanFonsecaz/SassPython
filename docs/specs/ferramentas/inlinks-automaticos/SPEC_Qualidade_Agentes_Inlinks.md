# SPEC — Qualidade e robustez dos agentes LLM de inlinks

**Status:** ✅ aplicado (commit 0cbe741)
**Escopo:** backend (`app/agents/inlinks/{inseridor,enriquecedor_metadados,reranker,revisor}.py`)
**Crédito:** não muda
**Esforço:** ~5h
**Depende de:** nada. As 4 sub-partes (§4.1–§4.4) são independentes e podem virar PRs separados.

## 1. Resumo

Quatro problemas de qualidade/latência nos agentes LLM de inlinks:
1. **Latência**: chamadas LLM por candidato em **série** (até 20× gpt-4.1).
2. **Robustez**: parsing JSON frágil (find/rfind) no inseridor e enriquecedor — a doc do LangChain recomenda *structured output* ("instead of parsing natural language responses…"), já usado pelo reranker/revisor.
3. **Determinismo**: temperatura **0.7** numa tarefa de **cópia literal** (inseridor) e num **juiz** (revisor).
4. **Fail-open**: falhas de infra (embeddings/LLM) **relaxam** os portões de qualidade silenciosamente.

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | Inserção lenta | `inseridor.py:186-208` | loop `await` por candidato (seleção + proposta LLM) em série |
| 2 | Falha de parse vira "sem inserção"/metadados vazios | `inseridor.py:612` (`_parse_proposta_unica`); `enriquecedor_metadados.py:118` (`_parse`) | `find/rfind` de chaves; sem `invoke_structured` |
| 3 | Inseridor parafraseia (quebra match exato) e revisor oscila | `inseridor.py:294`, `revisor.py:129`, `reranker.py:101`, `enriquecedor:52` | `temperature=settings.llm_temperature` (0.7) |
| 4 | Links ruins passam quando embeddings/LLM falham | `inseridor.py:236-243` (cosine default 1.0); `revisor.py:113-116` (mantém todos) | fallback fail-open |
| 5 | `ChatOpenAI` recriado a cada chamada | `inseridor:292`, `reranker:99`, `enriquecedor:50`, `revisor:127` | override do `self.llm` sem cache; ainda cria o base (glm) antes |

## 3. Decisão de arquitetura

- **Reusar a infra do `BaseAgent`** (já aceita `temperature`/`model` por agente — adicionada na SPEC do revisor de artigo) em vez de instanciar `ChatOpenAI` na mão em cada agente. Isso resolve #3 e #5 de uma vez (cache via `_get_chat_model` lru_cache + temperatura por agente).
- **Paralelizar** as propostas por candidato com `asyncio.gather` (o token-bucket do `llm_guard` regula a taxa).
- **Structured output** no inseridor e enriquecedor (Pydantic + `invoke_structured`), como no reranker/revisor.
- **Fail-closed nos portões**: quando embeddings/LLM falham, marcar como `sugestao_manual` (revisão humana) em vez de aprovar automaticamente.

## 4. Mudanças

### 4.1 Temperatura por agente + modelo via BaseAgent (resolve #3 e #5)

Adicionar settings (`config.py`, perto dos `*_llm_model` existentes):

```python
inlinks_inseridor_temperature: float = 0.0   # cópia literal → determinístico
inlinks_revisor_temperature: float = 0.1     # juiz
inlinks_reranker_temperature: float = 0.2
inlinks_enriquecedor_temperature: float = 0.2
```

Refatorar cada agente para usar o construtor do `BaseAgent` (que já cacheia e aceita overrides), removendo o `ChatOpenAI` manual. Ex. inseridor:

```python
class _InseridorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(
            usuario_id,
            model=settings.inseridor_llm_model or None,
            temperature=settings.inlinks_inseridor_temperature,
        )
```

> `BaseAgent` usa `_get_chat_model` (lru_cache) → instâncias reaproveitadas; sem criar o modelo base e descartar. Aplicar o mesmo a reranker/revisor/enriquecedor com seus settings.
> ⚠️ Atenção: hoje os agentes só trocam de modelo quando `llm_provider == "openai"`. Manter esse comportamento (se provider não-openai, `model=None` → usa o modelo base).

### 4.2 Paralelizar propostas por candidato (resolve #1)

`inseridor.py:186-208` — trocar o loop sequencial por `gather`:

```python
async def _processar_candidato(c):
    contexto = await _selecionar_paragrafos_relevantes(
        paragrafos, c, paragrafos_embeddings, usuario_id, ancoras_preferidas=ancoras_preferidas)
    if not contexto:
        return (c, None)
    proposta = await _propor_insercao_para_candidato(
        c, contexto, usuario_id, ancoras_preferidas=ancoras_preferidas, objetivo_linkagem=objetivo_linkagem)
    return (c, proposta)

propostas_por_candidato = list(
    await asyncio.gather(*(_processar_candidato(c) for c in candidatos_top))
)
```

> A ordem de `candidatos_top` é preservada pelo `gather`. O `llm_guard` (token bucket) evita estouro de rate-limit. `import asyncio` no topo.

### 4.3 Structured output no inseridor e enriquecedor (resolve #2)

Inseridor — schema + `invoke_structured`:

```python
class PropostaInsercaoSchema(BaseModel):
    paragrafo_idx: int = Field(description="Indice local do paragrafo (0..N)")
    trecho_original: str = Field(default="", description="Trecho copiado EXATAMENTE")
    anchor_text: str = Field(default="")
    palavra_chave_destino: str = Field(default="")
    conector_antes: str = Field(default="")
    conector_depois: str = Field(default="")
    justificativa: str = Field(default="")

# em _propor_insercao_para_candidato:
try:
    parsed_obj = await agente.invoke_structured(prompt, PropostaInsercaoSchema)
    parsed = parsed_obj.model_dump()
    if not parsed.get("trecho_original"):
        parsed = None
except Exception as e:
    logger.warning("Inseridor structured falhou para %s: %s", candidato.get("url"), e)
    parsed = None
```

> O caso "modelo recusa" (retornava `{}`) vira `trecho_original` vazio → tratar como "sem proposta" (mantém o caminho `_inseridor_vazio`). Manter `_parse_proposta_unica` como fallback opcional se quiser tolerância dupla.

Enriquecedor — schema `MetadadosSchema` análogo a `MetadadosConteudo` + `invoke_structured`, removendo `_parse`/`_invoke_llm` manuais.

### 4.4 Fail-closed nos portões (resolve #4)

Inseridor (`:242-243`): se faltar embedding, **não** assumir cosine 1.0 — marcar para revisão manual:

```python
if emb_ctx is None or emb_dst is None:
    proposta["forcar_sugestao_manual"] = True
    proposta["motivo_sugestao"] = "Não foi possível validar semanticamente (embedding indisponível)."
    todas_insercoes.append(proposta); continue
cosine_contexto = cosine_seguro(emb_ctx, emb_dst)
cosine_ancora = cosine_seguro(emb_anc, emb_tit) if (emb_anc is not None and emb_tit is not None) else 0.0
```

Revisor (`revisor.py:113-116`): se o LLM falhar, em vez de aprovar todos, **rebaixar para sugestão manual** (preferível a publicar links não revisados):

```python
except Exception as e:
    logger.warning("Revisor LLM falhou; rebaixando inlinks para sugestao manual: %s", e)
    for il in inlinks_revisaveis:
        il["status"] = "sugestao_manual"
        il["motivo_rejeicao"] = "Revisão automática indisponível — confira manualmente."
```

> ✅ **Decidido (produto):** rebaixar para `sugestao_manual` está aprovado — implementar como acima, sem reabrir. Não publicar link não revisado quando a revisão automática estiver indisponível.

## 5. Verificação

- **§4.1**: unit — cada agente pede a temperatura esperada (mockar `_get_chat_model` e capturar args, como no teste do revisor de artigo).
- **§4.2**: unit — `inserir_inlinks` com N candidatos chama o LLM N vezes mas o tempo total ≈ max (não soma); medir com stub que dorme. Resultado idêntico ao sequencial (ordem preservada).
- **§4.3**: unit — proposta válida via structured; `{}`/recusa vira "sem proposta"; metadados parseiam sem find/rfind.
- **§4.4**: unit — embedding None → `forcar_sugestao_manual`; revisor com exceção → todos `sugestao_manual`.
- **Regressão**: e2e de inlinks (`tests/e2e`/`tests/unit` existentes) seguem verdes.

## 6. Riscos

- **Paralelização e rate-limit**: o `llm_guard` já enfileira; com 20 candidatos pode haver espera (esperado). Monitorar 429.
- **Structured output em provider não-openai** (glm/ChatZhipuAI): `with_structured_output(method="function_calling")` depende de suporte do provider. O `BaseAgent.invoke_structured` já usa function_calling; validar com o provider default. Manter fallback de parsing se necessário.
- **Fail-closed muda volume de "sugestão manual"** quando há incidentes de infra — é o trade-off correto (não publicar link não validado), mas comunicar.
- **`lru_cache(maxsize=8)`** do `_get_chat_model`: com várias temperaturas/modelos novos, subir o `maxsize` (ex.: 16).

## 7. Fora de escopo

- Trocar o modelo/abordagem de ranking.
- Cachear embeddings de parágrafos entre execuções.

## 8. Arquivos alterados

- `backend/app/config.py` — temperaturas por agente de inlinks; possivelmente `lru_cache(maxsize=16)` em `base.py`.
- `backend/app/agents/inlinks/inseridor.py` — BaseAgent c/ temperatura; `gather`; structured output; fail-closed.
- `backend/app/agents/inlinks/enriquecedor_metadados.py` — BaseAgent c/ temperatura; structured output.
- `backend/app/agents/inlinks/reranker.py`, `revisor.py` — BaseAgent c/ temperatura; revisor fail-closed.
- `backend/tests/unit/` — temperatura, paralelização, structured, fail-closed.
