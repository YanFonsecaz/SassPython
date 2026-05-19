# SPEC — Distribuir Inlinks: Filtro Adaptativo + Keyword Override no modo `slug_only`

**Status:** a aplicar · **Escopo:** `workflow_inlinks_reversos.py` (apenas `node_filtrar_similaridade` + pequenos ajustes em pseudo-conteúdo) · **Crédito:** mantém política atual
**Depende de:** [[SPEC_Distribuir_Inlinks_Slug_Fallback_Categoria_Produto]] aplicada
**Contexto:** E2E Mundo Cristão (categoria livros/mulheres) com slug fallback ativo produziu 5 aplicadas + **5 falsos negativos**. As 5 rejeitadas têm tema feminino-bíblico claro (mulher de Provérbios, mães na bíblia, trabalho feminino na igreja, filhas de Zelofeade, papel da mãe) — todas com cosine entre 0.41 e 0.47, abaixo do threshold 0.50. Para um SaaS SEO destinado a não-técnicos, perder 50% das oportunidades reais de inlink em uma execução paga é regressão de UX inaceitável.

## 1. Causas-raiz dos falsos negativos

### 1.1 Embedding de pseudo-conteúdo é "tópico fixo"

O pseudo-conteúdo gerado no slug fallback tem ~365 chars com repetição dos termos do slug:

```
# Arquivo de Mulheres

Esta pagina apresenta conteudo sobre livros, mulheres.
Os principais temas abordados sao livros mulheres.
Aqui voce encontra informacoes, recursos e materiais relacionados a livros, mulheres.
O foco da pagina e livros e mulheres, oferecendo opcoes variadas para quem busca livros mulheres.
Categoria: livros, mulheres. Tema: livros, mulheres.
```

Embedding desse texto é uma representação **estreita** de "livros + mulheres" sem nuance. Cosine com conteúdo redacional rico (artigos de 800-1500 palavras sobre histórias específicas) cai naturalmente para 0.40-0.48 — mesmo quando o tema é claramente afim.

Threshold 0.50 (mesmo usado para conteúdo pleno) é **calibrado para embedding rico × embedding rico**. Aplicado a embedding pobre × embedding rico, é restritivo demais.

### 1.2 Filtro semântico não considera match léxico literal

Hoje, `node_filtrar_similaridade` decide passar/descartar apenas por cosine. Mas o Inseridor (Fix B herdado da SPEC do Inseridor) tem **boost de keyword match**: parágrafos da candidata que contêm palavras-chave do destino literalmente sobem no top-N.

Esse boost **só é aplicado dentro de candidatas que passaram o filtro semântico**. As 5 candidatas rejeitadas têm "mulher", "mães", "feminino" literalmente no corpo — o Inseridor encontraria âncoras válidas se chegasse a executar nelas. Mas o filtro de cosine 0.50 corta antes.

### 1.3 Pseudo-conteúdo não cobre variações morfológicas

Slug `mulheres` (plural) é diferente de `mulher` (singular), `feminino`, `feminina`, `mães`. O pseudo-conteúdo não expande para essas formas, então embedding fica desbalanceado: candidatas que dizem "mulher" sem nunca dizer "mulheres" caem no cosine.

## 2. Solução em três camadas

### 2.1 Threshold adaptativo por `alvo_modo`

Quando `alvo_modo == "slug_only"`, aplicar fator de correção ao threshold:

```
threshold_efetivo = threshold_score * 0.65
```

Justificativa: pseudo-conteúdo de slug gera embeddings com magnitude semântica ~30-35% menor que conteúdo redacional rico. Multiplicar por 0.65 calibra o threshold sem precisar mexer no input do usuário.

Exemplo (Mundo Cristão, threshold padrão 0.5):
- Modo pleno: filtro = 0.50.
- Modo slug_only: filtro = 0.50 × 0.65 = **0.325**.

Com 0.325, as 5 candidatas (cosines 0.41-0.47) **todas passam** e vão para o Inseridor.

Manter um **piso absoluto** `_PISO_SLUG_ONLY = 0.30` para evitar admitir candidatas totalmente desconectadas se o usuário enviar threshold muito baixo.

```python
threshold_efetivo = max(threshold_score * 0.65, _PISO_SLUG_ONLY) if alvo_modo == "slug_only" else threshold_score
```

