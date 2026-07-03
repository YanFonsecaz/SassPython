# SPEC — Distribuir Inlinks: Slug Fallback para URLs de Categoria/Produto

**Status:** ✅ implementado · **Escopo:** `workflow_inlinks_reversos.py` (modificar `node_extrair_alvo` + novos helpers) · **Crédito:** mantém política atual
**Depende de:** [[SPEC_Distribuir_Inlinks_Visibilidade_Protecao_Alvo_Cobranca]] aplicada
**Contexto:** E2E real com URL alvo `mundocristao.com.br/categoria-produto/livros/mulheres/` falhou no curto-circuito porque Trafilatura extraiu só boilerplate (tabela GDPR de cookies). Páginas de categoria WooCommerce / loja / produto são caso de uso legítimo: o usuário quer plantar links internos apontando para a página comercial. Hoje a ferramenta recusa essas URLs e cobra zero — mas isso é frustrante porque o usuário tem **intenção real** e o slug já carrega o sinal semântico necessário.

## 1. Causa-raiz

Trafilatura é otimizado para artigos. Em páginas de categoria/produto extrai:

- Tabelas GDPR de cookies.
- "Showing 1–9 of 18 results" (paginação WooCommerce).
- Título OG ("Arquivo de Mulheres").
- **Nenhum texto redacional sobre o produto/categoria** (essas páginas geralmente listam itens, não descrevem).

O guard `_MIN_ALVO_CHARS=1500 / _MIN_ALVO_PALAVRAS=250` + `_detectar_boilerplate` corretamente identifica o caso e curto-circuita. Mas perde uma oportunidade: o **slug da URL** carrega o sinal de intenção do site:

```
/categoria-produto/livros/mulheres/
                   ^      ^
                   livros mulheres   ← palavras-chave da página
```

Quando o body é pobre, **URL + title + metadata** são o sinal primário em SEO/IR. Esta SPEC adiciona esse caminho.

## 2. Estratégia

### 2.1 Detecção

Quando `node_extrair_alvo` produziria falha (por boilerplate ou < threshold), antes de marcar `falhou=true`, verificar:

1. URL bate em padrão de categoria/produto? (`/categoria/`, `/categoria-produto/`, `/produto/`, `/product-category/`, `/cat/`, `/loja/`, `/shop/`, `/product/`, `/p/`).
2. Slug tem qualidade mínima? (≥ 2 segmentos alfabéticos de ≥ 3 chars, excluindo stopwords e segmentos genéricos como `categoria`, `produto`, `blog`).

Se ambos verdadeiros → caminho **slug fallback**. Caso contrário → falha normal (como hoje).

### 2.2 Derivação de contexto

A partir de slug + título, sintetizar:

- `palavras_chave_sinteticas: list[str]` — termos individuais + bigramas. Ex: `["livros", "mulheres", "livros para mulheres"]`.
- `pseudo_conteudo: str` — texto curto ~100-200 palavras construído a partir das palavras-chave + título. Suficiente para gerar embedding decente.

Esse pseudo-conteúdo passa pelo pipeline normal (`node_enriquecer` → embedding → `node_filtrar_similaridade` → `node_inserir_em_cada`). O Inseridor recebe `palavras_chave` reais e o boost de keyword match herdado do Fix B faz seu trabalho.

### 2.3 Transparência

O resultado marca `alvo_modo: "slug_only"` (ou `"pleno"` no caso normal) para o frontend exibir aviso ao usuário:

> "Análise baseada em slug e título — esta URL não tinha conteúdo redacional. Resultados são mais conservadores."

Cobrança permanece a regra atual (paga só se `n_aplicadas + n_sugestoes ≥ 1`).

## 3. Mudanças

### 3.1 Constantes e helpers (topo de `workflow_inlinks_reversos.py`)

