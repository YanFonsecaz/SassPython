# Auditoria SEO Técnico — Onda 1b (Cobertura Completa de Regras) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levar o motor de regras SEOTEC de 31 para **98 itens `fonte: sf` com regra** (cobertura total dos automatizáveis), estendendo o contrato de ingestão com 12 exports novos e o motor com 3 pequenas extensões + 9 funções custom. Sem mudanças de DB, rotas ou workflow.

**Architecture:** Mesma fundação da Onda 1 (mergeada no main): overlay YAML → seed regenerado → loader valida → motor puro avalia. As regras novas são dados (overlay) + funções custom puras; o contrato ganha exports novos com nomes canônicos que o conector (Onda 2) e o guia de upload manual produzirão.

**Tech Stack:** Python 3.12, Pydantic v2, pytest. Arquivos-chave existentes: `backend/app/services/seotec_checklist.py` (schema), `seotec_ingestao.py` (contrato), `seotec_motor.py` + `seotec_motor_custom.py` (motor), `backend/scripts/seed_seotec_checklist.py` + `seed_overlay_seotec.yaml` (seed), `backend/app/data/seotec_checklist/*.yaml` (gerados).

## Global Constraints

- Comandos com prefixo `rtk`; pytest de `backend/` com `.venv/bin/python -m pytest`.
- Status tokens ASCII: `aprovado` · `atencao` · `reprovado` · `na` · `sem_dados`. Sem dados NUNCA vira reprovado.
- Soma dos pesos = 940; 124 itens; 22 categorias (invariantes existentes — não mudam).
- Ao final: **98 itens `fonte: sf`, todos com `regra`** (invariante novo, testado).
- Itens de tipo de schema (18) e outros "presença recomendada": ausência vira `atencao`, nunca `reprovado` nem `na` — o usuário rebaixa manualmente para n/a quando não aplicável (decisão: motor não adivinha aplicabilidade do negócio).
- Sites sem hreflang/AMP: itens dessas famílias viram `na` via `na_se_export_vazio` (planilha faz o mesmo).
- Seed regenerado SEMPRE via `python scripts/seed_seotec_checklist.py` (nunca editar `app/data/seotec_checklist/*.yaml` à mão); `--dry-run` deve conferir após cada mudança de overlay.
- Trabalho na branch `feat/seotec-onda1b` (worktree `.claude/worktrees/seotec-onda1b`, base = main local `9d69d39`). Nunca commitar em main direto; planilha xlsx não vai para o git.
- Código/docstrings em português. Commits conventional em português.

## Contrato: 12 exports novos (referência para todas as tasks)

Formato por linha de cada export (todos com `{"linhas": [...], "total_antes_corte": N}`):

| Export | Colunas por linha | Fonte SF |
|---|---|---|
| `directives` | `address, meta_robots` (string, ex. "noindex,follow") | Directives tab |
| `pagina_404` | `url_testada, status_code, soft_404` (bool) — 1 linha | teste de URL inexistente |
| `orfas` | `address, origem` ("sitemap"/"gsc") | Sitemaps × crawl |
| `sitemap_response_codes` | `address, status_code, sitemap_url` | URLs do sitemap re-checadas |
| `extracoes` | `address, nav_html, viewport, doctype, meta_refresh, lang, iframe_count, flash_count, lorem_ipsum_count` | Custom Search/Extraction |
| `structured_data` | `address, tipos` (lista de strings), `erros` (int), `avisos` (int) | Structured Data tab |
| `hreflang` | `address, problema` — 1 linha por (página, problema); tokens: `url_nao_200, nao_vinculada, retorno_ausente, retorno_inconsistente, retorno_nao_canonico, retorno_noindex, codigo_invalido, entradas_multiplas, auto_referencia_ausente, canonical_ausente, x_default_ausente`; linha `{address, problema: null}` = página com hreflang OK | Hreflang reports |
| `amp` | `address, amp_url, problema` — tokens: `canonical_ausente, alternate_ausente, html_nao_amp, nao_indexavel`; `problema: null` = AMP ok | AMP tab |
| `canonicals` | `address, canonical, quebrado` (bool), `multiplas` (bool) | Canonicals tab |
| `content` | `address, near_duplicate_de` (url ou null), `similaridade` (float) | Content/Duplicates |
| `security` | `address, links_http` (int), `recursos_http` (int) | Security tab |
| `seguranca_site` | `ssl_valido` (bool), `hsts` (bool) — 1 linha resumo | agregado do conector |

Além disso, o export existente `h1` ganha a coluna **opcional** `h2_ocorrencias` (int ou `None` quando o produtor do pacote não coleta H2) — usada só por `hierarquia_headings`.

---

### Task 1: Extensões do schema e do motor (`nao_regex`, `severidade_max`, `parametros`)

**Files:**
- Modify: `backend/app/services/seotec_checklist.py` (RegraFiltro + RegraItem)
- Modify: `backend/app/services/seotec_motor.py` (`_linha_casa`, aplicação de `severidade_max`)
- Test: `backend/tests/unit/test_seotec_motor.py` (append)
- Test: `backend/tests/unit/test_seotec_checklist.py` (append)

**Interfaces:**
- Consumes: schema/motor existentes.
- Produces: op de filtro `nao_regex` (casa quando o valor NÃO casa a regex — inclui None/vazio); `RegraItem.severidade_max: Literal["reprovado","atencao"] = "reprovado"` (quando `atencao`, um resultado que seria `reprovado` vira `atencao`; não afeta `aprovado`/`na`/`sem_dados`); `RegraItem.parametros: dict[str, str] = {}` (repassado às funções custom).

