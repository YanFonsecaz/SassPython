# SPEC — Inlinks: Seleção de Parágrafos por Keyword + Visibilidade do Inseridor

**Status:** a aplicar · **Escopo:** `inseridor.py` (3 mudanças coordenadas) · **Crédito:** não muda
**Depende de:** [[SPEC_Inlinks_Inseridor_Palavra_Chave_Destino_Ancorada]] aplicada
**Contexto:** E2E #9 e #10 com pilar `o-que-montar-para-ganhar-dinheiro` + 4 satélites (restaurante, loja-virtual, imobiliária, agência-viagens).

- E2E #9: 4 candidatos → 4 `{}` do Inseridor → 0 sugestões persistidas. Comportamento silencioso.
- E2E #10: 3 `{}` + 1 sugestão_manual (loja-virtual com âncora "Negócios digitais"). Variação por temperatura.
- O pilar menciona "restaurante", "gastronomia", "delivery", "cardápio" literalmente → match óbvio para o destino restaurante. Mesmo assim Inseridor retornou `{}` nas duas execuções para restaurante.

## 1. Causas-raiz

Três bloqueios coordenados no `inseridor.py` que produziram o resultado:

### 1.1 Seleção de parágrafos só por cosine

`_selecionar_paragrafos_relevantes` ordena top-5 parágrafos do pilar pelo cosine entre embedding do parágrafo e embedding da consulta (`titulo + resumo` do destino).

Problema: o pilar tem ~50 parágrafos curtos. Os 5 mais próximos por cosine de "Como abrir um restaurante: guia" podem ser parágrafos do pilar que falam de "abrir empresa", "formalizar negócio", "MEI", etc. (próximos semanticamente a um guia de abertura) — em vez do parágrafo que menciona literalmente "restaurante". Resultado: o Inseridor recebe contexto onde a palavra-chave do destino não aparece e honestamente retorna `{}`.

Embedding bi-encoder é bom para tema global mas não privilegia match literal de termos curtos e específicos.

### 1.2 Prompt com viés para recusa

O prompt do Inseridor tem (na ordem):

1. EXEMPLO de "boa resposta": Python / linguagem.
2. EXEMPLO de "quando recusar": "estudo de mercado" + imobiliária → `{}`.
3. EXEMPLO de "palavra_chave_destino ancorada": "dropshipping NÃO use, retorne {}".

A sequência tem 2 EXEMPLOs reforçando recusa ("retorne {}") contra 1 reforçando match. Combinado com gpt-4.1 (mais cauteloso que gpt-4o-mini), o LLM tende a recusar quando há qualquer dúvida — mesmo no caso óbvio do restaurante.

Falta um EXEMPLO POSITIVO com **match literal** claro: parágrafo contém "restaurante" + destino tem "restaurante" nas palavras_chave → escolha a palavra "restaurante" da lista.

### 1.3 Inseridor `{}` é silencioso

Quando o LLM retorna `{}`, `_propor_insercao_para_candidato` retorna `None` e o candidato é descartado. Não vira sugestão, não vira rejeição — simplesmente some. O usuário vê "0 aplicadas, 0 rejeitadas" sem entender por quê.

Quando o problema é "Inseridor não achou âncora", o usuário deveria ver isso como sugestão informativa com motivo: "Nenhum parágrafo do pilar menciona termos específicos do destino (X, Y, Z)" — para que ele possa decidir reescrever o pilar ou trocar o destino.

## 2. Mudanças

### 2.1 Fix B — Boost de keyword match em `_selecionar_paragrafos_relevantes`

#### Adicionar dois helpers antes da função (após `_paragrafo_elegivel`):

```python
def _termos_keyword_destino(candidato: dict) -> list[str]:
    """Coleta termos de busca lexical do destino: palavras_chave + título.
    Filtra stopwords genéricas e termos curtos."""
    termos: list[str] = []
    palavras = candidato.get("palavras_chave") or []
    if isinstance(palavras, list):
        termos.extend(str(p).strip() for p in palavras if p and len(str(p).strip()) >= 3)
    titulo = candidato.get("titulo", "") or ""
    for t in titulo.split():
        t_clean = t.strip(",.:;!?()[]\"'").lower()
        if len(t_clean) >= 4 and _normalize_token(t_clean) not in _STOPWORDS_GENERICAS:
            termos.append(t_clean)
    vistos: set[str] = set()
    out: list[str] = []
    for t in termos:
        n = _normalize_token(t)
        if n in _STOPWORDS_GENERICAS or n in vistos or len(n) < 3:
            continue
        vistos.add(n)
        out.append(t)
    return out


def _keyword_boost(paragrafo: str, termos: list[str]) -> float:
    """Bonus aditivo ao cosine para parágrafos com match literal.
    Cap em 0.25 — embedding semântico continua dominante."""
    if not termos or not paragrafo:
        return 0.0
    matches = sum(1 for t in termos if _contem_termo(paragrafo, t))
    if matches == 0:
        return 0.0
    return min(0.25, 0.08 * matches)
```

#### Reescrever `_selecionar_paragrafos_relevantes` para somar boost:

```python
async def _selecionar_paragrafos_relevantes(
    paragrafos: list[str],
    candidato: dict,
    paragrafos_embeddings: list,
    usuario_id: str,
    top_n: int = _TOP_N_PARAGRAFOS,
) -> list[tuple[int, str]]:
    consulta = _texto_destino(candidato)[:1500]
    emb_consulta_lst = await gerar_embeddings_batch([consulta], usuario_id)
    emb_consulta = emb_consulta_lst[0] if emb_consulta_lst else None
    termos_kw = _termos_keyword_destino(candidato)

    if emb_consulta is None:
        elegiveis = [(i, p) for i, p in enumerate(paragrafos) if _paragrafo_elegivel(p)]
        if termos_kw:
            scored_kw = [(i, p, _keyword_boost(p, termos_kw)) for i, p in elegiveis]
            scored_kw.sort(key=lambda x: x[2], reverse=True)
            return [(i, p) for i, p, _ in scored_kw[:top_n]]
        return elegiveis[:top_n]

    scored: list[tuple[int, str, float, float]] = []
    for i, (p, emb_p) in enumerate(zip(paragrafos, paragrafos_embeddings)):
        if emb_p is None or not _paragrafo_elegivel(p):
            continue
        cosine = cosine_seguro(emb_consulta, emb_p)
        boost = _keyword_boost(p, termos_kw)
        scored.append((i, p, float(cosine) + boost, boost))

    scored.sort(key=lambda x: x[2], reverse=True)
    n_kw_match = sum(1 for _, _, _, b in scored[:top_n] if b > 0)
    logger.info(
        "Inseridor: top-%d parágrafos para %s — %d com keyword match (termos=%s)",
        top_n, candidato.get("url", "?")[-60:], n_kw_match,
        ", ".join(termos_kw[:5]),
    )
    return [(i, p) for i, p, _, _ in scored[:top_n]]
```

**Justificativa técnica:** equivale a uma fusão simples BM25 + dense (técnica padrão em RAG/IR, ver LangChain `EnsembleRetriever`). Sem dep nova: usa o `_contem_termo` já existente. Boost cap em 0.25 garante que cosine continua dominante — só quebra empate quando há match literal.

### 2.2 Fix A — Suavizar prompt do Inseridor + log temporário

#### Reordenar e adicionar EXEMPLO positivo de match literal

Substituir o bloco de EXEMPLOs (linhas 338-362 do `_build_prompt_focado`) por:

```text
EXEMPLO 1 — match literal direto (caminho padrão):

Parágrafo L0: "Restaurante que ofereça um cardápio específico, com estrutura para entregas, aproveita o crescimento do delivery."
URL destino: como-abrir-um-restaurante
Palavras-chave do destino: ["restaurante", "gastronomia", "cardápio", "delivery"]

Resposta:
{"paragrafo_idx": 0, "trecho_original": "Restaurante que ofereça", "anchor_text": "Restaurante", "palavra_chave_destino": "restaurante", "justificativa": "Trecho menciona 'restaurante' literalmente; destino aprofunda como abrir um restaurante."}

EXEMPLO 2 — match por sinônimo PRESENTE na lista (caminho válido):

Parágrafo L1: "Python é uma das linguagens mais populares para iniciantes."
URL destino: melhor-linguagem-iniciantes / Palavras-chave: ["linguagem", "Python", "iniciantes"]

Resposta:
{"paragrafo_idx": 1, "trecho_original": "Python é uma das linguagens", "anchor_text": "Python", "palavra_chave_destino": "Python", "justificativa": "Trecho menciona 'Python', que é uma das palavras-chave do destino."}

EXEMPLO 3 — quando recusar (sem match no parágrafo NEM na lista):

Parágrafo: "Antes de empreender, faça um estudo de mercado completo."
URL destino: como-abrir-uma-imobiliaria / Palavras-chave: ["imobiliária", "imóveis", "corretagem"]

Nenhum termo das palavras-chave aparece no parágrafo. Resposta: {}.

REGRA DE DECISÃO: se algum termo das palavras-chave do destino aparece literalmente em algum parágrafo (mesmo flexionado), você DEVE propor uma inserção. Só retorne {} quando nenhum parágrafo menciona termos específicos do destino.
```

Mudanças-chave:
- 2 EXEMPLOs POSITIVOS antes do exemplo de recusa (reorder).
- EXEMPLO 1 é o caso "restaurante" — match literal exato.
- EXEMPLO 2 remove o caso "dropshipping" (anti-padrão); usa Python no lugar (todos termos da lista).
- Regra de decisão final em uma frase: "se aparece literalmente, DEVE propor".

#### Log temporário (deletável depois de validar)

No início de `_propor_insercao_para_candidato`, antes de invocar o LLM:

```python
logger.info(
    "Inseridor: prompt para %s (%d chars, %d parágrafos)\n%s\n---END PROMPT---",
    candidato.get("url", "?"),
    len(prompt),
    len(contexto_paragrafos),
    prompt[:3000],
)
```

E após `resposta` chegar, antes de parse:

```python
logger.info(
    "Inseridor: resposta para %s: %s",
    candidato.get("url", "?"),
    (resposta or "")[:500],
)
```