### 2.2 Keyword override (passa direto se contém termo do slug literal)

Para candidatas com cosine entre `_PISO_SLUG_ONLY` e `threshold_efetivo` — região cinzenta — verificar se o **conteúdo da candidata contém ≥ 1 palavra-chave do slug literalmente**. Se sim, força passagem.

Usa `_contem_termo` já existente (substring case-insensitive + strip de acentos).

```python
def _candidata_tem_keyword_alvo(conteudo_md: str, palavras_alvo: list[str]) -> bool:
    for p in palavras_alvo:
        if _contem_termo(conteudo_md, p):
            return True
    return False
```

Aplicado em `node_filtrar_similaridade` no modo `slug_only`:

```python
if score >= threshold_efetivo:
    viavel = True
elif alvo_modo == "slug_only" and score >= _PISO_SLUG_ONLY:
    viavel = _candidata_tem_keyword_alvo(conteudo_md_candidata, palavras_alvo)
else:
    viavel = False
```

**Defesa em profundidade:** mesmo se uma candidata passa por keyword override mas o tema for fraco, o Inseridor + validação dura de palavra-chave do destino vai rejeitar. Pior caso: vira `sugestao_manual` com motivo claro.

### 2.3 Pseudo-conteúdo enriquecido com variações morfológicas

`_construir_pseudo_alvo` ganha expansão simples de plural/feminino:

```python
def _variacoes_morfologicas(termo: str) -> list[str]:
    """Variações simples para PT-BR: plural↔singular, feminino↔masculino básicos.
    Não tenta ser linguisticamente perfeito; cobre os casos mais comuns para
    melhorar densidade do embedding sem chamar dicionário externo."""
    t = termo.lower().strip()
    if len(t) < 4:
        return [t]
    out = {t}
    # plural/singular
    if t.endswith("s") and len(t) > 4:
        out.add(t[:-1])  # mulheres -> mulhere (não ideal); refinar para -es
    if t.endswith("es") and len(t) > 5:
        out.add(t[:-2])  # mulheres -> mulher
    elif not t.endswith("s"):
        out.add(t + "s")  # mulher -> mulheres (parcial; mulher -> mulheres falha)
    # gênero (-a/-o)
    if t.endswith("a"):
        out.add(t[:-1] + "o")  # feminina -> feminino
    elif t.endswith("o"):
        out.add(t[:-1] + "a")
    return sorted(out)
```

No `_construir_pseudo_alvo`, incluir variações no texto:

```python
todas_formas: list[str] = []
for t in termos_slug:
    todas_formas.extend(_variacoes_morfologicas(t))
todas_formas_uniq = list(dict.fromkeys(todas_formas))  # preserva ordem

# Pseudo enriquecido
pseudo = (
    f"# {titulo_limpo or termos_slug[0].title()}\n\n"
    f"Esta pagina apresenta conteudo sobre {', '.join(termos_slug)}. "
    f"Termos relacionados: {', '.join(todas_formas_uniq)}. "
    f"Os principais temas abordados sao {bigramas_str}. "
    f"Aqui voce encontra informacoes, recursos e materiais relacionados a "
    f"{', '.join(todas_formas_uniq)}. "
    f"O foco da pagina e {' e '.join(termos_slug[:3])}, oferecendo opcoes "
    f"variadas para quem busca {bigramas_str}. "
    f"Categoria: {', '.join(termos_slug)}. "
    f"Tema: {', '.join(todas_formas_uniq)}."
)

# palavras_chave também recebem as formas para o boost de keyword no Inseridor
palavras_chave = list(dict.fromkeys(todas_formas_uniq + bigramas))
```

Resultado para slug `livros/mulheres`:
- `palavras_chave` antes: `["livros", "mulheres", "livros mulheres", "arquivo"]`
- `palavras_chave` depois: `["livros", "livro", "mulheres", "mulher", "mulhere", "livros mulheres", "arquivo"]`

Mais variações nas palavras-chave = mais oportunidades de keyword match no Inseridor (Fix B).

## 3. Constantes

```python
_PISO_SLUG_ONLY = 0.30
_FATOR_SLUG_ONLY = 0.65
```

Colocadas no topo do `workflow_inlinks_reversos.py`, próximo de `_MIN_SEMANTIC_SCORE`.