- [ ] **Step 1: Write the failing tests**

Append em `backend/tests/unit/test_seotec_motor.py`:

```python
def test_op_nao_regex():
    regra = RegraItem(export="extracoes", tipo="contagem",
                      filtro=RegraFiltro(campo="viewport", op="nao_regex", valor="width=device-width"))
    pacote = _pacote(extracoes=[
        {"address": "https://a/", "viewport": "width=device-width, initial-scale=1"},
        {"address": "https://b/", "viewport": "width=1024"},
        {"address": "https://c/", "viewport": None},
    ])
    r = avaliar_item(_item(regra, ["address", "viewport"]), pacote)
    assert r.total_afetadas == 2  # b (não casa) e c (vazio)


def test_severidade_max_atencao():
    regra = RegraItem(export="directives", tipo="contagem",
                      filtro=RegraFiltro(campo="meta_robots", op="regex", valor="noindex"),
                      severidade_max="atencao")
    pacote = _pacote(directives=[
        {"address": f"https://a/{i}", "meta_robots": "noindex,follow"} for i in range(50)
    ])
    assert avaliar_item(_item(regra), pacote).status == "atencao"  # nunca reprovado


def test_severidade_max_nao_afeta_aprovado():
    regra = RegraItem(export="directives", tipo="contagem",
                      filtro=RegraFiltro(campo="meta_robots", op="regex", valor="noindex"),
                      severidade_max="atencao")
    pacote = _pacote(directives=[{"address": "https://a/", "meta_robots": "index,follow"}])
    assert avaliar_item(_item(regra), pacote).status == "aprovado"
```

Append em `backend/tests/unit/test_seotec_checklist.py`:

```python
def test_regra_parametros_e_severidade():
    from app.services.seotec_checklist import RegraItem

    r = RegraItem(export="structured_data", tipo="custom", funcao="uso_tipo_schema",
                  parametros={"tipo": "Article"}, severidade_max="atencao")
    assert r.parametros["tipo"] == "Article"
    with pytest.raises(Exception):
        RegraItem(export="x", tipo="contagem", severidade_max="invalida",
                  filtro={"campo": "a", "op": "vazio"})
```

- [ ] **Step 2: Run to verify failure**

Run: `rtk pytest tests/unit/test_seotec_motor.py -k "nao_regex or severidade" -v` — Expected: FAIL (validation error: op/campo desconhecido).

- [ ] **Step 3: Implement**

Em `seotec_checklist.py`: adicionar `"nao_regex"` ao `OpFiltro`; em `RegraItem` adicionar `severidade_max: Literal["reprovado", "atencao"] = "reprovado"` e `parametros: dict[str, str] = Field(default_factory=dict)`; em `RegraFiltro.valor`, incluir `bool` no union (**antes** de `int`, para pydantic não coagir `true`→`1`): `valor: bool | int | float | str | list[int | float] | None = None` — necessário para as regras `igual: true` da Task 8 (`quebrado`/`multiplas`).

Em `seotec_motor.py` `_linha_casa`, novo case:

```python
        case "nao_regex":
            return valor is None or re.search(str(filtro.valor), str(valor)) is None
```

E na montagem do status de contagem/limiar/proporcao (após decidir `status`), aplicar:

```python
    if status == "reprovado" and regra.severidade_max == "atencao":
        status = "atencao"
```

(Aplicar no ponto único onde `status` é decidido para os tipos com filtro; `existencia` e `custom` não passam por `severidade_max` nesta onda.)

- [ ] **Step 4: Run to verify pass**

Run: `rtk pytest tests/unit/test_seotec_motor.py tests/unit/test_seotec_checklist.py -q` — Expected: PASS (todos, incl. os anteriores).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/seotec_checklist.py backend/app/services/seotec_motor.py backend/tests/unit/test_seotec_motor.py backend/tests/unit/test_seotec_checklist.py
rtk git commit -m "feat(seotec): motor ganha op nao_regex, severidade_max e parametros de regra"
```

---

### Task 2: 12 exports novos no contrato de ingestão

**Files:**
- Modify: `backend/app/services/seotec_ingestao.py` (`EXPORTS_CONHECIDOS`)
- Test: `backend/tests/unit/test_seotec_ingestao.py` (append)

**Interfaces:**
- Produces: `EXPORTS_CONHECIDOS` com 21 nomes (9 atuais + os 12 da tabela do contrato acima). Nada mais muda — validação/hash/limites já são genéricos.

- [ ] **Step 1: Write the failing test**

Atualizar o assert exato de `test_export_desconhecido_ignorado` (que fixa o conjunto de 9) para o conjunto de 21:

```python
    assert EXPORTS_CONHECIDOS == {
        "robots", "sitemaps", "response_codes", "internal", "page_titles",
        "meta_description", "h1", "images", "redirects",
        "directives", "pagina_404", "orfas", "sitemap_response_codes",
        "extracoes", "structured_data", "hreflang", "amp",
        "canonicals", "content", "security", "seguranca_site",
    }
```

E novo teste:

```python
def test_exports_novos_aceitos():
    zip_bytes = montar_pacote_zip({
        "hreflang": [{"address": "https://a/", "problema": "retorno_ausente"}],
        "seguranca_site": [{"ssl_valido": True, "hsts": False}],
    })
    r = validar_pacote(zip_bytes, exports_requeridos={"hreflang"})
    assert r.erros == [] and "hreflang" in r.pacote.exports and "seguranca_site" in r.pacote.exports