```python
import re
from urllib.parse import urlparse

_CATEGORIA_URL_PATTERNS = (
    "/categoria-produto/",
    "/categoria/",
    "/categorias/",
    "/produto/",
    "/produtos/",
    "/product/",
    "/products/",
    "/product-category/",
    "/cat/",
    "/loja/",
    "/shop/",
    "/colecoes/",
    "/collections/",
    "/p/",
)

_SLUG_SEGMENTOS_GENERICOS = {
    "categoria", "categorias", "produto", "produtos",
    "product", "products", "category", "categories",
    "blog", "post", "posts", "page", "p", "cat",
    "loja", "shop", "store", "tag", "tags",
    "colecao", "colecoes", "collection", "collections",
    "br", "com", "www", "html", "htm", "php",
}

_SLUG_STOPWORDS = {
    "de", "da", "do", "das", "dos", "para", "com",
    "e", "ou", "o", "a", "os", "as", "no", "na",
    "em", "by", "the", "of", "and", "for", "to", "in",
}

_SLUG_NAO_ALFA_RE = re.compile(r"[^a-zA-ZÀ-ſ]")


def _e_url_categoria_produto(url: str) -> bool:
    """True se a URL parece ser categoria, produto ou listagem."""
    if not url:
        return False
    url_lower = url.lower()
    return any(p in url_lower for p in _CATEGORIA_URL_PATTERNS)


def _extrair_termos_slug(url: str) -> list[str]:
    """Extrai termos alfabéticos significativos do slug da URL.
    Filtra genéricos, stopwords, segmentos curtos."""
    if not url:
        return []
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return []

    segmentos = path.split("/")
    termos: list[str] = []
    vistos: set[str] = set()

    for seg in segmentos:
        # divide hífens e underscores: "livros-para-mulheres" → ["livros","para","mulheres"]
        partes = re.split(r"[-_]+", seg)
        for parte in partes:
            limpa = _SLUG_NAO_ALFA_RE.sub("", parte).lower()
            if len(limpa) < 3:
                continue
            if limpa in _SLUG_SEGMENTOS_GENERICOS or limpa in _SLUG_STOPWORDS:
                continue
            if limpa in vistos:
                continue
            vistos.add(limpa)
            termos.append(limpa)

    return termos


def _slug_tem_qualidade(termos: list[str]) -> bool:
    """≥ 2 termos significativos."""
    return len(termos) >= 2


def _construir_pseudo_alvo(url: str, titulo: str, termos_slug: list[str]) -> tuple[str, list[str]]:
    """Gera pseudo-conteúdo + palavras_chave sintéticas a partir de slug + título.

    Retorna (pseudo_md, palavras_chave).
    """
    titulo_limpo = (titulo or "").strip()

    # bigramas adjacentes do slug (ordem preservada)
    bigramas: list[str] = []
    for i in range(len(termos_slug) - 1):
        bigramas.append(f"{termos_slug[i]} {termos_slug[i+1]}")

    # palavras-chave: termos individuais + bigramas + título tokenizado (se útil)
    palavras_chave = list(termos_slug)
    palavras_chave.extend(bigramas)
    if titulo_limpo:
        # adiciona substantivos do título não duplicados
        for t in titulo_limpo.split():
            t_norm = _SLUG_NAO_ALFA_RE.sub("", t).lower()
            if len(t_norm) >= 3 and t_norm not in _SLUG_SEGMENTOS_GENERICOS and t_norm not in _SLUG_STOPWORDS:
                if t_norm not in [p.lower() for p in palavras_chave]:
                    palavras_chave.append(t_norm)

    # pseudo-conteúdo de ~150 palavras: descritivo, focado nos termos
    termos_str = ", ".join(termos_slug)
    bigramas_str = ", ".join(bigramas) if bigramas else termos_slug[0]
    pseudo = (
        f"# {titulo_limpo or termos_slug[0].title()}\n\n"
        f"Esta pagina apresenta conteudo sobre {termos_str}. "
        f"Os principais temas abordados sao {bigramas_str}. "
        f"Aqui voce encontra informacoes, recursos e materiais relacionados a "
        f"{termos_str}. "
        f"O foco da pagina e {' e '.join(termos_slug[:3])}, oferecendo opcoes "
        f"variadas para quem busca {bigramas_str}. "
        f"Categoria: {termos_str}. "
        f"Tema: {termos_str}."
    )
    return pseudo, palavras_chave
```

### 3.2 Modificação em `node_extrair_alvo`

Substituir o bloco que detecta boilerplate/conteúdo insuficiente:

```python
async def node_extrair_alvo(estado: EstadoDistribuir) -> dict:
    from app.agents.inlinks.extrator import extrair_pilar
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    url_alvo = estado.get("url_alvo", "")
    await publish_event(eid, "node_start", "extrair_alvo", f"Extraindo conteudo da URL alvo: {url_alvo}")

    resultado = await extrair_pilar(url_alvo, None)

    alvo_modo = "pleno"
    pseudo_palavras_chave: list[str] = []

    if not resultado.falhou:
        conteudo = resultado.conteudo_md or ""
        n_chars = len(conteudo.strip())
        n_palavras = len(conteudo.split())
        motivo_boilerplate = _detectar_boilerplate(conteudo)
        conteudo_pobre = (
            motivo_boilerplate is not None
            or n_chars < _MIN_ALVO_CHARS
            or n_palavras < _MIN_ALVO_PALAVRAS
        )

        if conteudo_pobre:
            # Tentar slug fallback antes de marcar como falha
            termos_slug = _extrair_termos_slug(resultado.url_canonica or url_alvo)
            url_categoria = _e_url_categoria_produto(resultado.url_canonica or url_alvo)

            if _slug_tem_qualidade(termos_slug) and (url_categoria or n_chars < 200):
                pseudo_md, pseudo_palavras_chave = _construir_pseudo_alvo(
                    resultado.url_canonica or url_alvo,
                    resultado.titulo,
                    termos_slug,
                )
                resultado.conteudo_md = pseudo_md
                resultado.tokens = len(pseudo_md.split())
                # Mantém html_hash original (se houver) — cache de vetores
                # discrimina por html_hash, então pseudo-conteúdo regenerado por
                # execução não conflita com vetores reais cacheados.
                alvo_modo = "slug_only"
                logger.info(
                    "%s alvo_modo=slug_only (termos=%s, motivo=%s)",
                    _log_prefix(eid),
                    ", ".join(termos_slug[:5]),
                    motivo_boilerplate or f"{n_palavras} palavras",
                )
            else:
                # Sem slug útil — falha com mensagem original
                resultado.falhou = True
                if motivo_boilerplate:
                    resultado.erro = (
                        f"URL alvo nao tem conteudo redacional util: {motivo_boilerplate}. "
                        f"Tambem nao foi possivel extrair palavras-chave significativas do slug. "
                        f"Use URL de artigo ou landing page com texto."
                    )
                else:
                    resultado.erro = (
                        f"URL alvo extraida com conteudo insuficiente ({n_palavras} palavras, "
                        f"{n_chars} caracteres). Minimo: {_MIN_ALVO_PALAVRAS} palavras. "
                        f"Slug da URL tambem nao tem palavras-chave significativas."
                    )

    if resultado.falhou:
        await publish_event(eid, "node_complete", "extrair_alvo", f"Falha ao extrair alvo: {resultado.erro}")
    else:
        sufixo = " (modo slug_only)" if alvo_modo == "slug_only" else ""
        await publish_event(eid, "node_complete", "extrair_alvo", f"Alvo extraido: {resultado.tokens} tokens{sufixo}")

    return {
        "alvo_resultado": {
            "url": resultado.url,
            "url_canonica": resultado.url_canonica,
            "conteudo_md": resultado.conteudo_md,
            "titulo": resultado.titulo,
            "tokens": resultado.tokens,
            "html_hash": resultado.html_hash,
            "falhou": resultado.falhou,
            "erro": resultado.erro,
            "alvo_modo": alvo_modo,
            "pseudo_palavras_chave": pseudo_palavras_chave,
        }
    }
```

### 3.3 Propagação de `alvo_modo` para o resultado final

Em `EstadoDistribuir`:

```python
class EstadoDistribuir(TypedDict):
    ...
    alvo_modo: str  # "pleno" | "slug_only"
```

Em `node_persistir`, adicionar a `resultado_final`:

```python
resultado_final = {
    "url_alvo": url_alvo,
    "titulo_alvo": alvo.get("titulo", ""),
    "alvo_modo": alvo.get("alvo_modo", "pleno"),
    "n_candidatas_validas": n_validas,
    ...
}
```

Frontend (`distribuir-inlinks-resultado.tsx`) exibe banner condicional quando `resultado.alvo_modo === "slug_only"`:

> "ℹ️ Esta URL alvo é uma página de categoria/produto sem conteúdo redacional. A análise foi feita a partir do slug e título. Resultados podem ser mais conservadores — revise as sugestões antes de aplicar."