## 4. Mudanças por arquivo

### 4.1 `workflow_inlinks_reversos.py`

**Topo** (após `_MIN_SEMANTIC_SCORE`):

```python
_PISO_SLUG_ONLY = 0.30
_FATOR_SLUG_ONLY = 0.65
```

**Helper novo** (após `_construir_pseudo_alvo`):

```python
def _variacoes_morfologicas(termo: str) -> list[str]:
    ...  # ver §2.3


def _candidata_tem_keyword_alvo(conteudo_md: str, palavras_alvo: list[str]) -> bool:
    if not conteudo_md or not palavras_alvo:
        return False
    for p in palavras_alvo:
        if _contem_termo(conteudo_md, p):
            return True
    return False
```

**`_construir_pseudo_alvo`**: incluir variações morfológicas no texto e nas palavras_chave (§2.3).

**`node_filtrar_similaridade`**: reescrever bloco de filtro:

```python
alvo_modo = estado.get("alvo_modo", "pleno")
threshold = estado.get("threshold_score", 0.6)

if alvo_modo == "slug_only":
    threshold_efetivo = max(threshold * _FATOR_SLUG_ONLY, _PISO_SLUG_ONLY)
    palavras_alvo = estado.get("alvo_resultado", {}).get("pseudo_palavras_chave", [])
    logger.info(
        "%s slug_only: threshold %.2f -> efetivo %.2f (palavras_alvo=%s)",
        _log_prefix(eid), threshold, threshold_efetivo,
        ", ".join(palavras_alvo[:5]),
    )
else:
    threshold_efetivo = threshold
    palavras_alvo = []

viaveis: list[dict] = []
descartadas: list[dict] = []

for c in best_by_url.values():
    score = c["score_semantico"]
    if score >= threshold_efetivo:
        c["motivo_viavel"] = f"cosine {score:.2f} >= threshold {threshold_efetivo:.2f}"
        viaveis.append(c)
    elif alvo_modo == "slug_only" and score >= _PISO_SLUG_ONLY:
        # Override por keyword literal
        if _candidata_tem_keyword_alvo(c.get("conteudo_md", ""), palavras_alvo):
            c["motivo_viavel"] = (
                f"cosine {score:.2f} baixo, mas candidata contem palavras do slug literalmente"
            )
            viaveis.append(c)
        else:
            descartadas.append(c)
    else:
        descartadas.append(c)

viaveis.sort(key=lambda x: x["score_semantico"], reverse=True)
descartadas.sort(key=lambda x: x["score_semantico"], reverse=True)
```

### 4.2 `node_inserir_em_cada` (ajuste mínimo)

Quando uma candidata vira viável via keyword override, ela tem cosine baixo. O Inseridor usa `score_semantico` para escolha de candidatos (mas aqui sempre passa só 1 candidato, então não afeta). Sem mudança real necessária — apenas garantia de que `score_semantico` real é preservado no resultado (não substituído).

Já está correto da SPEC anterior (passa `candidata["score_semantico"]` ao Inseridor).

## 5. Verificação

### 5.1 E2E principal — Mundo Cristão (já conhecido)

Mesma URL alvo `categoria-produto/livros/mulheres/` + 10 satélites.

**Antes** (apenas SPEC slug fallback):
- 5 aplicadas, 5 sem_match (cosines 0.41-0.47 abaixo do threshold 0.50).

**Depois esperado:**
- threshold_efetivo = `max(0.50 × 0.65, 0.30) = 0.325`.
- Todas as 10 candidatas têm cosine ≥ 0.41 > 0.325 → passam direto, **sem precisar de keyword override**.
- Esperado: **8-10 aplicadas + sugestões** (todas viáveis vão ao Inseridor, que aplica ou sugere conforme validação).
- 0-2 sem_match (só se o Inseridor não achar âncora adequada — improvável dado que todas mencionam "mulher").

### 5.2 E2E controle — URL plena (sem regressão)

URL Hashtag python-mais-facil + 4 candidatas Hashtag.

Esperado:
- `alvo_modo=pleno`, threshold = 0.50, sem fator de correção.
- Resultado idêntico aos testes anteriores: 2-3 aplicadas + 1-2 sugestões.
- Sem regressão.

### 5.3 E2E controle — slug inútil

URL `/p/12345` (slug sem termos significativos).