```

- [ ] **Step 2: Run to verify failure** — `rtk pytest tests/unit/test_seotec_ingestao.py -q` — FAIL no assert do conjunto.

- [ ] **Step 3: Implement** — expandir `EXPORTS_CONHECIDOS` com os 12 nomes.

- [ ] **Step 4: Run to verify pass** — mesmo comando, PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/seotec_ingestao.py backend/tests/unit/test_seotec_ingestao.py
rtk git commit -m "feat(seotec): contrato aceita 12 exports novos (21 canônicos)"
```

---

### Task 3: Customs lote 1 — sitemap, 404, metas no head, hierarquia de headings

**Files:**
- Modify: `backend/app/services/seotec_motor_custom.py`
- Test: `backend/tests/unit/test_seotec_motor_custom.py` (append)

**Interfaces:**
- Produces (assinatura padrão `(item, pacote) -> ResultadoItem`):
  - `sitemap_otimizado` — export `sitemaps`; afetada: linha com `status_code != 200` OU `total_urls > 50000` OU `total_urls == 0`.
  - `pagina_404_adequada` — export `pagina_404`; aprovado se a linha única tem `status_code == 404` e `soft_404` falsy; senão reprovado (evidência = a linha). Export ausente → `sem_dados`.
  - `metas_no_head` — join `page_titles` × `meta_description` por `address`; afetada: página com title vazio **e** meta_description vazia (nenhuma meta no head).
  - `hierarquia_headings` — usa o export `h1`, que ganha a coluna **opcional** `h2_ocorrencias` (ver nota na tabela do contrato). Afetada = página com `h1` vazio e `(h2_ocorrencias or 0) > 0` (usa H2 sem ter H1 — nível pulado). Se nenhuma linha tem `h2_ocorrencias` preenchido (todas `None`) → `sem_dados`.

- [ ] **Step 1: Write the failing tests**

```python
def test_sitemap_otimizado():
    pacote = _pacote(sitemaps=[
        {"sitemap_url": "https://a/s1.xml", "status_code": 200, "total_urls": 100},
        {"sitemap_url": "https://a/s2.xml", "status_code": 404, "total_urls": 0},
    ])
    r = sitemap_otimizado(_item(None, ["sitemap_url", "status_code", "total_urls"]), pacote)
    assert (r.status, r.total_afetadas) == ("reprovado", 1)


def test_sitemap_otimizado_ok():
    pacote = _pacote(sitemaps=[{"sitemap_url": "https://a/s.xml", "status_code": 200, "total_urls": 50}])
    assert sitemap_otimizado(_item(None), pacote).status == "aprovado"


def test_pagina_404_adequada():
    ok = _pacote(pagina_404=[{"url_testada": "https://a/xyz", "status_code": 404, "soft_404": False}])
    soft = _pacote(pagina_404=[{"url_testada": "https://a/xyz", "status_code": 200, "soft_404": True}])
    assert pagina_404_adequada(_item(None), ok).status == "aprovado"
    assert pagina_404_adequada(_item(None), soft).status == "reprovado"
    assert pagina_404_adequada(_item(None), _pacote()).status == "sem_dados"


def test_metas_no_head():
    pacote = _pacote(
        page_titles=[
            {"address": "https://a/", "title": "", "title_length": 0, "ocorrencias": 0},
            {"address": "https://b/", "title": "Ok", "title_length": 2, "ocorrencias": 1},
        ],
        meta_description=[
            {"address": "https://a/", "meta_description": "", "meta_description_length": 0, "ocorrencias": 0},
            {"address": "https://b/", "meta_description": "", "meta_description_length": 0, "ocorrencias": 0},
        ],
    )
    r = metas_no_head(_item(None, ["address"]), pacote)
    assert r.total_afetadas == 1  # só a/ não tem NENHUMA meta


def test_hierarquia_headings():
    pacote = _pacote(h1=[
        {"address": "https://a/", "h1": "", "ocorrencias": 0, "h2_ocorrencias": 3},
        {"address": "https://b/", "h1": "Tem", "ocorrencias": 1, "h2_ocorrencias": 2},
    ])
    assert hierarquia_headings(_item(None, ["address"]), pacote).total_afetadas == 1


def test_hierarquia_headings_sem_coluna():
    pacote = _pacote(h1=[{"address": "https://a/", "h1": "", "ocorrencias": 0}])
    assert hierarquia_headings(_item(None), pacote).status == "sem_dados"
```

- [ ] **Step 2: Run to verify failure** — ImportError nas funções novas.

- [ ] **Step 3: Implement** as 4 funções em `seotec_motor_custom.py` seguindo o padrão existente (`_resultado_lista` com export, `sem_dados` quando export ausente). Para `hierarquia_headings`: `sem_dados` também quando todas as linhas têm `h2_ocorrencias` None (usar `li.get("h2_ocorrencias") is not None`).

