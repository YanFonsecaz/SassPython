# SPEC — Correções nos Inlinks Automáticos: título de destino e markdown final

**Status:** pendente · **Autor:** análise pós-execução `0ad3cdc7-6fbf-42f9-a23c-40728b3ccca5` · **Escopo:** backend somente · **Migration?** não

## 1. Resumo

Duas correções focadas na ferramenta `inlinks_automaticos`:

- **Fix A:** quando o título de uma página candidata não é extraído pelo `trafilatura`, o scraper cai direto para o domínio. Adicionar fallback HTML (`og:title` → `<title>` → primeiro `<h1>`) antes do hostname.
- **Fix B:** o markdown final do pilar inclui inlinks que o revisor LLM rejeitou. Em `node_revisar`, depois de aplicar os status, reconstruir `pilar_modificado` removendo a marcação `[anchor_text](url_destino)` dos rejeitados (vira texto plano de novo).

Sem mudança de schema, sem mudança de API, sem alteração de UI. Total: 2 arquivos backend + 2 arquivos de teste novos.

## 2. Fix A — Título de destino caindo no domínio

### Sintoma

Em `inlinks_sugeridos.titulo_destino` (e em `resultado_json.inlinks[].titulo_destino`), o campo aparece como `www.hashtagtreinamentos.com` para múltiplas URLs do mesmo domínio. A UI em `frontend/src/components/ferramentas/inlinks-resultado.tsx` mostra esse valor abaixo da âncora, então três inlinks distintos viram "www.hashtagtreinamentos.com".

### Causa raiz

`backend/app/core/scraper.py`, linhas 235-247:

```python
metadata = trafilatura.extract(html, output_format="json", include_links=False, include_images=False)
titulo = ""
if metadata:
    try:
        import json

        meta = json.loads(metadata)
        titulo = meta.get("title", "")
    except Exception:
        pass

resultado.conteudo_md = conteudo.strip()
resultado.titulo = titulo or parsed.hostname or ""
```

Quando `trafilatura` devolve `title=""` (acontece em páginas com schema.org não-padrão ou metadados ruins), o `or parsed.hostname` assume.

### Solução

Adicionar fallback **antes** do hostname, lendo o HTML cru (variável `html` já disponível na mesma função, vinda de linha 213). Tentar nesta ordem:

1. `<meta property="og:title" content="…">` (preferido para SEO)
2. `<title>…</title>`
3. Primeiro `<h1>…</h1>`
4. Por fim, `parsed.hostname`

Implementação em regex (sem nova dependência — `lxml`/`bs4` não são necessárias para essa busca pontual):

```python
# adicionar no topo do arquivo, junto aos outros imports
import re
import html as html_lib
```

Substituir o bloco de extração do título pelo seguinte (manter posicionamento dentro de `scrape_url`, logo antes de atribuir `resultado.titulo`):

```python
metadata = trafilatura.extract(html, output_format="json", include_links=False, include_images=False)
titulo = ""
if metadata:
    try:
        meta = json.loads(metadata)
        titulo = (meta.get("title") or "").strip()
    except Exception:
        pass

if not titulo:
    titulo = _extrair_titulo_html(html)

resultado.conteudo_md = conteudo.strip()
resultado.titulo = titulo or (parsed.hostname or "")
```

E adicionar uma função privada no mesmo arquivo (junto a `_estimate_tokens`):

```python
_TITULO_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TITULO_OG_REV_RE = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
    re.IGNORECASE,
)
_TITULO_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


def _extrair_titulo_html(html: str) -> str:
    """Fallback de título quando trafilatura devolve vazio.

    Tenta og:title → <title> → primeiro <h1>. Decodifica entidades HTML e
    descarta o sufixo " | <site>" / " - <site>" típico se houver.
    """
    candidatos: list[str] = []
    for m in _TITULO_OG_RE.finditer(html):
        candidatos.append(m.group(1))
        break
    if not candidatos:
        for m in _TITULO_OG_REV_RE.finditer(html):
            candidatos.append(m.group(1))
            break
    m = _TITULO_TAG_RE.search(html)
    if m:
        candidatos.append(m.group(1))
    m = _H1_RE.search(html)
    if m:
        candidatos.append(_STRIP_TAGS_RE.sub("", m.group(1)))

    for bruto in candidatos:
        limpo = html_lib.unescape(bruto).strip()
        limpo = re.sub(r"\s+", " ", limpo)
        # remove sufixos comuns " | Marca", " - Marca", " — Marca"
        limpo = re.sub(r"\s+[\|\-–—]\s+[^|\-–—]{1,60}$", "", limpo).strip()
        if 3 <= len(limpo) <= 200:
            return limpo
    return ""
```

### Cache

`scrape_url` cacheia o resultado em Redis por 7 dias (`_SCRAPE_CACHE_TTL` em `scraper.py:34`, chave `scrape:{url_normalizada}`). Páginas já scrapadas continuarão retornando o título errado pelo TTL inteiro.