(Frontend é v2 da SPEC — backend primeiro.)

### 3.4 Garantia: pseudo-conteúdo bypassa cache real

O pseudo-conteúdo gerado no slug fallback **não deve poluir o cache `conteudos_vetores`** com chunks fake. Solução: o `html_hash` continua sendo o hash do HTML real da página (cookies + listagem). Se a mesma URL for usada novamente em outra execução com `alvo_modo=slug_only`, o pseudo-conteúdo é regenerado e o embedding também é cold (porque o hash mudou? não — o hash é do HTML original).

**Edge case:** se um usuário no futuro passar a mesma URL em ferramenta diferente (Inlinks Automáticos) que tenta usar o vetor cacheado, vai pegar o vetor do pseudo-conteúdo do slug fallback — não do conteúdo real. Isso pode confundir.

**Mitigação:** marcar os chunks do pseudo-conteúdo com `tipo_recurso="pilar_slug_only"` em vez de `"pilar"`, e na busca de cache em `node_enriquecer` filtrar por `tipo_recurso="pilar"` (ou `"candidata"`). Assim pseudo-vetores ficam isolados e não contaminam o cache normal.

Implementação concreta em `node_enriquecer`:

```python
# No bloco else (cold path):
tipo_recurso_alvo = "pilar_slug_only" if estado.get("alvo_resultado", {}).get("alvo_modo") == "slug_only" else "pilar"
...
vetor = ConteudoVetor(
    ...
    tipo_recurso=tipo_recurso_alvo if item["is_alvo"] else "candidata",
    ...
)
```

E no SELECT de cache:

```python
.where(
    ConteudoVetor.usuario_id == uid,
    ConteudoVetor.url_canonica == url_c,
    ConteudoVetor.html_hash == html_hash,
    ConteudoVetor.ativo == True,
    ConteudoVetor.tipo_recurso.in_(["pilar", "candidata"]),  # não pega pilar_slug_only
)
```

Pseudo-vetores não são recuperáveis via cache normal — são sempre regenerados quando uma nova execução pede slug fallback. Aceitável (volume baixo).

## 4. Verificação

### 4.1 E2E #1 — Mundo Cristão categoria (caso de uso real)

```json
{
  "url_alvo": "https://www.mundocristao.com.br/categoria-produto/livros/mulheres/",
  "candidatas_urls": [10 blog posts sobre mulheres/mães]
}
```

Esperado:
- `alvo_modo: "slug_only"` no resultado.
- Termos slug derivados: `["livros", "mulheres"]`.
- Pseudo-conteúdo gerado, embedding feito, candidatas filtradas pela similaridade real.
- Pelo menos 3-5 das 10 satélites têm "mulheres" ou "livros" no corpo → várias deveriam aplicar.
- Resultado: ≥ 1 `aplicado` ou `sugestao_manual`.
- Cobrança: normal (15 + 10 = 25 créditos) se ≥ 1 aplicada/sugerida; zero se nada útil.

### 4.2 E2E #2 — URL alvo com slug inútil

```json
{
  "url_alvo": "https://exemplo.com/p/12345/",
  ...
}
```

Esperado:
- Slug tem só "12345" (segmento numérico, não passa no filtro alfabético).
- `_slug_tem_qualidade` retorna False.
- Cai no caminho de falha atual: `alvo_invalido=true`, 0 créditos.

### 4.3 E2E #3 — URL alvo com conteúdo pleno

```json
{
  "url_alvo": "https://www.hashtagtreinamentos.com/qual-a-linguagem-de-programacao-mais-facil-python",
  ...
}
```

Esperado:
- Conteúdo passa do guard, `alvo_modo: "pleno"`.
- Comportamento idêntico ao atual — sem regressão.

### 4.4 Validação técnica

- `tipo_recurso="pilar_slug_only"` em `conteudos_vetores` quando E2E #1 roda cold.
- Cache de Inlinks Automáticos não pega esses chunks (filtro `IN ('pilar','candidata')`).
- `resultado_json.alvo_modo` populado nas 3 execuções.

## 5. Riscos