- [ ] **Step 4: Run to verify pass** — `rtk pytest tests/unit/test_seotec_motor_custom.py -q`.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/seotec_motor_custom.py backend/tests/unit/test_seotec_motor_custom.py
rtk git commit -m "feat(seotec): customs sitemap/404/metas-no-head/hierarquia-headings"
```

---

### Task 4: Customs lote 2 — schema por tipo, www/trailing/case, nomes de imagem

**Files:**
- Modify: `backend/app/services/seotec_motor_custom.py`
- Test: `backend/tests/unit/test_seotec_motor_custom.py` (append)

**Interfaces:**
- Produces:
  - `uso_tipo_schema` — export `structured_data`, parametrizada: `tipo = item.regra.parametros["tipo"]`. Alguma linha com `tipo in (li.get("tipos") or [])` → `aprovado`; senão → **`atencao`** (nunca reprovado; usuário rebaixa p/ n/a quando não aplicável). Evidência quando atencao: vazia, `total_avaliadas` = linhas.
  - `www_vs_non_www` — export `internal`; extrai host de cada `address`; se existem hosts com e sem prefixo `www.` do MESMO domínio-base → reprovado com amostra das URLs do lado minoritário; senão aprovado.
  - `trailing_slash_misto` — export `internal`; considera paths não-raiz; se existem `address` duplicados a menos da barra final (ex. `/a` e `/a/` ambos presentes) → reprovado com amostra dos pares; senão aprovado.
  - `case_sensitive_urls` — export `internal`; agrupa por `address.lower()`; grupos com >1 variante → reprovado com amostra; senão aprovado.
  - `imagens_nome_generico` — export `images`; afetada: nome de arquivo (última parte do path) casa `(?i)^(img|dsc|image|screenshot|whatsapp[- ]image)[-_ ]?\d|^\d+\.(jpe?g|png|webp|gif)$`; sempre no máximo `atencao` (aplicar como custom: status reprovado→atencao internamente).

- [ ] **Step 1: Write the failing tests**

```python
def test_uso_tipo_schema_presente_e_ausente():
    from app.services.seotec_checklist import RegraItem

    pacote = _pacote(structured_data=[
        {"address": "https://a/", "tipos": ["Article", "WebSite"], "erros": 0, "avisos": 0},
    ])
    item = _item(RegraItem(export="structured_data", tipo="custom", funcao="uso_tipo_schema",
                           parametros={"tipo": "Article"}))
    assert uso_tipo_schema(item, pacote).status == "aprovado"
    item2 = _item(RegraItem(export="structured_data", tipo="custom", funcao="uso_tipo_schema",
                            parametros={"tipo": "Product"}))
    assert uso_tipo_schema(item2, pacote).status == "atencao"


def test_www_vs_non_www():
    misto = _pacote(internal=[
        {"address": "https://www.ex.com/a"}, {"address": "https://ex.com/b"},
    ])
    ok = _pacote(internal=[{"address": "https://www.ex.com/a"}, {"address": "https://www.ex.com/b"}])
    assert www_vs_non_www(_item(None, ["address"]), misto).status == "reprovado"
    assert www_vs_non_www(_item(None), ok).status == "aprovado"


def test_trailing_slash_misto():
    misto = _pacote(internal=[{"address": "https://ex.com/a"}, {"address": "https://ex.com/a/"}])
    ok = _pacote(internal=[{"address": "https://ex.com/a/"}, {"address": "https://ex.com/b/"}])
    assert trailing_slash_misto(_item(None, ["address"]), misto).status == "reprovado"
    assert trailing_slash_misto(_item(None), ok).status == "aprovado"


def test_case_sensitive_urls():
    misto = _pacote(internal=[{"address": "https://ex.com/Pagina"}, {"address": "https://ex.com/pagina"}])
    assert case_sensitive_urls(_item(None, ["address"]), misto).status == "reprovado"


def test_imagens_nome_generico():
    pacote = _pacote(images=[
        {"address": "https://ex.com/img/IMG_1234.jpg", "size_bytes": 1000, "alt_text": "x"},
        {"address": "https://ex.com/img/produto-azul.jpg", "size_bytes": 1000, "alt_text": "x"},
    ])
    r = imagens_nome_generico(_item(None, ["address"]), pacote)
    assert (r.status, r.total_afetadas) == ("atencao", 1)
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement** as 5 funções (usar `urllib.parse.urlsplit` para host/path; domínio-base = host sem prefixo `www.`).