**Ação obrigatória ao implementar:** mudar a chave de cache para forçar invalidação imediata sem dependência de TTL. Em `scraper.py:158`, alterar:

```python
cache_key = f"scrape:{normalizada}"
```

para:

```python
cache_key = f"scrape:v2:{normalizada}"
```

Isso bypassa caches antigos sem precisar limpar Redis manualmente.

### Testes (Fix A)

Adicionar em `backend/tests/test_scraper.py` (criar se não existir):

```python
from app.core.scraper import _extrair_titulo_html


def test_extrai_og_title():
    html = '<html><head><meta property="og:title" content="Como começar em programação"></head></html>'
    assert _extrair_titulo_html(html) == "Como começar em programação"


def test_extrai_title_tag_e_remove_sufixo_marca():
    html = "<html><head><title>Roadmap de Programação | Hashtag Treinamentos</title></head></html>"
    assert _extrair_titulo_html(html) == "Roadmap de Programação"


def test_fallback_h1_quando_sem_title():
    html = "<html><body><h1>Currículo de Programação</h1></body></html>"
    assert _extrair_titulo_html(html) == "Currículo de Programação"


def test_decodifica_entidades_html():
    html = "<title>Pre&ccedil;o &amp; Valor</title>"
    assert _extrair_titulo_html(html) == "Preço & Valor"


def test_devolve_vazio_sem_pistas():
    assert _extrair_titulo_html("<html><body>nada</body></html>") == ""


def test_descarta_titulos_curtos_demais():
    assert _extrair_titulo_html("<title>OK</title>") == ""
```

## 3. Fix B — Link rejeitado pelo revisor permanece no markdown final

### Sintoma

Execução `0ad3cdc7-6fbf-42f9-a23c-40728b3ccca5`: o inlink "escolher a primeira linguagem de programação" foi marcado `status=rejeitado_revisor` em `inlinks_sugeridos`, mas o markdown salvo em `versoes_artigo` e devolvido em `resultado_json.artigo` ainda contém `[escolher a primeira linguagem de programação](https://www.hashtagtreinamentos.com/melhor-linguagem-de-programacao-iniciantes)`. O revisor virou teatro: rejeita, mas o usuário recebe igual.

### Causa raiz

`backend/app/agents/workflow_inlinks.py`:

- Linhas 317-348 (`node_injetar`): constrói `pilar_modificado` com **todos** os candidatos.
- Linhas 351-368 (`node_revisar`): chama LLM revisor; só ajusta `status` em cada item de `inlinks_revisados`. Não toca `pilar_modificado`.
- Linha 405 (`node_persistir → ferramenta_service.salvar_versao`) salva `pilar_modificado` original.
- Linha 453 (`resultado_final["artigo"]`) idem.

### Solução

Em `node_revisar`, depois de chamar `revisar_inlinks`, reconstruir `pilar_modificado` removendo as marcações markdown dos inlinks com `status != "aplicado"`.

Os offsets armazenados em `InlinkSugerido.offset_chars` referem-se ao **texto pilar original**, não ao `pilar_modificado` — então remover bytes do `pilar_modificado` não invalida nenhum dado persistido.

#### Helper

Adicionar helper privado em `backend/app/agents/inlinks/injector.py` (junto às outras funções utilitárias):

```python
def remover_links_rejeitados(pilar_modificado: str, inlinks_revisados: list[dict]) -> str:
    """Para cada inlink com status != 'aplicado', desfaz a marcação `[ancora](url)`
    no `pilar_modificado` retornando à âncora em texto plano.

    Usa replace literal com count=1 para não afetar âncoras duplicadas que
    pertençam a outro inlink aplicado (improvável dado o `_MIN_DISTANCE_WORDS`,
    mas é a opção segura).
    """
    texto = pilar_modificado
    for il in inlinks_revisados:
        if il.get("status") == "aplicado":
            continue
        ancora = il.get("anchor_text") or ""
        url = il.get("url_destino") or ""
        if not ancora or not url:
            continue
        marca = f"[{ancora}]({url})"
        texto = texto.replace(marca, ancora, 1)
    return texto
```

#### Mudança em `node_revisar`

`backend/app/agents/workflow_inlinks.py`, linhas 351-368, alterar para retornar também o `pilar_modificado` saneado:

```python
async def node_revisar(estado: EstadoInlinks) -> dict:
    from app.agents.inlinks.injector import remover_links_rejeitados
    from app.agents.inlinks.revisor import revisar_inlinks
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "revisar", "Revisando inlinks aplicados...")

    inlinks = estado.get("inlinks_aplicados", [])
    pilar_original = estado.get("pilar_resultado", {}).get("conteudo_md", "")
    pilar_modificado = estado.get("pilar_modificado", "")

    revisados = await revisar_inlinks(pilar_original, pilar_modificado, inlinks, estado["usuario_id"])

    pilar_saneado = remover_links_rejeitados(pilar_modificado, revisados)

    n_aplicados = sum(1 for r in revisados if r.get("status") == "aplicado")
    n_rejeitados = len(revisados) - n_aplicados

    await publish_event(eid, "node_complete", "revisar", f"Revisao: {n_aplicados} aplicados, {n_rejeitados} rejeitados")
    return {"inlinks_revisados": revisados, "pilar_modificado": pilar_saneado}
```