Esses 2 logs ficam até confirmar comportamento esperado em E2E #11. Depois removemos.

### 2.3 Fix C — Visibilidade quando Inseridor retorna `{}`

Hoje `_propor_insercao_para_candidato` retorna `None` quando o LLM devolve `{}`. Isso some no `inserir_inlinks` (loop ignora `None`). Vamos converter em sugestão informativa.

#### Em `_propor_insercao_para_candidato`, substituir o `return None` do bloco `if not parsed:`:

```python
if not parsed:
    logger.warning(
        "Inseridor: LLM não propôs inserção para %s. Resposta: %s",
        candidato.get("url"),
        (resposta or "")[:400],
    )
    termos_kw = _termos_keyword_destino(candidato)
    motivo = (
        f"Inseridor não encontrou parágrafo do pilar com termos do destino "
        f"({', '.join(termos_kw[:5])}). Considere reescrever o pilar mencionando o nicho."
    )
    return {
        "url_destino": candidato["url"],
        "anchor_text": "",
        "trecho_original": "",
        "paragrafo_idx": 0,
        "forcar_sugestao_manual": True,
        "motivo_sugestao": motivo,
        "_inseridor_vazio": True,
    }
```

#### Em `_aplicar_insercoes`, tratar `_inseridor_vazio`:

Logo após `c = candidatos_by_url.get(url, {})` no loop de sugestões (linha ~514), adicionar guarda no loop principal antes do `p_idx = ins.get("paragrafo_idx", -1)`:

```python
if ins.get("_inseridor_vazio"):
    sugestoes.append({**ins, "motivo_sugestao": ins.get("motivo_sugestao")})
    continue
```

Isso garante que o candidato vira `sugestao_manual` em `inlinks_sugeridos` com motivo claro, em vez de sumir.

## 3. Verificação E2E #11

Mesmas URLs da E2E #9/#10. Esperado **após o fix**:

| Candidato | Comportamento esperado | Critério |
|---|---|---|
| **restaurante** | `aplicado` (1 inlink) | Parágrafo selecionado contém "restaurante" literal via keyword boost. Inseridor escolhe `palavra_chave_destino` em ["restaurante","gastronomia","cardápio","delivery"]. |
| loja-virtual | `sugestao_manual` ou `aplicado` | Pilar não menciona "loja virtual" literal → sugestão informativa com motivo "termos não encontrados". |
| imobiliária | `sugestao_manual` informativa | Motivo: "Pilar não menciona 'imobiliária', 'imóveis', 'corretagem'." |
| agência-viagens | `sugestao_manual` informativa | Motivo: "Pilar não menciona 'viagens', 'turismo'." |

**Métricas-chave:**
- `n_aplicadas >= 1` (restaurante destrava).
- `len(inlinks_sugeridos) == 4` — todo candidato vira linha visível no banco, mesmo que sem aplicação.
- Log do worker contém `"Inseridor: top-5 parágrafos para .../restaurante — N com keyword match"` com `N >= 1`.

## 4. Riscos

- **Boost de 0.25 pode promover parágrafo ruim** quando há keyword match mas tema diferente (ex: parágrafo "evite restaurantes caros ao montar empresa" para destino "abrir restaurante"). Mitigação: cap em 0.25 é menor que diferença típica de cosine entre temas (~0.4). Embedding ainda decide se o parágrafo é tematicamente próximo.
- **EXEMPLO de match literal pode levar Inseridor a aceitar mentions casuais**. Mitigação: a validação `_validar_palavra_chave_destino` (já endurecida na SPEC anterior) continua filtrando — kw_destino tem que estar nas palavras_chave do destino.
- **Sugestões informativas poluem dashboard** se sempre houver 4 por execução. Aceitável: para o público não-técnico do produto, é melhor mostrar "nenhum link cabe porque..." do que "0 sugestões".
- **Logs grandes em produção** (prompt de ~3000 chars × candidato). Mitigação: removível após E2E #11; pode virar `logger.debug` se ficar permanente.

## 5. Não-objetivos

- Não vamos adicionar `rank_bm25` como dep nova — fix B usa boost aditivo simples (suficiente para o problema observado).
- Não vamos tocar Reranker, Revisor, Cleaner, Formatador, Enriquecedor — análise mostra que estão OK pós-SPECs anteriores.
- Não vamos relaxar `_validar_palavra_chave_destino` — a validação continua dura por design (impede alucinação de sinônimos).
- Não vamos suavizar regras 1-7 do prompt — só os EXEMPLOs.

## 6. Plano de execução

1. Aplicar 2.1 (helpers + reescrita de `_selecionar_paragrafos_relevantes`).
2. Aplicar 2.2 (reescrita do bloco de EXEMPLOs + 2 logs temporários).
3. Aplicar 2.3 (sugestão informativa em `_propor_insercao_para_candidato` + guarda em `_aplicar_insercoes`).
4. Restart worker, invalidar cache, rodar E2E #11 com mesmas URLs.
5. Validar critérios da seção 3.
6. Remover os 2 logs temporários (2.2) após confirmação.