| Risco | Mitigação |
|---|---|
| Pseudo-conteúdo é tão pobre que filtro de similaridade rejeita tudo | Aceitável: se mesmo o slug não bate com candidatas, é porque candidatas não têm tema relacionado. Cobrança zero (Fix 3 da SPEC anterior). |
| Slug com termos enganosos (ex: SKU técnico em slug "amazing-product") leva a links irrelevantes | O Inseridor valida palavras_chave do alvo dentro da candidata (Fix B). Se nenhum termo do slug aparece literalmente nas candidatas, vira `sem_match`. Defesa em profundidade. |
| Pseudo-conteúdo polui análise futura via cache | Mitigado pela coluna `tipo_recurso="pilar_slug_only"` e filtro no SELECT. |
| Inseridor pode propor âncoras muito genéricas baseadas em poucas palavras | Validação `_MIN_ANCORA_TITULO=0.35` continua filtrando. Se âncora não tem relação com termos do slug, vira sugestão manual. |
| Detecção `_e_url_categoria_produto` falsos positivos (ex: blog com slug `/categoria/`) | Combinação com `conteudo_pobre`: só aciona slug fallback se conteúdo é insuficiente E URL parece categoria. Blog com `/categoria/` mas conteúdo rico passa direto. |

## 6. Não-objetivos

- **Permitir markdown_alvo manual no request** (usuário cola descrição): seria adicional ao slug fallback, fora desta SPEC. Resolve cenário diferente (usuário não tem URL com conteúdo, quer passar texto direto).
- **Scrapear schema.org `Product` JSON-LD** para extrair descrição estruturada de páginas de produto: mais robusto que slug mas requer parser JSON-LD. v2.
- **Frontend banner para `alvo_modo=slug_only`**: backend primeiro; frontend pode receber o campo e adicionar banner depois. Não bloqueia a SPEC.
- **Suporte a slug fallback em `candidatas`**: candidatas com conteúdo pobre ainda viram `falhou_extracao` ou `sem_match`. Inverter ferramenta para forçar slug fallback na candidata é outra ferramenta (out of scope).

## 7. Plano de execução

1. **Helpers e constantes** no topo de `workflow_inlinks_reversos.py`:
   - `_CATEGORIA_URL_PATTERNS`, `_SLUG_SEGMENTOS_GENERICOS`, `_SLUG_STOPWORDS`.
   - `_e_url_categoria_produto`, `_extrair_termos_slug`, `_slug_tem_qualidade`, `_construir_pseudo_alvo`.

2. **Modificar `node_extrair_alvo`**: adicionar caminho slug fallback antes de marcar falha. Retornar `alvo_modo` e `pseudo_palavras_chave` no dict.

3. **Atualizar `EstadoDistribuir`**: campo `alvo_modo: str`.

4. **Modificar `node_enriquecer`**:
   - `tipo_recurso` condicional (`"pilar_slug_only"` quando `alvo_modo="slug_only"`).
   - Filtro no SELECT de cache: `tipo_recurso.in_(["pilar", "candidata"])` em vez de aceitar qualquer valor.

5. **Modificar `node_persistir`**: incluir `alvo_modo` em `resultado_final`.

6. **Atualizar `node_persistir_falha_alvo`**: marcar `alvo_modo: "falhou"` ou similar.

7. Restart worker. Rodar E2E #1, #2, #3.

8. Validar com SQL:
   - `tipo_recurso='pilar_slug_only'` aparece em `conteudos_vetores` apenas no E2E #1.
   - `resultado_json.alvo_modo` correto nos 3 casos.
   - Inseridor recebe `palavras_chave` derivadas do slug no E2E #1.

## 8. Critério de pronto

- E2E Mundo Cristão (categoria-produto/livros/mulheres) **NÃO** é mais bloqueado por falha de alvo.
- `alvo_modo="slug_only"` populado em `resultado_json`.
- Pseudo-conteúdo gerado com termos `livros`, `mulheres` e bigramas relevantes.
- ≥ 1 candidata vira `aplicado` ou `sugestao_manual` (mesmo conservador).
- E2E com URL alvo plena (Hashtag) mantém `alvo_modo="pleno"` e comportamento atual sem regressão.
- E2E com URL alvo com slug inútil (números, identificadores) cai no caminho de falha.
- Cache `conteudos_vetores` isola pseudo-vetores via `tipo_recurso="pilar_slug_only"`.