- [ ] **Step 4: Run to verify pass** — `rtk pytest tests/unit/test_seotec_motor_custom.py -q`.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/seotec_motor_custom.py backend/tests/unit/test_seotec_motor_custom.py
rtk git commit -m "feat(seotec): customs schema-por-tipo, www/trailing/case e nome de imagem"
```

---

### Task 5: Overlay parte 1 — 14 regras (acessibilidade, sitemaps, arquitetura, mobile, markup, headings, conteúdo, não-indexável, imagens)

**Files:**
- Modify: `backend/scripts/seed_overlay_seotec.yaml` (adicionar em `regras:`)
- Regenerate: `backend/app/data/seotec_checklist/*.yaml` (via script)
- Test: `backend/tests/unit/test_seotec_checklist_seed.py` (append contagem)

**Interfaces:**
- Consumes: extensões da Task 1, customs das Tasks 3-4, exports da Task 2.
- Produces: 31→45 itens com regra.

- [ ] **Step 1: Failing test** — append:

```python
def test_total_regras_onda_1b_parte1():
    cats = _carregar_tudo()
    com_regra = [i for c in cats for i in c["itens"] if i.get("regra")]
    assert len(com_regra) >= 45
```

Run — FAIL (31).

- [ ] **Step 2: Add to overlay `regras:`** (exatamente):

```yaml
  sitemap-xml-otimizado:
    regra: {export: sitemaps, tipo: custom, funcao: sitemap_otimizado}
    evidencia: {colunas: [sitemap_url, status_code, total_urls]}
  uso-de-tags-de-meta-robots-follow-nofollow-index-noindex:
    regra:
      export: directives
      tipo: contagem
      filtro: {campo: meta_robots, op: regex, valor: noindex}
      severidade_max: atencao
    evidencia: {colunas: [address, meta_robots]}
  configuracao-adequada-para-pagina-de-erro-404:
    regra: {export: pagina_404, tipo: custom, funcao: pagina_404_adequada}
    evidencia: {colunas: [url_testada, status_code, soft_404]}
  pagina-orfa-sem-links-internos-recebidos:
    regra:
      export: orfas
      tipo: contagem
      filtro: {campo: address, op: nao_vazio}
      atencao_max: 10
    evidencia: {colunas: [address, origem]}
  sitemap-xml-da-pagina-com-links-quebrados:
    regra:
      export: sitemap_response_codes
      tipo: contagem
      filtro: {campo: status_code, op: entre, valor: [400, 599]}
    evidencia: {colunas: [address, status_code, sitemap_url]}
  barra-de-navegacao-menu-em-html:
    regra:
      export: extracoes
      tipo: proporcao
      filtro: {campo: nav_html, op: vazio}
      limite_proporcao: 0.5
    evidencia: {colunas: [address]}
  hierarquia-de-urls:
    regra:
      export: internal
      tipo: proporcao
      filtro: {campo: address, op: regex, valor: "^https?://[^/]+(/[^/]+){5,}"}
      limite_proporcao: 0.2
    evidencia: {colunas: [address, crawl_depth]}
  tag-viewport-configurada-corretamente:
    regra:
      export: extracoes
      tipo: contagem
      filtro: {campo: viewport, op: nao_regex, valor: "width=device-width"}
    evidencia: {colunas: [address, viewport]}
  html-doctype-declarada:
    regra:
      export: extracoes
      tipo: contagem
      filtro: {campo: doctype, op: vazio}
    evidencia: {colunas: [address, doctype]}
  nao-uso-de-meta-refresh:
    regra:
      export: extracoes
      tipo: contagem
      filtro: {campo: meta_refresh, op: nao_vazio}
    evidencia: {colunas: [address, meta_refresh]}
  fonte-da-pagina-contem-tags-meta-tags-ex-title-meta-description-no-cabecalho:
    regra: {export: page_titles, tipo: custom, funcao: metas_no_head}
    evidencia: {colunas: [address]}
  hierarquia-de-heading-tags:
    regra: {export: h1, tipo: custom, funcao: hierarquia_headings}
    evidencia: {colunas: [address]}
  presenca-de-lorem-ipsum-no-conteudo:
    regra:
      export: extracoes
      tipo: contagem
      filtro: {campo: lorem_ipsum_count, op: maior, valor: 0}
    evidencia: {colunas: [address, lorem_ipsum_count]}
  nao-uso-de-flash:
    regra:
      export: extracoes
      tipo: contagem
      filtro: {campo: flash_count, op: maior, valor: 0}
    evidencia: {colunas: [address, flash_count]}
  cuidado-no-uso-de-iframe:
    regra:
      export: extracoes
      tipo: contagem
      filtro: {campo: iframe_count, op: maior, valor: 0}
      severidade_max: atencao
    evidencia: {colunas: [address, iframe_count]}
  nome-de-arquivo-com-palavras-chave-especificas:
    regra: {export: images, tipo: custom, funcao: imagens_nome_generico}
    evidencia: {colunas: [address]}
```

(São 16 entradas; 14 contam para categorias desta parte + flash/iframe/lorem já inclusos — total com regra sobe para 47, ≥45 ok.)

- [ ] **Step 3: Regenerate + verify**

```bash
python scripts/seed_seotec_checklist.py && python scripts/seed_seotec_checklist.py --dry-run
rtk pytest tests/unit -k seotec -q
```

Expected: dry-run "OK"; suíte toda verde (loader valida as regras novas contra o schema — falha aqui = overlay errado, corrigir overlay).

- [ ] **Step 4: Commit**

```bash
rtk git add backend/scripts/seed_overlay_seotec.yaml backend/app/data/seotec_checklist/ backend/tests/unit/test_seotec_checklist_seed.py
rtk git commit -m "feat(seotec): 16 regras novas (fundacao html/sitemaps/conteudo)"
```

---

### Task 6: Overlay parte 2 — Dados Estruturados (21 regras)

**Files:**
- Modify: `backend/scripts/seed_overlay_seotec.yaml`
- Regenerate: `backend/app/data/seotec_checklist/*.yaml`
- Test: `backend/tests/unit/test_seotec_motor_custom.py` (append teste de integração)

**Interfaces:** 47→68 itens com regra.

- [ ] **Step 1: Add to overlay** — uso geral, erros, avisos:

```yaml
  uso-de-markup-de-dados-estruturados:
    regra: {export: structured_data, tipo: existencia, campo: tipos}
    evidencia: {colunas: [address, tipos]}
  nao-ha-erros-no-esquema-de-marcacao:
    regra:
      export: structured_data
      tipo: contagem
      filtro: {campo: erros, op: maior, valor: 0}
    evidencia: {colunas: [address, erros]}
  nao-ha-avisos-no-esquema-de-marcacao:
    regra:
      export: structured_data
      tipo: contagem
      filtro: {campo: avisos, op: maior, valor: 0}
      severidade_max: atencao
    evidencia: {colunas: [address, avisos]}
```

E os 18 tipos — todos com o mesmo shape, mudando só `parametros.tipo`:

```yaml
  uso-do-tipo-de-esquema-article:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: Article}}
  uso-do-tipo-de-esquema-blogposting:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: BlogPosting}}
  uso-do-tipo-de-esquema-breadcrumb:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: BreadcrumbList}}
  uso-do-tipo-de-esquema-broadcastevent:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: BroadcastEvent}}
  uso-do-tipo-de-esquema-course:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: Course}}
  uso-do-tipo-de-esquema-event:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: Event}}
  uso-do-tipo-de-esquema-howto:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: HowTo}}
  uso-do-tipo-de-esquema-localbusiness:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: LocalBusiness}}
  uso-do-tipo-de-esquema-logo:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: Organization}}
  uso-do-tipo-de-esquema-newsarticle:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: NewsArticle}}
  uso-do-tipo-de-esquema-organization:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: Organization}}
  uso-do-tipo-de-esquema-product:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: Product}}
  uso-do-tipo-de-esquema-realestate:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: RealEstateListing}}
  uso-do-tipo-de-esquema-recipe:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: Recipe}}
  uso-do-tipo-de-esquema-review:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: Review}}
  uso-do-tipo-de-esquema-softwareapplication:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: SoftwareApplication}}
  uso-do-tipo-de-esquema-videoobject:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: VideoObject}}
  uso-do-tipo-de-esquema-website:
    regra: {export: structured_data, tipo: custom, funcao: uso_tipo_schema, parametros: {tipo: WebSite}}
```

(Sem `evidencia` nos tipos — amostra vazia; nota: `logo` mapeia para Organization por convenção schema.org atual.)

- [ ] **Step 2: Integration test** — append em `test_seotec_motor_custom.py`:

```python
def test_avaliar_pacote_dados_estruturados():
    recarregar_checklist()
    ck = carregar_checklist()
    pacote = _pacote(structured_data=[
        {"address": "https://a/", "tipos": ["Article", "WebSite"], "erros": 2, "avisos": 1},
    ])
    r = avaliar_pacote(ck, pacote, faltantes=[])
    assert r["uso-de-markup-de-dados-estruturados"].status == "aprovado"
    assert r["uso-do-tipo-de-esquema-article"].status == "aprovado"
    assert r["uso-do-tipo-de-esquema-product"].status == "atencao"
    assert r["nao-ha-erros-no-esquema-de-marcacao"].status == "reprovado"
    assert r["nao-ha-avisos-no-esquema-de-marcacao"].status == "atencao"
```

- [ ] **Step 3: Regenerate + verify** — `python scripts/seed_seotec_checklist.py && python scripts/seed_seotec_checklist.py --dry-run && rtk pytest tests/unit -k seotec -q` — PASS.

- [ ] **Step 4: Commit**

```bash
rtk git add backend/scripts/seed_overlay_seotec.yaml backend/app/data/seotec_checklist/ backend/tests/unit/test_seotec_motor_custom.py
rtk git commit -m "feat(seotec): 21 regras de dados estruturados (tipos via parametros)"
```

---

### Task 7: Overlay parte 3 — SEO Internacional (13) + AMP (5)

**Files:** overlay + regen + `test_seotec_motor_custom.py` (append integração).

**Interfaces:** 68→86 itens com regra. Todos com `na_se_export_vazio: true` (site sem hreflang/AMP → `na`).

- [ ] **Step 1: Add to overlay** — hreflang (o item `uso-do-atributo-lang…` usa `extracoes`, os demais o export `hreflang` com filtro por token de `problema`):

```yaml
  uso-do-atributo-lang-html-lang-pt-br-html:
    regra:
      export: extracoes
      tipo: contagem
      filtro: {campo: lang, op: vazio}
    evidencia: {colunas: [address, lang]}
  diretiva-de-idioma-alternativo-hreflang-no-cabecalho-do-codigo-fonte:
    regra: {export: hreflang, tipo: existencia, campo: address, na_se_export_vazio: true}
    evidencia: {colunas: [address]}
  uso-de-urls-hreflang-com-codigo-de-status-200:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: url_nao_200}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  urls-hreflang-nao-vinculadas:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: nao_vinculada}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  links-de-retorno-ausentes:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: retorno_ausente}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  links-de-retorno-de-idioma-e-regiao-inconsistentes:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: retorno_inconsistente}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  links-de-retorno-nao-canonicos:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: retorno_nao_canonico}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  links-de-retorno-noindex:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: retorno_noindex}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  codigos-de-idioma-e-regiao-incorretos:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: codigo_invalido}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  entradas-multiplas:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: entradas_multiplas}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  auto-referencia-ausente:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: auto_referencia_ausente}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  nao-usando-canonico:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: canonical_ausente}
      na_se_export_vazio: true
    evidencia: {colunas: [address, problema]}
  x-default-ausente:
    regra:
      export: hreflang
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: x_default_ausente}
      na_se_export_vazio: true
      severidade_max: atencao
    evidencia: {colunas: [address, problema]}
```

AMP:

```yaml
  uso-de-paginas-amp-em-amp-estrutura-de-url:
    regra: {export: amp, tipo: existencia, campo: amp_url, na_se_export_vazio: true}
    evidencia: {colunas: [address, amp_url]}
  uso-de-rel-canonical-em-pagina-amp-para-pagina-regular:
    regra:
      export: amp
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: canonical_ausente}
      na_se_export_vazio: true
    evidencia: {colunas: [address, amp_url, problema]}
  uso-de-rel-alternate-em-pagina-regular-para-pagina-amp:
    regra:
      export: amp
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: alternate_ausente}
      na_se_export_vazio: true
    evidencia: {colunas: [address, amp_url, problema]}
  html-declarada-como-amp-html:
    regra:
      export: amp
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: html_nao_amp}
      na_se_export_vazio: true
    evidencia: {colunas: [address, amp_url, problema]}
  amp-nao-indexavel:
    regra:
      export: amp
      tipo: contagem
      filtro: {campo: problema, op: igual, valor: nao_indexavel}
      na_se_export_vazio: true
    evidencia: {colunas: [address, amp_url, problema]}
```

- [ ] **Step 2: Integration test** — append:

```python
def test_avaliar_pacote_hreflang_e_amp():
    recarregar_checklist()
    ck = carregar_checklist()
    # site SEM hreflang/AMP: exports presentes e vazios -> na
    vazio = _pacote(hreflang=[], amp=[])
    r = avaliar_pacote(ck, vazio, faltantes=[])
    assert r["links-de-retorno-ausentes"].status == "na"
    assert r["amp-nao-indexavel"].status == "na"
    # site COM problemas
    cheio = _pacote(
        hreflang=[{"address": "https://a/", "problema": "retorno_ausente"},
                  {"address": "https://b/", "problema": None}],
        amp=[{"address": "https://a/", "amp_url": "https://a/amp/", "problema": "html_nao_amp"}],
    )
    r2 = avaliar_pacote(ck, cheio, faltantes=[])
    assert r2["links-de-retorno-ausentes"].status == "reprovado"
    assert r2["diretiva-de-idioma-alternativo-hreflang-no-cabecalho-do-codigo-fonte"].status == "aprovado"
    assert r2["html-declarada-como-amp-html"].status == "reprovado"
    assert r2["uso-de-urls-hreflang-com-codigo-de-status-200"].status == "aprovado"
```

- [ ] **Step 3: Regenerate + verify** — regen + dry-run + `rtk pytest tests/unit -k seotec -q` — PASS.

- [ ] **Step 4: Commit**

```bash
rtk git add backend/scripts/seed_overlay_seotec.yaml backend/app/data/seotec_checklist/ backend/tests/unit/test_seotec_motor_custom.py
rtk git commit -m "feat(seotec): 18 regras internacional/AMP com na para sites sem uso"
```

---

### Task 8: Overlay parte 4 — Conteúdo Duplicado (8) + Segurança (4) → 98/98

**Files:** overlay + regen + testes (seed count final + integração).

**Interfaces:** 86→98 itens com regra. **Invariante final: todo item `fonte: sf` tem `regra`.**

- [ ] **Step 1: Failing test** — substituir `test_total_regras_onda_1b_parte1` por invariante final em `test_seotec_checklist_seed.py`:

```python
def test_todo_item_sf_tem_regra():
    cats = _carregar_tudo()
    sf_sem_regra = [i["slug"] for c in cats for i in c["itens"]
                    if i["fonte"] == "sf" and not i.get("regra")]
    assert sf_sem_regra == [], f"itens sf sem regra: {sf_sem_regra}"
    com_regra = [i for c in cats for i in c["itens"] if i.get("regra")]
    assert len(com_regra) == 98
```

Run — FAIL (12 faltando).

- [ ] **Step 2: Add to overlay**:

```yaml
  www-vs-non-www:
    regra: {export: internal, tipo: custom, funcao: www_vs_non_www}
    evidencia: {colunas: [address]}
  http-vs-https:
    regra:
      export: internal
      tipo: contagem
      filtro: {campo: address, op: regex, valor: "^http://"}
    evidencia: {colunas: [address]}
  nao-uso-de-trailing-slash:
    regra: {export: internal, tipo: custom, funcao: trailing_slash_misto}
    evidencia: {colunas: [address]}
  case-sensitive-habilitado:
    regra: {export: internal, tipo: custom, funcao: case_sensitive_urls}
    evidencia: {colunas: [address]}
  conteudo-duplicado:
    regra:
      export: content
      tipo: contagem
      filtro: {campo: near_duplicate_de, op: nao_vazio}
    evidencia: {colunas: [address, near_duplicate_de, similaridade]}
  uso-de-self-canonical:
    regra:
      export: canonicals
      tipo: contagem
      filtro: {campo: canonical, op: vazio}
      atencao_max: 5
    evidencia: {colunas: [address, canonical]}
  link-canonical-quebrado:
    regra:
      export: canonicals
      tipo: contagem
      filtro: {campo: quebrado, op: igual, valor: true}
    evidencia: {colunas: [address, canonical]}
  varias-urls-canonical:
    regra:
      export: canonicals
      tipo: contagem
      filtro: {campo: multiplas, op: igual, valor: true}
    evidencia: {colunas: [address, canonical]}
  certificado-ssl:
    regra: {export: seguranca_site, tipo: existencia, campo: ssl_valido}
    evidencia: {colunas: [ssl_valido]}
  sem-suporte-hsts:
    regra: {export: seguranca_site, tipo: existencia, campo: hsts}
    evidencia: {colunas: [hsts]}
  paginas-https-levando-a-paginas-http:
    regra:
      export: security
      tipo: contagem
      filtro: {campo: links_http, op: maior, valor: 0}
    evidencia: {colunas: [address, links_http]}
  paginas-https-levando-a-recursos-http:
    regra:
      export: security
      tipo: contagem
      filtro: {campo: recursos_http, op: maior, valor: 0}
    evidencia: {colunas: [address, recursos_http]}
```

- [ ] **Step 3: Integration test** — append em `test_seotec_motor_custom.py`:

```python
def test_avaliar_pacote_duplicado_e_seguranca():
    recarregar_checklist()
    ck = carregar_checklist()
    pacote = _pacote(
        internal=[{"address": "http://ex.com/a"}, {"address": "https://ex.com/a"}],
        content=[{"address": "https://ex.com/a", "near_duplicate_de": "https://ex.com/b", "similaridade": 0.97}],
        canonicals=[{"address": "https://ex.com/a", "canonical": "", "quebrado": False, "multiplas": False}],
        security=[{"address": "https://ex.com/a", "links_http": 2, "recursos_http": 0}],
        seguranca_site=[{"ssl_valido": True, "hsts": False}],
    )
    r = avaliar_pacote(ck, pacote, faltantes=[])
    assert r["http-vs-https"].status == "reprovado"
    assert r["conteudo-duplicado"].status == "reprovado"
    assert r["uso-de-self-canonical"].status == "atencao"  # 1 <= atencao_max
    assert r["certificado-ssl"].status == "aprovado"
    assert r["sem-suporte-hsts"].status == "reprovado"
    assert r["paginas-https-levando-a-paginas-http"].status == "reprovado"
    assert r["paginas-https-levando-a-recursos-http"].status == "aprovado"
```

- [ ] **Step 4: Regenerate + verify all** — regen + dry-run + `rtk pytest tests/unit -k seotec -q` — PASS incl. `test_todo_item_sf_tem_regra` (98/98).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/scripts/seed_overlay_seotec.yaml backend/app/data/seotec_checklist/ backend/tests/unit/test_seotec_checklist_seed.py backend/tests/unit/test_seotec_motor_custom.py
rtk git commit -m "feat(seotec): 12 regras finais (duplicado/segurança) — 98/98 itens sf cobertos"
```

---

### Task 9: E2E estendido + docs

**Files:**
- Modify: `backend/tests/e2e/test_e2e_seotec.py` (`_pacote_fixture` ganha os exports novos; asserts novos)
- Modify: `docs/specs/ferramentas/auditoria-seo-tecnico/SPEC_SEOTEC_Checklist_Motor_Regras.md` e `SPEC_SEOTEC_Conector_Local_SF.md` (Histórico + tabela de exports do contrato = a tabela deste plano) e `README.md` da ferramenta (nota: motor 98/98)

- [ ] **Step 1: Extend fixture** — em `_pacote_fixture`, adicionar aos exports existentes:

```python
        "directives": [{"address": "https://exemplo.com.br/", "meta_robots": "index,follow"}],
        "pagina_404": [{"url_testada": "https://exemplo.com.br/nao-existe-xyz", "status_code": 404, "soft_404": False}],
        "orfas": [],
        "sitemap_response_codes": [{"address": "https://exemplo.com.br/", "status_code": 200, "sitemap_url": "https://exemplo.com.br/sitemap.xml"}],
        "extracoes": [{"address": "https://exemplo.com.br/", "nav_html": "<nav>", "viewport": "width=device-width, initial-scale=1", "doctype": "html", "meta_refresh": None, "lang": "pt-BR", "iframe_count": 0, "flash_count": 0, "lorem_ipsum_count": 0}],
        "structured_data": [{"address": "https://exemplo.com.br/", "tipos": ["Organization", "WebSite"], "erros": 0, "avisos": 0}],
        "hreflang": [],
        "amp": [],
        "canonicals": [{"address": "https://exemplo.com.br/", "canonical": "https://exemplo.com.br/", "quebrado": False, "multiplas": False}],
        "content": [],
        "security": [{"address": "https://exemplo.com.br/", "links_http": 0, "recursos_http": 0}],
        "seguranca_site": [{"ssl_valido": True, "hsts": True}],
```

Asserts novos (dentro do bloco existente):

```python
        assert por_slug["certificado-ssl"].status_antes == "aprovado"
        assert por_slug["links-de-retorno-ausentes"].status_antes == "na"
        assert por_slug["uso-do-tipo-de-esquema-website"].status_antes == "aprovado"
        assert por_slug["uso-do-tipo-de-esquema-product"].status_antes == "atencao"
        auto_sem_dados = [i.item_slug for i in itens if i.modo == "auto" and i.status_antes == "sem_dados"]
        assert auto_sem_dados == [], f"itens auto sem dados com pacote completo: {auto_sem_dados}"
```

Nota: o assert existente `por_slug["conteudo-duplicado"].status_antes == "sem_dados"` DEVE mudar para `"aprovado"` (agora tem regra e o export content está presente e vazio).

- [ ] **Step 2: Run e2e**

```bash
cd backend && DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/sass2_seotec_dev" .venv/bin/python -m pytest tests/e2e/test_e2e_seotec.py -v
```

Expected: PASS. Corrigir causa raiz, nunca enfraquecer asserts.

- [ ] **Step 3: Docs** — nas duas specs: linha no Histórico (`2026-07-19 · Onda 1b: motor completo 98/98 regras; contrato ganha 12 exports (21 canônicos); decisões: tipo-schema ausente→atencao, hreflang/AMP sem uso→na`); em `SPEC_SEOTEC_Conector_Local_SF.md`, substituir a lista de "Exports mínimos da receita v1" por referência à tabela canônica de 21 exports (copiar a tabela do topo deste plano); README da ferramenta: nota curta em "Onda 1" de que o motor cobre 98/98.

- [ ] **Step 4: Full suite + commit**

```bash
rtk pytest tests/unit -q          # 10 falhas pré-existentes CWV permitidas; nada seotec falha
rtk git add backend/tests/e2e/test_e2e_seotec.py docs/specs/
rtk git commit -m "test(seotec): e2e com pacote completo 21 exports + docs Onda 1b"
```

---

## Fora deste plano

- Onda 2 (conector local produz os 21 exports), Onda 3 (IA), Onda 4 (ciclo/UI).
- Follow-ups herdados da Onda 1 (worker `_executar_job`, idempotência de billing, `CUSTOS_TABELA`, object storage) — não tocar aqui.