Mudanças:
- Importa `remover_links_rejeitados` no escopo da função (igual aos outros imports tardios do arquivo).
- Calcula `pilar_saneado` após o revisor.
- Devolve `pilar_modificado` no dict de retorno (LangGraph faz merge no `EstadoInlinks`, então `node_persistir` recebe a versão saneada).

Nada mais precisa mudar em `node_persistir`: ele já lê `estado.get("pilar_modificado", "")` (linha 384) e usa em `salvar_versao` (linha 405) e em `resultado_final["artigo"]` (linha 453).

### Testes (Fix B)

Adicionar em `backend/tests/test_inlinks_injector.py` (criar se não existir):

```python
from app.agents.inlinks.injector import remover_links_rejeitados


def test_remove_apenas_rejeitados():
    md = (
        "Comece com [passos iniciais](https://ex.com/a). "
        "Depois [escolher linguagem](https://ex.com/b). "
        "E por fim [um portfolio](https://ex.com/c)."
    )
    inlinks = [
        {"anchor_text": "passos iniciais", "url_destino": "https://ex.com/a", "status": "aplicado"},
        {"anchor_text": "escolher linguagem", "url_destino": "https://ex.com/b", "status": "rejeitado_revisor"},
        {"anchor_text": "um portfolio", "url_destino": "https://ex.com/c", "status": "aplicado"},
    ]
    saneado = remover_links_rejeitados(md, inlinks)
    assert "[passos iniciais](https://ex.com/a)" in saneado
    assert "[escolher linguagem]" not in saneado
    assert "escolher linguagem" in saneado
    assert "[um portfolio](https://ex.com/c)" in saneado


def test_no_op_quando_todos_aplicados():
    md = "Texto com [link](https://ex.com)."
    inlinks = [{"anchor_text": "link", "url_destino": "https://ex.com", "status": "aplicado"}]
    assert remover_links_rejeitados(md, inlinks) == md


def test_ignora_anchor_ou_url_vazios():
    md = "Texto."
    inlinks = [
        {"anchor_text": "", "url_destino": "https://ex.com", "status": "rejeitado_revisor"},
        {"anchor_text": "x", "url_destino": "", "status": "rejeitado_revisor"},
    ]
    assert remover_links_rejeitados(md, inlinks) == md
```

## 4. Verificação ponta a ponta

1. Aplicar as duas mudanças (não há migration nova).
2. Reiniciar `uvicorn` e o worker `arq` (precisam recarregar código).
3. Rodar `pytest backend/tests/test_scraper.py backend/tests/test_inlinks_injector.py`.
4. Submeter via API uma execução nova com a mesma entrada do teste original:
   - Pilar: `https://www.hashtagtreinamentos.com/como-comecar-trabalhar-com-programacao`
   - Candidatas: as 4 URLs do `hashtagtreinamentos.com` usadas anteriormente.
5. Após `status=concluida`, verificar:
   - `SELECT titulo_destino FROM inlinks_sugeridos WHERE execucao_id=…` → títulos reais (não o domínio).
   - `SELECT conteudo_markdown FROM versoes_artigo WHERE execucao_id=…` → não contém `[…](…)` para inlinks com `status != 'aplicado'`.
   - O endpoint `/api/ferramentas/historico/{id}` deve devolver `resultado_json.artigo` consistente com o item acima.

## 5. Fora de escopo (NÃO fazer agora)

- Mutação de texto para inserir inlinks quando a âncora literal não existe (decisão do usuário: aguardar dados do passo 3).
- Instrumentação de candidatos pré-filtro (aguardar passo 3).
- Mudanças no schema, na rota HTTP, na UI. A UI já consome `titulo_destino` e `resultado_json.artigo`, então o conserto vem "de graça" para o frontend.

## 6. Riscos

- **Cache antigo do scraper:** mitigado pela bump da chave `scrape:` → `scrape:v2:`. Custo: re-scraping pago de uma vez para todas as URLs já cacheadas. Aceitável.
- **`replace` de marca de link com âncora duplicada:** o `count=1` garante que só a primeira ocorrência é desfeita. Em pior caso (âncoras idênticas em locais diferentes para inlinks distintos), poderia desfazer a marca errada — mas o `_MIN_DISTANCE_WORDS=100` no injector torna isso muito improvável. Risco aceito.
- **Regex de título:** entradas adversariais podem produzir títulos esquisitos. Mitigado pelo limite `3 <= len(limpo) <= 200` e pela ordem de prioridade (`og:title` é o mais confiável).