Esperado:
- Cai em `alvo_invalido` (antes do filtro adaptativo), 0 créditos.
- Sem mudança em relação à SPEC anterior.

### 5.4 Validação técnica

- `palavras_chave` do alvo no resultado contém variações morfológicas (`mulher`, `livro`).
- Log do worker contém linha `slug_only: threshold 0.50 -> efetivo 0.32 (palavras_alvo=...)`.
- Para candidatas que passam via override de keyword: `motivo_viavel` mostra "contem palavras do slug literalmente".
- `tipo_recurso="pilar_slug_only"` continua isolado em `conteudos_vetores`.

## 6. Riscos

| Risco | Mitigação |
|---|---|
| Threshold relaxado admite candidatas pouco relacionadas | Defesa em profundidade: Inseridor + validação dura de palavra-chave do destino filtram. Pior caso: vira `sugestao_manual` (não link ruim aplicado). Custo: cobrança aumenta, mas usuário recebe valor (sugestões revisáveis). |
| Keyword override pega match casual (ex: "mulher" mencionada de passagem) | `_contem_termo` faz substring; uma única ocorrência basta. Para o domínio típico de páginas de categoria (livros, produtos), o termo da categoria aparecer no artigo já é forte sinal de relação. Inseridor tem regras adicionais. |
| Variações morfológicas geram palavras inválidas (ex: `mulhere`) | Aceitável — palavras inválidas em pseudo-conteúdo apenas "diluem" o embedding, não criam falsos matches. `_contem_termo` exige substring exato; "mulhere" não bate em texto real. |
| Custo aumenta nas execuções slug_only | Era o ponto — usuário paga porque recebe ≥ 1 link. Antes não recebia nada por uma URL legítima. |
| Fator 0.65 é arbitrário | Calibrado empiricamente para o caso Mundo Cristão (cosines 0.41-0.47 precisam passar com threshold base 0.50 → 0.325). Pode ser tuneado se aparecer falso positivo grave em outro caso. |
| Pseudo enriquecido pode ficar verboso | Tamanho aumenta de ~365 para ~500 chars. Embedding fica mais robusto. Não impacta downstream. |

## 7. Não-objetivos

- **Dicionário de sinônimos PT-BR**: variações morfológicas heurísticas bastam para o caso comum. Para sinônimos reais (mulher ↔ feminino), v2.
- **Threshold totalmente dinâmico baseado em "qualidade" do embedding**: sem benchmark grande, não justifica. Fator fixo 0.65 é defensável.
- **Cross-encoder reranker no filtro**: caro e complexo; o Inseridor já é cross-encoder via LLM dentro de cada candidata viável.
- **Frontend banner explicando threshold reduzido**: melhoria UX, v2.

## 8. Plano de execução

1. Adicionar constantes `_PISO_SLUG_ONLY`, `_FATOR_SLUG_ONLY` no topo.
2. Adicionar helpers `_variacoes_morfologicas`, `_candidata_tem_keyword_alvo`.
3. Atualizar `_construir_pseudo_alvo` para usar variações morfológicas.
4. Reescrever bloco de filtro em `node_filtrar_similaridade`.
5. Restart worker.
6. Invalidar cache do alvo Mundo Cristão (Redis scrape + conteudos_vetores) para forçar regeneração do pseudo-conteúdo com variações.
7. Rodar E2E Mundo Cristão + E2E Hashtag (controle).
8. Validar:
   - Mundo Cristão: 8-10 aplicadas+sugestões.
   - Hashtag: comportamento idêntico ao atual.
9. Verificar SQL: `pilar_slug_only` no banco com pseudo enriquecido (~500 chars).

## 9. Critério de pronto

- E2E Mundo Cristão: **≥ 8** candidatas em status `aplicado` ou `sugestao_manual` (vs. 5 antes).
- Threshold efetivo logado corretamente como 0.325 quando slug_only com threshold base 0.50.
- `palavras_chave` do alvo no resultado inclui variações (`mulher`, `livro`).
- Hashtag E2E (modo pleno) sem regressão: 2-3 aplicadas + 1-2 sugestões, threshold 0.50 inalterado.
- `_candidata_tem_keyword_alvo` ativa só em região cinzenta (cosine entre 0.30 e 0.325 com threshold base 0.50) — confirmar via log.
