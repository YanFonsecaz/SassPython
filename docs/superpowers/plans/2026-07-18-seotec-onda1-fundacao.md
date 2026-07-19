# Auditoria SEO Técnico — Onda 1 (Fundação de Dados) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auditoria de SEO técnico funcional ponta-a-ponta via upload manual de pacote de exports do Screaming Frog — seed dos 124 itens do checklist NPBR, modelos, contrato de ingestão, motor de regras determinístico (31 regras das categorias-núcleo) e health score. Sem IA, sem conector (ondas seguintes).

**Architecture:** Seed YAML versionado (gerado da planilha NPBR por script + overlay manual) → loader pydantic → pacote `.zip` (manifest + exports JSON normalizados) validado → motor de regras puro → score base 940 → persistência em 3 tabelas novas → workflow LangGraph linear rodando no worker ARQ, cobrança reserva→confirma/refund.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, LangGraph, ARQ, pytest. Specs: `docs/specs/ferramentas/auditoria-seo-tecnico/*`.

## Global Constraints

- Comandos bash sempre com prefixo `rtk` (ex.: `rtk pytest …`). Rodar pytest de `backend/`.
- Statuses de item são tokens ASCII: `aprovado` · `atencao` · `reprovado` · `na` · `sem_dados`. Nunca strings com acento no DB/JSON.
- Fases da auditoria: `before` · `implementacao` · `after` · `concluida`. Origens de crawl: `conector` · `upload`. Status de crawl: `recebido` · `processando` · `processado` · `parcial` · `erro`.
- Fontes de item: `sf` · `manual` · `gsc` · `cwv-link`.
- Soma dos pesos do checklist = **940** (invariante testado). 124 itens, 22 categorias.
- Score = Σ pesos com status ∈ {`aprovado`,`na`} ÷ 940 × 100.
- Item sem dados no pacote → `sem_dados`, **nunca** `reprovado`. Item `fonte: sf` sem `regra` (cobertura da Onda 1b) → `sem_dados`.
- Slug da ferramenta: `auditoria_seo_tecnico`. Créditos: before=30, after=15.
- Checklist YAML vive em `backend/app/data/seotec_checklist/` (padrão do repo — a spec citava `app/kb/`, o repo usa `app/data/`; seguir o repo).
- SSE de progresso fica para a Onda 4 (UI); Onda 1 usa polling do status do crawl.
- Código, docstrings e identificadores em português (padrão do repo).
- Nunca commitar na branch `main`. Trabalho na branch `feat/seotec-onda1`.

## Pré-requisito (antes da Task 1)

A branch atual `feat/cwv-auditoria-ui-v2` tem trabalho CWV não relacionado em andamento. Criar branch limpa a partir de `main`:

```bash
rtk git fetch origin
rtk git checkout -b feat/seotec-onda1 origin/main
```

A planilha-fonte `® [TEMPLATE OFICIAL ENTERPRISE - 2026] Auditoria de SEO Técnico _ NPBR.xlsx` está na raiz do repo (untracked — não commitar a planilha). O script de seed a lê por glob. `openpyxl` é dependência só do script (dev): instalar com `pip install openpyxl` no venv do backend se faltar.

---

### Task 1: Seed YAML do checklist (script + overlay + 22 arquivos gerados)

**Files:**
- Create: `backend/scripts/seed_seotec_checklist.py`
- Create: `backend/scripts/seed_overlay_seotec.yaml`
- Create: `backend/app/data/seotec_checklist/*.yaml` (22 arquivos, gerados pelo script)
- Test: `backend/tests/unit/test_seotec_checklist_seed.py`

**Interfaces:**
- Produces: arquivos YAML com schema `{categoria: str, itens: [{slug, nome, peso, prioridade, implementacao, responsavel, impacto, fonte, descricao?, importancia?, regra?, evidencia?}]}` consumidos pelo loader da Task 2. Slugs são estáveis (função `slugify` abaixo é o contrato).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_seotec_checklist_seed.py
"""Invariantes do seed do checklist SEOTEC (SPEC_SEOTEC_Checklist_Motor_Regras)."""
from pathlib import Path

import yaml

SEED_DIR = Path(__file__).parents[2] / "app" / "data" / "seotec_checklist"

FONTES_VALIDAS = {"sf", "manual", "gsc", "cwv-link"}
PRIORIDADES_VALIDAS = {"low", "medium", "high", "very-high"}


def _carregar_tudo() -> list[dict]:
    arquivos = sorted(SEED_DIR.glob("*.yaml"))
    assert len(arquivos) == 22, f"esperado 22 categorias, achou {len(arquivos)}"
    return [yaml.safe_load(a.read_text(encoding="utf-8")) for a in arquivos]


def test_total_itens_e_pesos():
    cats = _carregar_tudo()
    itens = [i for c in cats for i in c["itens"]]
    assert len(itens) == 124
    assert sum(i["peso"] for i in itens) == 940


def test_slugs_unicos_e_campos_obrigatorios():
    cats = _carregar_tudo()
    slugs = []
    for c in cats:
        assert c["categoria"]
        for i in c["itens"]:
            slugs.append(i["slug"])
            assert i["fonte"] in FONTES_VALIDAS
            assert i["prioridade"] in PRIORIDADES_VALIDAS
            assert 1 <= i["peso"] <= 10
    assert len(slugs) == len(set(slugs)), "slugs duplicados"


def test_regras_da_fatia_presentes():
    cats = _carregar_tudo()
    por_slug = {i["slug"]: i for c in cats for i in c["itens"]}
    fatia = [
        "title-tag-ausente-ou-vazia", "title-duplicado",
        "tag-meta-description-ausente-ou-vazia", "tag-h1-ausente-ou-vazia",
        "erros-no-lado-do-cliente-40x", "cadeias-de-redirecionamento",
        "tamanho-do-arquivo-de-imagem-100-kb",
    ]
    for slug in fatia:
        assert por_slug[slug].get("regra"), f"{slug} sem regra"
        assert por_slug[slug]["fonte"] == "sf"


def test_itens_gsc_e_cwv_link():
    cats = _carregar_tudo()
    itens = [i for c in cats for i in c["itens"]]
    assert sum(1 for i in itens if i["fonte"] == "gsc") == 7
    assert sum(1 for i in itens if i["fonte"] == "cwv-link") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/unit/test_seotec_checklist_seed.py -v` (de `backend/`)
Expected: FAIL — `esperado 22 categorias, achou 0`

- [ ] **Step 3: Write the overlay**

`backend/scripts/seed_overlay_seotec.yaml` — fonte de TODOS os 124 slugs + regras dos 31 itens da fatia. Conteúdo completo:

```yaml
# Overlay do seed SEOTEC: fonte por item + regras determinísticas da Onda 1.
# Slug ausente em `fontes` = erro no seed (garante cobertura dos 124).
fontes:
  # Problemas de Accessibilidade/Encontrabilidade
  o-site-esta-sendo-indexado-de-forma-eficiente: manual
  ha-um-robots-txt-configurado-corretamente-no-site: sf
  sitemap-xml-encontrado-em-robots-txt: sf
  sitemap-xml-otimizado: sf
  uso-de-tags-de-meta-robots-follow-nofollow-index-noindex: sf
  configuracao-adequada-para-pagina-de-erro-404: sf
  erros-no-lado-do-cliente-40x: sf
  erros-no-lado-do-servidor-50x: sf
  pagina-orfa-sem-links-internos-recebidos: sf
  analise-de-logfile: manual
  # Sitemaps XML da Página
  site-tem-sitemap-xml: sf
  sitemap-s-xml-da-pagina-estao-listados-no-gsc: gsc
  sitemap-xml-da-pagina-com-links-quebrados: sf
  # Arquitetura
  breadcrumbs-encontrados-e-disponiveis-em-todas-as-paginas: manual
  breadcrumbs-voce-pode-clicar-nas-ultimas-2-3-paginas: manual
  ha-uma-barra-de-navegacao-otimizada: manual
  barra-de-navegacao-menu-em-html: sf
  o-site-tem-rodape-otimizado: manual
  paginas-que-exigem-mais-de-tres-cliques-para-alcancar: sf
  ha-backlink-do-site-dominio-para-o-blog-subdominio-e-vice-versa: manual
  hierarquia-de-urls: sf
  # Problemas da URL
  hifens-usados-como-delimitador-default-em-urls: sf
  usabilidade-geral-da-url-curta-e-facil-de-compartilhar: sf
  otimizacao-geral-da-url-usa-de-palavras-chave-segmentadas: manual
  # Otimização para Mobile
  tag-viewport-configurada-corretamente: sf
  # Problemas com Tags na Página/Markup
  html-doctype-declarada: sf
  nao-uso-de-meta-refresh: sf
  fonte-da-pagina-contem-tags-meta-tags-ex-title-meta-description-no-cabecalho: sf
  # Tag <title>
  title-tag-ausente-ou-vazia: sf
  title-duplicado: sf
  titulo-longo-demais-mais-de-63-caracteres: sf
  titulo-curto-demais-menos-de-30-caracteres: sf
  o-mesmo-que-h1: sf
  multiplas-title-tags: sf
  # Tag <meta description>
  tag-meta-description-ausente-ou-vazia: sf
  tags-meta-description-duplicadas: sf
  meta-description-longa-demais-mais-de-155-caracteres: sf
  meta-description-curta-demais-menos-de-70-caracteres: sf
  multiplas-meta-descriptions: sf
  # Headings da Página (H1-H6)
  tag-h1-ausente-ou-vazia: sf
  tags-h1-duplicadas-em-varias-paginas: sf
  heading-h1-acima-da-dobra: manual
  multiplas-tags-h1-no-codigo: sf
  hierarquia-de-heading-tags: sf
  # Dados Estruturados
  uso-de-markup-de-dados-estruturados: sf
  uso-do-tipo-de-esquema-article: sf
  uso-do-tipo-de-esquema-blogposting: sf
  uso-do-tipo-de-esquema-breadcrumb: sf
  uso-do-tipo-de-esquema-broadcastevent: sf
  uso-do-tipo-de-esquema-course: sf
  uso-do-tipo-de-esquema-event: sf
  uso-do-tipo-de-esquema-howto: sf
  uso-do-tipo-de-esquema-localbusiness: sf
  uso-do-tipo-de-esquema-logo: sf
  uso-do-tipo-de-esquema-newsarticle: sf
  uso-do-tipo-de-esquema-organization: sf
  uso-do-tipo-de-esquema-product: sf
  uso-do-tipo-de-esquema-realestate: sf
  uso-do-tipo-de-esquema-recipe: sf
  uso-do-tipo-de-esquema-review: sf
  uso-do-tipo-de-esquema-softwareapplication: sf
  uso-do-tipo-de-esquema-videoobject: sf
  uso-do-tipo-de-esquema-website: sf
  nao-ha-erros-no-esquema-de-marcacao: sf
  nao-ha-avisos-no-esquema-de-marcacao: sf
  # Conteúdo do Corpo Principal
  presenca-de-lorem-ipsum-no-conteudo: sf
  paginas-com-numero-de-palavras-baixo: sf
  # Conteúdo não indexável
  conteudo-injetado-por-html-nao-js: manual
  nao-uso-de-flash: sf
  cuidado-no-uso-de-iframe: sf
  nao-ha-conteudo-escondido: manual
  # Imagens de SEO
  nome-de-arquivo-com-palavras-chave-especificas: sf
  tamanho-do-arquivo-de-imagem-100-kb: sf
  texto-alt-faltando-revisao-e-otimizado-para-seo: sf
  # SEO Internacional
  uso-do-atributo-lang-html-lang-pt-br-html: sf
  diretiva-de-idioma-alternativo-hreflang-no-cabecalho-do-codigo-fonte: sf
  uso-de-urls-hreflang-com-codigo-de-status-200: sf
  urls-hreflang-nao-vinculadas: sf
  links-de-retorno-ausentes: sf
  links-de-retorno-de-idioma-e-regiao-inconsistentes: sf
  links-de-retorno-nao-canonicos: sf
  links-de-retorno-noindex: sf
  codigos-de-idioma-e-regiao-incorretos: sf
  entradas-multiplas: sf
  auto-referencia-ausente: sf
  nao-usando-canonico: sf
  x-default-ausente: sf
  # Páginas AMP
  uso-de-paginas-amp-em-amp-estrutura-de-url: sf
  uso-de-rel-canonical-em-pagina-amp-para-pagina-regular: sf
  uso-de-rel-alternate-em-pagina-regular-para-pagina-amp: sf
  html-declarada-como-amp-html: sf
  amp-nao-indexavel: sf
  # Potenciais Gatilhos de Conteúdo Duplicado
  www-vs-non-www: sf
  http-vs-https: sf
  nao-uso-de-trailing-slash: sf
  case-sensitive-habilitado: sf
  conteudo-duplicado: sf
  uso-de-self-canonical: sf
  link-canonical-quebrado: sf
  varias-urls-canonical: sf
  # Autoridade
  pagina-com-biografia-do-autor-blog: manual
  implementacao-de-rel-author-blog: manual
  avaliacao-dos-clientes-pagina-de-produto: manual
  # Problemas com Links
  links-quebrados-codigos-de-resposta-4xx-ou-5xx: sf
  # Problemas com Google Search Console
  google-search-console-acoes-manuais: gsc
  google-search-console-pagina-nao-encontrada: gsc
  google-search-console-paginas-bloqueadas-por-robots-txt: gsc
  google-search-console-paginas-indexadas: gsc
  google-search-console-indexacao-de-sitemap: gsc
  google-search-console-estatisticas-de-rastreamento: gsc
  # Problemas de Segurança
  certificado-ssl: sf
  verificacao-de-seguranca-e-scanner-de-malware: manual
  sem-suporte-hsts: sf
  paginas-https-levando-a-paginas-http: sf
  paginas-https-levando-a-recursos-http: sf
  # Propriedade de SEO
  redirecionamentos-302: sf
  cadeias-de-redirecionamento: sf
  loops-de-redirecionamento: sf
  redirecionamentos-quebrados: sf
  # Velocidade da Página
  paginas-lentas: sf
  google-page-speed-insights-abaixo-de-70-desktop-home-page-landing-page: cwv-link
  google-page-speed-insights-abaixo-de-50-mobile-home-page-landing-page: cwv-link
  teste-de-velocidade-abaixo-de-80-usando-gtmetrix-home-page-landing-page: manual
  experiencia-na-pagina: manual

# Regras da fatia Onda 1 (31 itens). Itens fonte=sf ausentes aqui ficam com
# regra null (motor devolve `sem_dados`); cobertura completa é a Onda 1b.
regras:
  ha-um-robots-txt-configurado-corretamente-no-site:
    regra: {export: robots, tipo: existencia, campo: existe}
    evidencia: {colunas: [status_code]}
  sitemap-xml-encontrado-em-robots-txt:
    regra: {export: robots, tipo: existencia, campo: sitemaps_declarados}
    evidencia: {colunas: [sitemaps_declarados]}
  erros-no-lado-do-cliente-40x:
    regra:
      export: response_codes
      tipo: contagem
      filtro: {campo: status_code, op: entre, valor: [400, 499]}
    evidencia: {colunas: [address, status_code]}
  erros-no-lado-do-servidor-50x:
    regra:
      export: response_codes
      tipo: contagem
      filtro: {campo: status_code, op: entre, valor: [500, 599]}
    evidencia: {colunas: [address, status_code]}
  site-tem-sitemap-xml:
    regra: {export: sitemaps, tipo: existencia, campo: total_urls}
    evidencia: {colunas: [sitemap_url, total_urls, status_code]}
  paginas-que-exigem-mais-de-tres-cliques-para-alcancar:
    regra:
      export: internal
      tipo: contagem
      filtro: {campo: crawl_depth, op: maior, valor: 3}
      atencao_max: 10
    evidencia: {colunas: [address, crawl_depth]}
  hifens-usados-como-delimitador-default-em-urls:
    regra:
      export: internal
      tipo: contagem
      filtro: {campo: address, op: regex, valor: "_|%20"}
    evidencia: {colunas: [address]}
  usabilidade-geral-da-url-curta-e-facil-de-compartilhar:
    regra:
      export: internal
      tipo: contagem
      filtro: {campo: address, op: len_maior, valor: 115}
      atencao_max: 5
    evidencia: {colunas: [address]}
  title-tag-ausente-ou-vazia:
    regra:
      export: page_titles
      tipo: contagem
      filtro: {campo: title, op: vazio}
    evidencia: {colunas: [address, title]}
  title-duplicado:
    regra:
      export: page_titles
      tipo: contagem
      filtro: {campo: title, op: duplicado}
    evidencia: {colunas: [address, title]}
  titulo-longo-demais-mais-de-63-caracteres:
    regra:
      export: page_titles
      tipo: limiar
      filtro: {campo: title_length, op: maior, valor: 63}
      atencao_max: 5
    evidencia: {colunas: [address, title, title_length]}
  titulo-curto-demais-menos-de-30-caracteres:
    regra:
      export: page_titles
      tipo: limiar
      filtro: {campo: title_length, op: entre, valor: [1, 29]}
      atencao_max: 5
    evidencia: {colunas: [address, title, title_length]}
  o-mesmo-que-h1:
    regra: {export: page_titles, tipo: custom, funcao: title_igual_h1}
    evidencia: {colunas: [address, title, h1]}
  multiplas-title-tags:
    regra:
      export: page_titles
      tipo: limiar
      filtro: {campo: ocorrencias, op: maior, valor: 1}
    evidencia: {colunas: [address, ocorrencias]}
  tag-meta-description-ausente-ou-vazia:
    regra:
      export: meta_description
      tipo: contagem
      filtro: {campo: meta_description, op: vazio}
      atencao_max: 5
    evidencia: {colunas: [address, meta_description]}
  tags-meta-description-duplicadas:
    regra:
      export: meta_description
      tipo: contagem
      filtro: {campo: meta_description, op: duplicado}
    evidencia: {colunas: [address, meta_description]}
  meta-description-longa-demais-mais-de-155-caracteres:
    regra:
      export: meta_description
      tipo: limiar
      filtro: {campo: meta_description_length, op: maior, valor: 155}
      atencao_max: 5
    evidencia: {colunas: [address, meta_description, meta_description_length]}
  meta-description-curta-demais-menos-de-70-caracteres:
    regra:
      export: meta_description
      tipo: limiar
      filtro: {campo: meta_description_length, op: entre, valor: [1, 69]}
      atencao_max: 5
    evidencia: {colunas: [address, meta_description, meta_description_length]}
  multiplas-meta-descriptions:
    regra:
      export: meta_description
      tipo: limiar
      filtro: {campo: ocorrencias, op: maior, valor: 1}
    evidencia: {colunas: [address, ocorrencias]}
  tag-h1-ausente-ou-vazia:
    regra:
      export: h1
      tipo: contagem
      filtro: {campo: h1, op: vazio}
    evidencia: {colunas: [address, h1]}
  tags-h1-duplicadas-em-varias-paginas:
    regra:
      export: h1
      tipo: contagem
      filtro: {campo: h1, op: duplicado}
      atencao_max: 5
    evidencia: {colunas: [address, h1]}
  multiplas-tags-h1-no-codigo:
    regra:
      export: h1
      tipo: limiar
      filtro: {campo: ocorrencias, op: maior, valor: 1}
    evidencia: {colunas: [address, ocorrencias]}
  paginas-com-numero-de-palavras-baixo:
    regra:
      export: internal
      tipo: limiar
      filtro: {campo: word_count, op: entre, valor: [1, 199]}
      atencao_max: 10
    evidencia: {colunas: [address, word_count]}
  tamanho-do-arquivo-de-imagem-100-kb:
    regra:
      export: images
      tipo: limiar
      filtro: {campo: size_bytes, op: maior, valor: 102400}
      atencao_max: 5
    evidencia: {colunas: [address, size_bytes]}
  texto-alt-faltando-revisao-e-otimizado-para-seo:
    regra:
      export: images
      tipo: contagem
      filtro: {campo: alt_text, op: vazio}
      atencao_max: 10
    evidencia: {colunas: [address, alt_text]}
  links-quebrados-codigos-de-resposta-4xx-ou-5xx:
    regra:
      export: response_codes
      tipo: contagem
      filtro: {campo: status_code, op: entre, valor: [400, 599]}
    evidencia: {colunas: [address, status_code]}
  redirecionamentos-302:
    regra:
      export: redirects
      tipo: contagem
      filtro: {campo: redirect_type, op: igual, valor: 302}
      atencao_max: 5
      na_se_export_vazio: true
    evidencia: {colunas: [address, destino_final, redirect_type]}
  cadeias-de-redirecionamento:
    regra:
      export: redirects
      tipo: custom
      funcao: cadeias_redirecionamento
      na_se_export_vazio: true
    evidencia: {colunas: [address, destino_final, num_hops]}
  loops-de-redirecionamento:
    regra:
      export: redirects
      tipo: custom
      funcao: loops_redirecionamento
      na_se_export_vazio: true
    evidencia: {colunas: [address, destino_final]}
  redirecionamentos-quebrados:
    regra:
      export: redirects
      tipo: contagem
      filtro: {campo: status_final, op: entre, valor: [400, 599]}
      na_se_export_vazio: true
    evidencia: {colunas: [address, destino_final, status_final]}
  paginas-lentas:
    regra:
      export: internal
      tipo: limiar
      filtro: {campo: response_time, op: maior, valor: 1.0}
      atencao_max: 10
    evidencia: {colunas: [address, response_time]}
```

- [ ] **Step 4: Write the seed script**

```python
# backend/scripts/seed_seotec_checklist.py
"""Gera backend/app/data/seotec_checklist/*.yaml a partir da planilha NPBR.

Uso (de backend/): python scripts/seed_seotec_checklist.py [--dry-run]
--dry-run: regenera em memória e compara com os YAMLs commitados (exit 1 se divergir).
Dependência dev: openpyxl (não é dependência de runtime do backend).
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

import yaml

RAIZ_REPO = Path(__file__).parents[2]
DESTINO = Path(__file__).parents[1] / "app" / "data" / "seotec_checklist"
OVERLAY = Path(__file__).parent / "seed_overlay_seotec.yaml"

ARQUIVO_POR_CATEGORIA = {
    "Problemas de Accessibilidade/Encontrabilidade": "acessibilidade",
    "Sitemaps XML da Página": "sitemaps-xml",
    "Arquitetura": "arquitetura",
    "Problemas da URL": "problemas-url",
    "Otimização para Mobile": "mobile",
    "Problemas com Tags na Página/Markup": "tags-markup",
    "Tag <title>": "tag-title",
    "Tag <meta description>": "tag-meta-description",
    "Headings da Página (H1-H6)": "headings",
    "Dados Estruturados": "dados-estruturados",
    "Conteúdo do Corpo Principal": "conteudo-principal",
    "Conteúdo não indexável (ex: uso de JS)": "conteudo-nao-indexavel",
    "Imagens de SEO": "imagens-seo",
    "SEO Internacional": "seo-internacional",
    "Páginas AMP": "paginas-amp",
    "Potenciais Gatilhos de Conteúdo Duplicado": "conteudo-duplicado",
    "Autoridade": "autoridade",
    "Problemas com Links": "problemas-links",
    "Problemas com Google Search Console": "google-search-console",
    "Problemas de Segurança": "seguranca",
    "Propriedade de SEO": "propriedade-seo",
    "Velocidade da Página": "velocidade",
}

PRIORIDADE = {"Low": "low", "Medium": "medium", "High": "high", "Very High": "very-high"}
IMPLEMENTACAO = {"Obrigatória": "obrigatoria", "É bom ter": "bom-ter", "Não é essencial": "nao-essencial"}
RESPONSAVEL = {"Desenvolvedor": "dev", "Time de marketing": "marketing"}


def slugify(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return s.strip("-")


def _achar_planilha() -> Path:
    candidatos = list(RAIZ_REPO.glob("*Auditoria de SEO*NPBR*.xlsx"))
    if not candidatos:
        sys.exit("Planilha NPBR não encontrada na raiz do repo")
    return candidatos[0]


def extrair() -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(_achar_planilha(), data_only=True)
    ws = wb["Checklist"]
    overlay = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    fontes, regras = overlay["fontes"], overlay["regras"]

    categorias: list[dict] = []
    atual: dict | None = None
    for row in ws.iter_rows(min_row=5, max_col=24, values_only=True):
        nome = (row[0] or "").strip() if isinstance(row[0], str) else row[0]
        categoria_x = row[23]
        if not nome:
            continue
        if not categoria_x:  # linha de categoria (coluna X vazia)
            atual = {"categoria": nome, "itens": []}
            categorias.append(atual)
            continue
        if atual is None:
            continue
        slug = slugify(nome)
        if slug not in fontes:
            sys.exit(f"Slug fora do overlay (fontes): {slug}")
        responsaveis = [RESPONSAVEL[p.strip()] for p in str(row[12]).split("/") if p.strip() in RESPONSAVEL]
        item = {
            "slug": slug,
            "nome": nome,
            "peso": int(row[16]),
            "prioridade": PRIORIDADE[str(row[10]).strip()],
            "implementacao": IMPLEMENTACAO[str(row[11]).strip()],
            "responsavel": responsaveis or ["dev"],
            "impacto": {"direto": bool(row[8]), "indireto": bool(row[9])},
            "fonte": fontes[slug],
        }
        if isinstance(row[21], str) and row[21].strip():
            item["descricao"] = row[21].strip()
        if isinstance(row[22], str) and row[22].strip():
            item["importancia"] = row[22].strip()
        if slug in regras:
            item["regra"] = regras[slug]["regra"]
            item["evidencia"] = regras[slug].get("evidencia")
        atual["itens"].append(item)
    return categorias


def render(categorias: list[dict]) -> dict[str, str]:
    saida: dict[str, str] = {}
    for cat in categorias:
        arquivo = ARQUIVO_POR_CATEGORIA[cat["categoria"]]
        saida[f"{arquivo}.yaml"] = yaml.safe_dump(
            cat, allow_unicode=True, sort_keys=False, width=100
        )
    return saida


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    arquivos = render(extrair())
    if args.dry_run:
        divergentes = [
            n for n, conteudo in arquivos.items()
            if not (DESTINO / n).exists() or (DESTINO / n).read_text(encoding="utf-8") != conteudo
        ]
        if divergentes:
            sys.exit(f"Divergência com YAMLs commitados: {divergentes}")
        print("OK: regeneração confere")
        return
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in arquivos.items():
        (DESTINO / nome).write_text(conteudo, encoding="utf-8")
    print(f"{len(arquivos)} arquivos gerados em {DESTINO}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the script and reconcile**

Run (de `backend/`): `python scripts/seed_seotec_checklist.py`

Se o script abortar com `Slug fora do overlay`, o nome real da planilha diverge do previsto: ajustar a chave em `fontes:` do overlay para o slug impresso (o overlay é a parte manual; a planilha é a verdade para nomes). Mesma coisa para `ARQUIVO_POR_CATEGORIA` se algum nome de categoria divergir — usar o nome exato impresso no erro `KeyError`. Repetir até gerar 22 arquivos.

- [ ] **Step 6: Run test to verify it passes**

Run: `rtk pytest tests/unit/test_seotec_checklist_seed.py -v`
Expected: PASS (4 testes)

- [ ] **Step 7: Commit**

```bash
rtk git add backend/scripts/seed_seotec_checklist.py backend/scripts/seed_overlay_seotec.yaml backend/app/data/seotec_checklist/ backend/tests/unit/test_seotec_checklist_seed.py
rtk git commit -m "feat(seotec): seed YAML do checklist NPBR (124 itens, 940 pontos)"
```

---

### Task 2: Loader do checklist (`services/seotec_checklist.py`)

**Files:**
- Create: `backend/app/services/seotec_checklist.py`
- Test: `backend/tests/unit/test_seotec_checklist.py`

**Interfaces:**
- Consumes: YAMLs da Task 1.
- Produces (usado pelas Tasks 5-9):
  - `carregar_checklist() -> ChecklistSeotec` (cacheado)
  - `ChecklistSeotec.itens_por_slug() -> dict[str, ItemChecklist]`
  - `ChecklistSeotec.itens() -> list[ItemChecklist]` (ordem dos YAMLs)
  - `ItemChecklist`: `.slug .nome .peso .prioridade .implementacao .responsavel .impacto .fonte .descricao .importancia .regra .evidencia .categoria`
  - `RegraItem`: `.export .tipo .filtro .campo .funcao .atencao_max .na_se_export_vazio`
  - `RegraFiltro`: `.campo .op .valor`
  - `recarregar_checklist()` limpa o cache (para testes)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_seotec_checklist.py
import pytest

from app.services.seotec_checklist import (
    ChecklistSeotec,
    carregar_checklist,
    recarregar_checklist,
)


@pytest.fixture(autouse=True)
def _limpar_cache():
    recarregar_checklist()
    yield
    recarregar_checklist()


def test_carrega_seed_real():
    ck = carregar_checklist()
    assert isinstance(ck, ChecklistSeotec)
    assert len(ck.itens()) == 124
    assert sum(i.peso for i in ck.itens()) == 940


def test_item_por_slug_com_regra():
    ck = carregar_checklist()
    item = ck.itens_por_slug()["title-tag-ausente-ou-vazia"]
    assert item.fonte == "sf"
    assert item.categoria == "Tag <title>"
    assert item.regra.export == "page_titles"
    assert item.regra.tipo == "contagem"
    assert item.regra.filtro.op == "vazio"


def test_item_sf_sem_regra_permitido():
    ck = carregar_checklist()
    item = ck.itens_por_slug()["conteudo-duplicado"]
    assert item.fonte == "sf"
    assert item.regra is None


def test_yaml_invalido_falha(tmp_path, monkeypatch):
    (tmp_path / "quebrado.yaml").write_text(
        "categoria: X\nitens:\n  - slug: a\n    nome: A\n    peso: 99\n", encoding="utf-8"
    )
    import app.services.seotec_checklist as mod

    monkeypatch.setattr(mod, "CHECKLIST_DIR", tmp_path)
    recarregar_checklist()
    with pytest.raises(Exception):
        carregar_checklist()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk pytest tests/unit/test_seotec_checklist.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.seotec_checklist`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/seotec_checklist.py
"""Loader do checklist SEOTEC (SPEC_SEOTEC_Checklist_Motor_Regras).

Carrega e valida os YAMLs de backend/app/data/seotec_checklist/ no padrão
da KB do CWV (services/cwv_kb.py): pydantic + cache + falha rápida no startup.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

CHECKLIST_DIR = Path(__file__).parent.parent / "data" / "seotec_checklist"

TOTAL_PESOS_ESPERADO = 940

Fonte = Literal["sf", "manual", "gsc", "cwv-link"]
Prioridade = Literal["low", "medium", "high", "very-high"]
OpFiltro = Literal[
    "vazio", "nao_vazio", "igual", "regex", "duplicado",
    "maior", "menor", "entre", "len_maior",
]


class RegraFiltro(BaseModel):
    campo: str
    op: OpFiltro
    valor: int | float | str | list[int | float] | None = None


class RegraItem(BaseModel):
    export: str
    tipo: Literal["contagem", "limiar", "existencia", "proporcao", "custom"]
    filtro: RegraFiltro | None = None
    campo: str | None = None
    funcao: str | None = None
    limite_proporcao: float | None = None
    atencao_max: int = 0
    na_se_export_vazio: bool = False

    @model_validator(mode="after")
    def _consistencia(self) -> "RegraItem":
        if self.tipo in ("contagem", "limiar", "proporcao") and self.filtro is None:
            raise ValueError(f"regra tipo {self.tipo} exige filtro")
        if self.tipo == "existencia" and not self.campo:
            raise ValueError("regra existencia exige campo")
        if self.tipo == "custom" and not self.funcao:
            raise ValueError("regra custom exige funcao")
        return self


class EvidenciaDef(BaseModel):
    colunas: list[str] = Field(default_factory=list)


class ImpactoItem(BaseModel):
    direto: bool = False
    indireto: bool = False
    ia: bool = False


class ItemChecklist(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=3, max_length=140)
    nome: str
    peso: int = Field(ge=1, le=10)
    prioridade: Prioridade
    implementacao: Literal["obrigatoria", "bom-ter", "nao-essencial"]
    responsavel: list[Literal["dev", "marketing"]]
    impacto: ImpactoItem
    fonte: Fonte
    descricao: str | None = None
    importancia: str | None = None
    regra: RegraItem | None = None
    evidencia: EvidenciaDef | None = None
    categoria: str = ""  # preenchido no load


class CategoriaChecklist(BaseModel):
    categoria: str
    itens: list[ItemChecklist]


class ChecklistSeotec(BaseModel):
    categorias: list[CategoriaChecklist]

    @model_validator(mode="after")
    def _invariantes(self) -> "ChecklistSeotec":
        slugs = [i.slug for c in self.categorias for i in c.itens]
        dup = {s for s in slugs if slugs.count(s) > 1}
        if dup:
            raise ValueError(f"Slugs duplicados no checklist: {dup}")
        total = sum(i.peso for c in self.categorias for i in c.itens)
        if total != TOTAL_PESOS_ESPERADO:
            raise ValueError(f"Soma de pesos {total} != {TOTAL_PESOS_ESPERADO}")
        return self

    def itens(self) -> list[ItemChecklist]:
        return [i for c in self.categorias for i in c.itens]

    def itens_por_slug(self) -> dict[str, ItemChecklist]:
        return {i.slug: i for i in self.itens()}


@lru_cache(maxsize=1)
def carregar_checklist() -> ChecklistSeotec:
    categorias = []
    for arquivo in sorted(CHECKLIST_DIR.glob("*.yaml")):
        raw = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
        cat = CategoriaChecklist(**raw)
        for item in cat.itens:
            item.categoria = cat.categoria
        categorias.append(cat)
    if not categorias:
        raise ValueError(f"Nenhum YAML de checklist em {CHECKLIST_DIR}")
    return ChecklistSeotec(categorias=categorias)


def recarregar_checklist() -> None:
    carregar_checklist.cache_clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/test_seotec_checklist.py tests/unit/test_seotec_checklist_seed.py -v`
Expected: PASS. Se `test_carrega_seed_real` falhar por validação, o seed viola o schema — corrigir o overlay/script (Task 1), regenerar, nunca afrouxar o schema.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/seotec_checklist.py backend/tests/unit/test_seotec_checklist.py
rtk git commit -m "feat(seotec): loader pydantic do checklist com invariantes (940/124)"
```

---

### Task 3: Modelos + migração 0029

**Files:**
- Create: `backend/app/models/seo_auditoria.py`
- Create: `backend/app/models/seo_crawl.py`
- Create: `backend/app/models/seo_item_resultado.py`
- Modify: `backend/app/models/__init__.py` (adicionar os 3 imports, seguindo o padrão dos existentes)
- Create: `backend/migrations/versions/0029_seotec_fundacao.py`

**Interfaces:**
- Produces: `SeoAuditoria`, `SeoCrawl`, `SeoItemResultado` (SQLAlchemy) usados nas Tasks 8-10. Campos exatamente como abaixo.

- [ ] **Step 1: Write the models**

```python
# backend/app/models/seo_auditoria.py
"""Modelo: seo_auditoria (SPEC_Ferramenta_Auditoria_SEO_Tecnico §3.1)."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class SeoAuditoria(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "seo_auditoria"
    __table_args__ = (
        CheckConstraint(
            "fase IN ('before','implementacao','after','concluida')",
            name="seo_auditoria_fase_check",
        ),
        Index("ix_seo_auditoria_cliente", "cliente_id", text("criado_em DESC")),
        Index("ix_seo_auditoria_usuario", "usuario_id"),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False,
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False,
    )
    dominio: Mapped[str] = mapped_column(Text, nullable=False)
    fase: Mapped[str] = mapped_column(String(20), nullable=False, server_default="before")
    score_antes: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    score_depois: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    data_inicial: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_conclusao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
```

```python
# backend/app/models/seo_crawl.py
"""Modelo: seo_crawl — 1 linha por ingestão de pacote (conector ou upload)."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class SeoCrawl(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "seo_crawl"
    __table_args__ = (
        CheckConstraint("origem IN ('conector','upload')", name="seo_crawl_origem_check"),
        CheckConstraint("fase_destino IN ('before','after')", name="seo_crawl_fase_check"),
        CheckConstraint(
            "status IN ('recebido','processando','processado','parcial','erro')",
            name="seo_crawl_status_check",
        ),
        Index("ix_seo_crawl_auditoria", "auditoria_id"),
    )

    auditoria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seo_auditoria.id", ondelete="CASCADE"), nullable=False,
    )
    execucao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"),
        nullable=True,
    )
    fase_destino: Mapped[str] = mapped_column(String(10), nullable=False)
    origem: Mapped[str] = mapped_column(String(10), nullable=False)
    sf_versao: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    contadores_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(15), nullable=False, server_default="recebido")
    erro_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
```

```python
# backend/app/models/seo_item_resultado.py
"""Modelo: seo_item_resultado — 1 linha por item do checklist por auditoria.

evidencias_json segue contrato JSONB tipado (padrão SPEC_CWV_Contratos_JSONB_Tipados):
{"total_avaliadas": int, "total_afetadas": int, "amostra": [{...}], "truncada": bool}
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin

STATUS_ITEM = ("aprovado", "atencao", "reprovado", "na", "sem_dados")


class SeoItemResultado(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "seo_item_resultado"
    __table_args__ = (
        UniqueConstraint("auditoria_id", "item_slug", name="uq_seo_item_auditoria_slug"),
        CheckConstraint(
            "status_antes IS NULL OR status_antes IN "
            "('aprovado','atencao','reprovado','na','sem_dados')",
            name="seo_item_status_antes_check",
        ),
        CheckConstraint(
            "status_depois IS NULL OR status_depois IN "
            "('aprovado','atencao','reprovado','na','sem_dados')",
            name="seo_item_status_depois_check",
        ),
        CheckConstraint("modo IN ('auto','manual')", name="seo_item_modo_check"),
        Index("ix_seo_item_auditoria", "auditoria_id"),
    )

    auditoria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seo_auditoria.id", ondelete="CASCADE"), nullable=False,
    )
    item_slug: Mapped[str] = mapped_column(String(140), nullable=False)
    status_antes: Mapped[str | None] = mapped_column(String(15), nullable=True)
    status_depois: Mapped[str | None] = mapped_column(String(15), nullable=True)
    modo: Mapped[str] = mapped_column(String(10), nullable=False, server_default="auto")
    diagnostico: Mapped[str | None] = mapped_column(Text, nullable=True)
    recomendacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidencias_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status_cliente: Mapped[str | None] = mapped_column(Text, nullable=True)
    validacao_seo: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacao_cliente: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacao_seo: Mapped[str | None] = mapped_column(Text, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
```

- [ ] **Step 2: Write the migration**

```python
# backend/migrations/versions/0029_seotec_fundacao.py
"""seo_auditoria + seo_crawl + seo_item_resultado (Onda 1 SEOTEC)."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seo_auditoria",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("cliente_id", UUID(as_uuid=True), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("dominio", sa.Text(), nullable=False),
        sa.Column("fase", sa.String(20), nullable=False, server_default="before"),
        sa.Column("score_antes", sa.Numeric(5, 2), nullable=True),
        sa.Column("score_depois", sa.Numeric(5, 2), nullable=True),
        sa.Column("data_inicial", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_conclusao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "fase IN ('before','implementacao','after','concluida')",
            name="seo_auditoria_fase_check",
        ),
    )
    op.create_index("ix_seo_auditoria_cliente", "seo_auditoria", ["cliente_id", sa.text("criado_em DESC")])
    op.create_index("ix_seo_auditoria_usuario", "seo_auditoria", ["usuario_id"])

    op.create_table(
        "seo_crawl",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("auditoria_id", UUID(as_uuid=True), sa.ForeignKey("seo_auditoria.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execucao_id", UUID(as_uuid=True), sa.ForeignKey("execucoes_ferramentas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fase_destino", sa.String(10), nullable=False),
        sa.Column("origem", sa.String(10), nullable=False),
        sa.Column("sf_versao", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("contadores_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(15), nullable=False, server_default="recebido"),
        sa.Column("erro_msg", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("origem IN ('conector','upload')", name="seo_crawl_origem_check"),
        sa.CheckConstraint("fase_destino IN ('before','after')", name="seo_crawl_fase_check"),
        sa.CheckConstraint(
            "status IN ('recebido','processando','processado','parcial','erro')",
            name="seo_crawl_status_check",
        ),
    )
    op.create_index("ix_seo_crawl_auditoria", "seo_crawl", ["auditoria_id"])

    op.create_table(
        "seo_item_resultado",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("auditoria_id", UUID(as_uuid=True), sa.ForeignKey("seo_auditoria.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_slug", sa.String(140), nullable=False),
        sa.Column("status_antes", sa.String(15), nullable=True),
        sa.Column("status_depois", sa.String(15), nullable=True),
        sa.Column("modo", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("diagnostico", sa.Text(), nullable=True),
        sa.Column("recomendacao", sa.Text(), nullable=True),
        sa.Column("evidencias_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("status_cliente", sa.Text(), nullable=True),
        sa.Column("validacao_seo", sa.Text(), nullable=True),
        sa.Column("observacao_cliente", sa.Text(), nullable=True),
        sa.Column("observacao_seo", sa.Text(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("auditoria_id", "item_slug", name="uq_seo_item_auditoria_slug"),
        sa.CheckConstraint(
            "status_antes IS NULL OR status_antes IN ('aprovado','atencao','reprovado','na','sem_dados')",
            name="seo_item_status_antes_check",
        ),
        sa.CheckConstraint(
            "status_depois IS NULL OR status_depois IN ('aprovado','atencao','reprovado','na','sem_dados')",
            name="seo_item_status_depois_check",
        ),
        sa.CheckConstraint("modo IN ('auto','manual')", name="seo_item_modo_check"),
    )
    op.create_index("ix_seo_item_auditoria", "seo_item_resultado", ["auditoria_id"])


def downgrade() -> None:
    op.drop_table("seo_item_resultado")
    op.drop_table("seo_crawl")
    op.drop_table("seo_auditoria")
```

- [ ] **Step 3: Register models**

Em `backend/app/models/__init__.py`, adicionar (seguindo o formato dos imports existentes):

```python
from app.models.seo_auditoria import SeoAuditoria
from app.models.seo_crawl import SeoCrawl
from app.models.seo_item_resultado import SeoItemResultado
```

- [ ] **Step 4: Apply migration against dev DB**

**DB dedicado desta branch:** o Postgres dev compartilhado tem migrações CWV (0029+ da branch CWV) que esta branch não conhece — `alembic upgrade` contra ele falha. Criar um banco dedicado e apontar a URL para ele em todos os comandos alembic/e2e desta branch:

```bash
psql -h localhost -U postgres -c "CREATE DATABASE sass2_seotec_dev" 2>/dev/null || true
```

Conferir em `backend/app/config.py` o nome da variável de ambiente da URL do banco (ex.: `DATABASE_URL`) e exportá-la apontando para `sass2_seotec_dev` antes de rodar alembic e o e2e (usuário/senha/porta iguais aos do `.env` do backend).

Run (de `backend/`): `rtk alembic upgrade head`
Expected: `Running upgrade 0028 -> 0029`. Depois `rtk alembic downgrade -1 && rtk alembic upgrade head` para validar o downgrade.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/models/seo_auditoria.py backend/app/models/seo_crawl.py backend/app/models/seo_item_resultado.py backend/app/models/__init__.py backend/migrations/versions/0029_seotec_fundacao.py
rtk git commit -m "feat(seotec): modelos seo_auditoria/seo_crawl/seo_item_resultado + migração 0029"
```

---

### Task 4: Contrato de ingestão (`services/seotec_ingestao.py`)

**Files:**
- Create: `backend/app/services/seotec_ingestao.py`
- Create: `backend/tests/unit/helpers_seotec.py`
- Test: `backend/tests/unit/test_seotec_ingestao.py`

**Interfaces:**
- Produces (usado pelas Tasks 5-9 e pelo e2e):
  - `SCHEMA_VERSION = 1`
  - `EXPORTS_CONHECIDOS: set[str]` — nomes canônicos: `robots, sitemaps, response_codes, internal, page_titles, meta_description, h1, images, redirects`
  - `ExportNormalizado(BaseModel)`: `.linhas: list[dict]`, `.total_antes_corte: int`
  - `PacoteIngestao(BaseModel)`: `.schema_version .dominio .sf_versao .gerado_em .exports: dict[str, ExportNormalizado]`
  - `ResultadoValidacao(BaseModel)`: `.pacote: PacoteIngestao | None`, `.faltantes: list[str]`, `.erros: list[str]`, `.parcial: bool` (property: pacote ok mas faltantes não-vazio)
  - `validar_pacote(zip_bytes: bytes, exports_requeridos: set[str]) -> ResultadoValidacao`
  - helper de teste `montar_pacote_zip(exports: dict[str, list[dict]], schema_version: int = 1, corromper_hash: str | None = None, sem_manifest: bool = False) -> bytes`

- [ ] **Step 1: Write the test helper**

```python
# backend/tests/unit/helpers_seotec.py
"""Monta pacotes .zip do contrato de ingestão SEOTEC para testes."""
import hashlib
import io
import json
import zipfile


def montar_pacote_zip(
    exports: dict[str, list[dict]],
    schema_version: int = 1,
    corromper_hash: str | None = None,
    sem_manifest: bool = False,
) -> bytes:
    buf = io.BytesIO()
    manifest: dict = {
        "schema_version": schema_version,
        "conector_versao": "0.0.0-teste",
        "sf_versao": "24.1",
        "dominio": "https://exemplo.com.br",
        "gerado_em": "2026-07-18T12:00:00+00:00",
        "exports": {},
    }
    with zipfile.ZipFile(buf, "w") as z:
        for nome, linhas in exports.items():
            corpo = json.dumps(
                {"linhas": linhas, "total_antes_corte": len(linhas)}, ensure_ascii=False
            ).encode("utf-8")
            digest = hashlib.sha256(corpo).hexdigest()
            if nome == corromper_hash:
                digest = "0" * 64
            manifest["exports"][nome] = {"linhas": len(linhas), "hash": f"sha256:{digest}"}
            z.writestr(f"exports/{nome}.json", corpo)
        if not sem_manifest:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return buf.getvalue()
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/unit/test_seotec_ingestao.py
from app.services.seotec_ingestao import EXPORTS_CONHECIDOS, validar_pacote
from tests.unit.helpers_seotec import montar_pacote_zip

TITLES = [{"address": "https://exemplo.com.br/", "title": "Home", "title_length": 4, "ocorrencias": 1}]


def test_pacote_valido_completo():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "h1": []})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1"})
    assert r.erros == []
    assert r.faltantes == []
    assert not r.parcial
    assert r.pacote.schema_version == 1
    assert r.pacote.dominio == "https://exemplo.com.br"
    assert r.pacote.exports["page_titles"].linhas == TITLES


def test_pacote_incompleto_vira_parcial():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1", "redirects"})
    assert r.erros == []
    assert sorted(r.faltantes) == ["h1", "redirects"]
    assert r.parcial


def test_schema_version_desconhecida_rejeita():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES}, schema_version=99)
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.pacote is None
    assert any("schema_version" in e for e in r.erros)


def test_hash_corrompido_rejeita_export():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "h1": []}, corromper_hash="page_titles")
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1"})
    assert "page_titles" in r.faltantes
    assert any("hash" in e for e in r.erros)


def test_sem_manifest_rejeita():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES}, sem_manifest=True)
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.pacote is None


def test_zip_invalido_rejeita():
    r = validar_pacote(b"nao sou zip", exports_requeridos={"page_titles"})
    assert r.pacote is None


def test_export_desconhecido_ignorado():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "inventado": []})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.erros == []
    assert "inventado" not in r.pacote.exports
    assert EXPORTS_CONHECIDOS  # sanity
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `rtk pytest tests/unit/test_seotec_ingestao.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.seotec_ingestao`

- [ ] **Step 4: Write the implementation**

```python
# backend/app/services/seotec_ingestao.py
"""Validação do pacote de ingestão SEOTEC (SPEC_SEOTEC_Conector_Local_SF §3.3).

Pacote .zip: manifest.json + exports/<nome>.json. Cada export:
{"linhas": [{...}], "total_antes_corte": N}. Hash sha256 do corpo no manifest.
Export ausente/corrompido vira `faltante` (ingestão parcial), nunca erro fatal —
erro fatal é só manifest/zip/schema_version inválidos.
"""
import hashlib
import io
import json
import zipfile

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

EXPORTS_CONHECIDOS: set[str] = {
    "robots", "sitemaps", "response_codes", "internal", "page_titles",
    "meta_description", "h1", "images", "redirects",
}

MAX_LINHAS_POR_EXPORT = 500


class ExportNormalizado(BaseModel):
    linhas: list[dict] = Field(default_factory=list)
    total_antes_corte: int = 0


class PacoteIngestao(BaseModel):
    schema_version: int
    dominio: str
    sf_versao: str | None = None
    gerado_em: str | None = None
    exports: dict[str, ExportNormalizado] = Field(default_factory=dict)


class ResultadoValidacao(BaseModel):
    pacote: PacoteIngestao | None = None
    faltantes: list[str] = Field(default_factory=list)
    erros: list[str] = Field(default_factory=list)

    @property
    def parcial(self) -> bool:
        return self.pacote is not None and bool(self.faltantes)


def validar_pacote(zip_bytes: bytes, exports_requeridos: set[str]) -> ResultadoValidacao:
    r = ResultadoValidacao()
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        r.erros.append("Arquivo não é um zip válido")
        return r

    try:
        manifest = json.loads(z.read("manifest.json"))
    except KeyError:
        r.erros.append("manifest.json ausente no pacote")
        return r
    except json.JSONDecodeError:
        r.erros.append("manifest.json inválido")
        return r

    versao = manifest.get("schema_version")
    if versao != SCHEMA_VERSION:
        r.erros.append(f"schema_version não suportada: {versao} (esperado {SCHEMA_VERSION})")
        return r

    pacote = PacoteIngestao(
        schema_version=versao,
        dominio=str(manifest.get("dominio") or ""),
        sf_versao=manifest.get("sf_versao"),
        gerado_em=manifest.get("gerado_em"),
    )

    declarados = manifest.get("exports") or {}
    for nome, meta in declarados.items():
        if nome not in EXPORTS_CONHECIDOS:
            continue
        caminho = f"exports/{nome}.json"
        try:
            corpo = z.read(caminho)
        except KeyError:
            r.erros.append(f"{nome}: declarado no manifest mas ausente no zip")
            r.faltantes.append(nome)
            continue
        hash_declarado = str(meta.get("hash", "")).removeprefix("sha256:")
        if hashlib.sha256(corpo).hexdigest() != hash_declarado:
            r.erros.append(f"{nome}: hash não confere")
            r.faltantes.append(nome)
            continue
        try:
            dados = json.loads(corpo)
            exp = ExportNormalizado(**dados)
        except (json.JSONDecodeError, ValueError) as exc:
            r.erros.append(f"{nome}: JSON inválido ({exc})")
            r.faltantes.append(nome)
            continue
        exp.linhas = exp.linhas[:MAX_LINHAS_POR_EXPORT]
        pacote.exports[nome] = exp

    for nome in sorted(exports_requeridos):
        if nome not in pacote.exports and nome not in r.faltantes:
            r.faltantes.append(nome)

    r.pacote = pacote
    return r
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `rtk pytest tests/unit/test_seotec_ingestao.py -v`
Expected: PASS (7 testes)

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/services/seotec_ingestao.py backend/tests/unit/helpers_seotec.py backend/tests/unit/test_seotec_ingestao.py
rtk git commit -m "feat(seotec): contrato de ingestão schema_version 1 com validação de hash"
```

---

### Task 5: Motor de regras — tipos `contagem`/`limiar`/`existencia`/`proporcao`

**Files:**
- Create: `backend/app/services/seotec_motor.py`
- Test: `backend/tests/unit/test_seotec_motor.py`

**Interfaces:**
- Consumes: `ItemChecklist`/`RegraItem` (Task 2), `PacoteIngestao`/`ExportNormalizado` (Task 4).
- Produces (usado pelas Tasks 6-9):
  - `ResultadoItem(BaseModel)`: `.status` (token), `.total_avaliadas: int`, `.total_afetadas: int`, `.amostra: list[dict]`, `.truncada: bool`
  - `avaliar_item(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem`
  - `MAX_AMOSTRA = 100`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_seotec_motor.py
from app.services.seotec_checklist import EvidenciaDef, ImpactoItem, ItemChecklist, RegraFiltro, RegraItem
from app.services.seotec_ingestao import ExportNormalizado, PacoteIngestao
from app.services.seotec_motor import avaliar_item


def _item(regra: RegraItem | None, evidencia: list[str] | None = None, fonte: str = "sf") -> ItemChecklist:
    return ItemChecklist(
        slug="item-teste", nome="Item teste", peso=5, prioridade="medium",
        implementacao="obrigatoria", responsavel=["dev"],
        impacto=ImpactoItem(direto=True), fonte=fonte, regra=regra,
        evidencia=EvidenciaDef(colunas=evidencia or []),
    )


def _pacote(**exports: list[dict]) -> PacoteIngestao:
    return PacoteIngestao(
        schema_version=1, dominio="https://exemplo.com.br",
        exports={k: ExportNormalizado(linhas=v, total_antes_corte=len(v)) for k, v in exports.items()},
    )


def test_contagem_vazio_reprova():
    regra = RegraItem(export="page_titles", tipo="contagem",
                      filtro=RegraFiltro(campo="title", op="vazio"))
    pacote = _pacote(page_titles=[
        {"address": "https://a/", "title": ""},
        {"address": "https://b/", "title": "Ok"},
    ])
    r = avaliar_item(_item(regra, ["address", "title"]), pacote)
    assert r.status == "reprovado"
    assert r.total_avaliadas == 2
    assert r.total_afetadas == 1
    assert r.amostra == [{"address": "https://a/", "title": ""}]


def test_contagem_zero_afetadas_aprova():
    regra = RegraItem(export="page_titles", tipo="contagem",
                      filtro=RegraFiltro(campo="title", op="vazio"))
    pacote = _pacote(page_titles=[{"address": "https://a/", "title": "Ok"}])
    assert avaliar_item(_item(regra), pacote).status == "aprovado"


def test_atencao_max():
    regra = RegraItem(export="page_titles", tipo="limiar",
                      filtro=RegraFiltro(campo="title_length", op="maior", valor=63),
                      atencao_max=5)
    pacote = _pacote(page_titles=[
        {"address": "https://a/", "title_length": 90},
        {"address": "https://b/", "title_length": 40},
    ])
    assert avaliar_item(_item(regra), pacote).status == "atencao"


def test_op_entre_e_duplicado():
    regra_entre = RegraItem(export="response_codes", tipo="contagem",
                            filtro=RegraFiltro(campo="status_code", op="entre", valor=[400, 499]))
    pacote = _pacote(response_codes=[
        {"address": "https://a/", "status_code": 404},
        {"address": "https://b/", "status_code": 200},
        {"address": "https://c/", "status_code": 500},
    ])
    r = avaliar_item(_item(regra_entre), pacote)
    assert (r.status, r.total_afetadas) == ("reprovado", 1)

    regra_dup = RegraItem(export="h1", tipo="contagem",
                          filtro=RegraFiltro(campo="h1", op="duplicado"))
    pacote2 = _pacote(h1=[
        {"address": "https://a/", "h1": "Igual"},
        {"address": "https://b/", "h1": "Igual"},
        {"address": "https://c/", "h1": "Diferente"},
        {"address": "https://d/", "h1": ""},
        {"address": "https://e/", "h1": ""},
    ])
    r2 = avaliar_item(_item(regra_dup), pacote2)
    assert r2.total_afetadas == 2  # vazios não contam como duplicados


def test_op_regex_e_len_maior():
    regra_rx = RegraItem(export="internal", tipo="contagem",
                         filtro=RegraFiltro(campo="address", op="regex", valor="_|%20"))
    pacote = _pacote(internal=[
        {"address": "https://a/pagina_ruim"},
        {"address": "https://a/pagina-boa"},
    ])
    assert avaliar_item(_item(regra_rx), pacote).total_afetadas == 1

    regra_len = RegraItem(export="internal", tipo="contagem",
                          filtro=RegraFiltro(campo="address", op="len_maior", valor=20))
    assert avaliar_item(_item(regra_len), pacote).total_afetadas == 1  # só "…pagina_ruim" (21 chars)


def test_existencia():
    regra = RegraItem(export="robots", tipo="existencia", campo="existe")
    assert avaliar_item(_item(regra), _pacote(robots=[{"existe": True}])).status == "aprovado"
    assert avaliar_item(_item(regra), _pacote(robots=[{"existe": False}])).status == "reprovado"
    regra_lista = RegraItem(export="robots", tipo="existencia", campo="sitemaps_declarados")
    assert avaliar_item(_item(regra_lista), _pacote(robots=[{"sitemaps_declarados": []}])).status == "reprovado"


def test_proporcao():
    regra = RegraItem(export="internal", tipo="proporcao",
                      filtro=RegraFiltro(campo="address", op="regex", valor="/$"),
                      limite_proporcao=0.2)
    pacote = _pacote(internal=[
        {"address": "https://a/x/"},
        {"address": "https://a/y"},
        {"address": "https://a/z"},
    ])
    # 1/3 = 33% > 20% => reprovado
    assert avaliar_item(_item(regra), pacote).status == "reprovado"


def test_export_ausente_sem_dados():
    regra = RegraItem(export="page_titles", tipo="contagem",
                      filtro=RegraFiltro(campo="title", op="vazio"))
    assert avaliar_item(_item(regra), _pacote()).status == "sem_dados"


def test_item_sf_sem_regra_sem_dados():
    assert avaliar_item(_item(None), _pacote()).status == "sem_dados"


def test_na_se_export_vazio():
    regra = RegraItem(export="redirects", tipo="contagem",
                      filtro=RegraFiltro(campo="redirect_type", op="igual", valor=302),
                      na_se_export_vazio=True)
    assert avaliar_item(_item(regra), _pacote(redirects=[])).status == "na"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/test_seotec_motor.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.seotec_motor`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/seotec_motor.py
"""Motor de regras determinístico SEOTEC (SPEC_SEOTEC_Checklist_Motor_Regras §3.2).

Funções puras: (definição do item, pacote) -> ResultadoItem. Zero LLM, zero IO.
"""
import re
from collections import Counter

from pydantic import BaseModel, Field

from app.services.seotec_checklist import ItemChecklist, RegraFiltro
from app.services.seotec_ingestao import PacoteIngestao

MAX_AMOSTRA = 100


class ResultadoItem(BaseModel):
    status: str
    total_avaliadas: int = 0
    total_afetadas: int = 0
    amostra: list[dict] = Field(default_factory=list)
    truncada: bool = False


def _linha_casa(linha: dict, filtro: RegraFiltro) -> bool:
    valor = linha.get(filtro.campo)
    match filtro.op:
        case "vazio":
            return valor is None or (isinstance(valor, str) and not valor.strip())
        case "nao_vazio":
            return not _linha_casa(linha, RegraFiltro(campo=filtro.campo, op="vazio"))
        case "igual":
            return valor == filtro.valor or str(valor) == str(filtro.valor)
        case "regex":
            return valor is not None and re.search(str(filtro.valor), str(valor)) is not None
        case "maior":
            return isinstance(valor, (int, float)) and valor > filtro.valor
        case "menor":
            return isinstance(valor, (int, float)) and valor < filtro.valor
        case "entre":
            lo, hi = filtro.valor
            return isinstance(valor, (int, float)) and lo <= valor <= hi
        case "len_maior":
            return valor is not None and len(str(valor)) > filtro.valor
        case "duplicado":
            return False  # tratado em _filtrar (precisa do conjunto)
    return False


def _filtrar(linhas: list[dict], filtro: RegraFiltro) -> list[dict]:
    if filtro.op == "duplicado":
        valores = Counter(
            str(li.get(filtro.campo)).strip()
            for li in linhas
            if li.get(filtro.campo) is not None and str(li.get(filtro.campo)).strip()
        )
        repetidos = {v for v, n in valores.items() if n > 1}
        return [li for li in linhas if str(li.get(filtro.campo)).strip() in repetidos]
    return [li for li in linhas if _linha_casa(li, filtro)]


def _montar_amostra(afetadas: list[dict], colunas: list[str]) -> list[dict]:
    corte = afetadas[:MAX_AMOSTRA]
    if not colunas:
        return corte
    return [{c: li.get(c) for c in colunas} for li in corte]


def avaliar_item(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    regra = item.regra
    if regra is None:
        return ResultadoItem(status="sem_dados")
    export = pacote.exports.get(regra.export)
    if export is None:
        return ResultadoItem(status="sem_dados")

    linhas = export.linhas
    if not linhas and regra.na_se_export_vazio:
        return ResultadoItem(status="na", total_avaliadas=export.total_antes_corte)

    colunas = item.evidencia.colunas if item.evidencia else []

    if regra.tipo == "existencia":
        ok = any(li.get(regra.campo) for li in linhas)
        return ResultadoItem(
            status="aprovado" if ok else "reprovado",
            total_avaliadas=len(linhas),
            total_afetadas=0 if ok else len(linhas),
            amostra=[] if ok else _montar_amostra(linhas, colunas),
        )

    if regra.tipo == "custom":
        from app.services import seotec_motor_custom

        fn = getattr(seotec_motor_custom, regra.funcao)
        return fn(item, pacote)

    afetadas = _filtrar(linhas, regra.filtro)
    n = len(afetadas)
    if regra.tipo == "proporcao":
        proporcao = n / len(linhas) if linhas else 0.0
        limite = regra.limite_proporcao or 0.0
        status = "aprovado" if proporcao <= limite else "reprovado"
    elif n == 0:
        status = "aprovado"
    elif n <= regra.atencao_max:
        status = "atencao"
    else:
        status = "reprovado"

    return ResultadoItem(
        status=status,
        total_avaliadas=export.total_antes_corte or len(linhas),
        total_afetadas=n,
        amostra=_montar_amostra(afetadas, colunas),
        truncada=len(afetadas) > MAX_AMOSTRA,
    )
```

Nota: o import de `seotec_motor_custom` só é exercitado na Task 6; nenhum teste desta task usa `tipo=custom`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/test_seotec_motor.py -v`
Expected: PASS (10 testes)

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/seotec_motor.py backend/tests/unit/test_seotec_motor.py
rtk git commit -m "feat(seotec): motor de regras (contagem/limiar/existencia/proporcao)"
```

---

### Task 6: Regras custom + avaliação do pacote inteiro

**Files:**
- Create: `backend/app/services/seotec_motor_custom.py`
- Modify: `backend/app/services/seotec_motor.py` (adicionar `avaliar_pacote` ao final)
- Test: `backend/tests/unit/test_seotec_motor_custom.py`

**Interfaces:**
- Produces:
  - `seotec_motor_custom.cadeias_redirecionamento(item, pacote) -> ResultadoItem`
  - `seotec_motor_custom.loops_redirecionamento(item, pacote) -> ResultadoItem`
  - `seotec_motor_custom.title_igual_h1(item, pacote) -> ResultadoItem`
  - `seotec_motor.avaliar_pacote(checklist: ChecklistSeotec, pacote: PacoteIngestao, faltantes: list[str]) -> dict[str, ResultadoItem]` — só itens `fonte == "sf"`; item cujo `regra.export` está em `faltantes` → `sem_dados`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_seotec_motor_custom.py
from app.services.seotec_checklist import carregar_checklist, recarregar_checklist
from app.services.seotec_ingestao import ExportNormalizado, PacoteIngestao
from app.services.seotec_motor import avaliar_pacote
from app.services.seotec_motor_custom import (
    cadeias_redirecionamento,
    loops_redirecionamento,
    title_igual_h1,
)
from tests.unit.test_seotec_motor import _item, _pacote  # reusa builders


def test_cadeias():
    pacote = _pacote(redirects=[
        {"address": "https://a/", "destino_final": "https://c/", "num_hops": 3, "loop": False},
        {"address": "https://b/", "destino_final": "https://d/", "num_hops": 1, "loop": False},
    ])
    r = cadeias_redirecionamento(_item(None, ["address", "destino_final", "num_hops"]), pacote)
    assert r.status == "reprovado"
    assert r.total_afetadas == 1
    assert r.amostra[0]["num_hops"] == 3


def test_loops():
    pacote = _pacote(redirects=[
        {"address": "https://a/", "destino_final": "https://a/", "num_hops": 2, "loop": True},
        {"address": "https://b/", "destino_final": "https://d/", "num_hops": 1, "loop": False},
    ])
    r = loops_redirecionamento(_item(None, ["address", "destino_final"]), pacote)
    assert (r.status, r.total_afetadas) == ("reprovado", 1)


def test_loops_sem_ocorrencia_aprova():
    pacote = _pacote(redirects=[
        {"address": "https://b/", "destino_final": "https://d/", "num_hops": 1, "loop": False},
    ])
    assert loops_redirecionamento(_item(None), pacote).status == "aprovado"


def test_title_igual_h1():
    pacote = _pacote(
        page_titles=[
            {"address": "https://a/", "title": "Mesma Coisa", "title_length": 11, "ocorrencias": 1},
            {"address": "https://b/", "title": "Título", "title_length": 6, "ocorrencias": 1},
        ],
        h1=[
            {"address": "https://a/", "h1": "mesma coisa", "ocorrencias": 1},
            {"address": "https://b/", "h1": "Outro H1", "ocorrencias": 1},
        ],
    )
    r = title_igual_h1(_item(None, ["address", "title", "h1"]), pacote)
    assert r.total_afetadas == 1  # comparação case-insensitive
    assert r.amostra[0]["h1"] == "mesma coisa"


def test_title_igual_h1_sem_export_h1():
    pacote = _pacote(page_titles=[{"address": "https://a/", "title": "X"}])
    assert title_igual_h1(_item(None), pacote).status == "sem_dados"


def test_avaliar_pacote_com_checklist_real():
    recarregar_checklist()
    ck = carregar_checklist()
    pacote = _pacote(
        page_titles=[{"address": "https://a/", "title": "", "title_length": 0, "ocorrencias": 1}],
    )
    resultados = avaliar_pacote(ck, pacote, faltantes=["h1"])
    assert resultados["title-tag-ausente-ou-vazia"].status == "reprovado"
    # export declarado como faltante -> sem_dados mesmo sem regra rodar
    assert resultados["tag-h1-ausente-ou-vazia"].status == "sem_dados"
    # item sf sem regra (fora da fatia) -> sem_dados
    assert resultados["conteudo-duplicado"].status == "sem_dados"
    # itens manuais/gsc/cwv-link não aparecem
    assert "analise-de-logfile" not in resultados
    assert all(s in {"aprovado", "atencao", "reprovado", "na", "sem_dados"}
               for s in (r.status for r in resultados.values()))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/test_seotec_motor_custom.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.seotec_motor_custom`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/seotec_motor_custom.py
"""Regras custom do motor SEOTEC — funções nomeadas referenciadas por `regra.funcao`.

Assinatura obrigatória: (item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem.
"""
from app.services.seotec_checklist import ItemChecklist
from app.services.seotec_ingestao import PacoteIngestao
from app.services.seotec_motor import ResultadoItem, _montar_amostra


def _colunas(item: ItemChecklist) -> list[str]:
    return item.evidencia.colunas if item.evidencia else []


def _resultado_lista(item: ItemChecklist, todas: list[dict], afetadas: list[dict]) -> ResultadoItem:
    n = len(afetadas)
    return ResultadoItem(
        status="aprovado" if n == 0 else "reprovado",
        total_avaliadas=len(todas),
        total_afetadas=n,
        amostra=_montar_amostra(afetadas, _colunas(item)),
        truncada=n > len(_montar_amostra(afetadas, _colunas(item))),
    )


def cadeias_redirecionamento(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("redirects")
    if export is None:
        return ResultadoItem(status="sem_dados")
    afetadas = [li for li in export.linhas if (li.get("num_hops") or 0) > 1 and not li.get("loop")]
    return _resultado_lista(item, export.linhas, afetadas)


def loops_redirecionamento(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("redirects")
    if export is None:
        return ResultadoItem(status="sem_dados")
    afetadas = [li for li in export.linhas if li.get("loop")]
    return _resultado_lista(item, export.linhas, afetadas)


def title_igual_h1(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    titles = pacote.exports.get("page_titles")
    h1s = pacote.exports.get("h1")
    if titles is None or h1s is None:
        return ResultadoItem(status="sem_dados")
    h1_por_url = {li.get("address"): (li.get("h1") or "") for li in h1s.linhas}
    afetadas = []
    for li in titles.linhas:
        title = (li.get("title") or "").strip().lower()
        h1 = h1_por_url.get(li.get("address"), "").strip().lower()
        if title and h1 and title == h1:
            afetadas.append({**li, "h1": h1_por_url[li.get("address")]})
    return _resultado_lista(item, titles.linhas, afetadas)
```

Adicionar ao final de `backend/app/services/seotec_motor.py`:

```python
def avaliar_pacote(checklist, pacote: PacoteIngestao, faltantes: list[str]) -> dict[str, ResultadoItem]:
    """Avalia todos os itens fonte=sf. Export faltante -> sem_dados (nunca reprovado)."""
    resultados: dict[str, ResultadoItem] = {}
    for item in checklist.itens():
        if item.fonte != "sf":
            continue
        if item.regra is not None and item.regra.export in faltantes:
            resultados[item.slug] = ResultadoItem(status="sem_dados")
            continue
        resultados[item.slug] = avaliar_item(item, pacote)
    return resultados
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/test_seotec_motor_custom.py tests/unit/test_seotec_motor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/seotec_motor_custom.py backend/app/services/seotec_motor.py backend/tests/unit/test_seotec_motor_custom.py
rtk git commit -m "feat(seotec): regras custom (redirects, title=H1) + avaliar_pacote"
```

---

### Task 7: Health score (`services/seotec_score.py`)

**Files:**
- Create: `backend/app/services/seotec_score.py`
- Test: `backend/tests/unit/test_seotec_score.py`

**Interfaces:**
- Consumes: `ChecklistSeotec` (Task 2).
- Produces (Tasks 8-10):
  - `ScoreResultado(BaseModel)`: `.score: float` (0-100, 2 casas), `.pontos: int`, `.total_pontos: int` (=940), `.por_prioridade: dict[str, dict[str, int]]` (prioridade → {status → contagem de itens}), `.por_categoria: dict[str, dict]` (categoria → {pontos, total_pontos, score})
  - `calcular_health_score(checklist: ChecklistSeotec, statuses: dict[str, str | None]) -> ScoreResultado` — `statuses` mapeia slug → token de status (ou None = não avaliado; conta 0 ponto, igual planilha).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_seotec_score.py
from app.services.seotec_checklist import carregar_checklist, recarregar_checklist
from app.services.seotec_score import calcular_health_score


def _ck():
    recarregar_checklist()
    return carregar_checklist()


def test_todos_aprovados_score_100():
    ck = _ck()
    statuses = {i.slug: "aprovado" for i in ck.itens()}
    r = calcular_health_score(ck, statuses)
    assert r.score == 100.0
    assert r.pontos == 940
    assert r.total_pontos == 940


def test_na_pontua_como_aprovado():
    ck = _ck()
    statuses = {i.slug: "na" for i in ck.itens()}
    assert calcular_health_score(ck, statuses).score == 100.0


def test_nenhum_status_score_0():
    ck = _ck()
    assert calcular_health_score(ck, {}).score == 0.0


def test_reprovado_atencao_sem_dados_nao_pontuam():
    ck = _ck()
    statuses = {i.slug: "aprovado" for i in ck.itens()}
    statuses["title-tag-ausente-ou-vazia"] = "reprovado"   # peso 10
    statuses["title-duplicado"] = "atencao"                # peso 9
    statuses["conteudo-duplicado"] = "sem_dados"           # peso 10
    r = calcular_health_score(ck, statuses)
    assert r.pontos == 940 - 10 - 9 - 10
    assert r.score == round((940 - 29) / 940 * 100, 2)


def test_agregados():
    ck = _ck()
    statuses = {i.slug: "aprovado" for i in ck.itens()}
    statuses["title-tag-ausente-ou-vazia"] = "reprovado"
    r = calcular_health_score(ck, statuses)
    assert r.por_prioridade["very-high"]["reprovado"] == 1
    cat = r.por_categoria["Tag <title>"]
    assert cat["total_pontos"] == 41
    assert cat["pontos"] == 31
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/unit/test_seotec_score.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.seotec_score`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/seotec_score.py
"""Health score SEOTEC — fórmula da planilha NPBR (base 940).

Pontua peso do item quando status ∈ {aprovado, na}; qualquer outro status
(ou ausência de status) pontua 0 — idêntico às colunas R/S do Checklist.
"""
from collections import defaultdict

from pydantic import BaseModel, Field

from app.services.seotec_checklist import ChecklistSeotec, TOTAL_PESOS_ESPERADO

STATUS_PONTUA = {"aprovado", "na"}


class ScoreResultado(BaseModel):
    score: float
    pontos: int
    total_pontos: int
    por_prioridade: dict[str, dict[str, int]] = Field(default_factory=dict)
    por_categoria: dict[str, dict] = Field(default_factory=dict)


def calcular_health_score(
    checklist: ChecklistSeotec, statuses: dict[str, str | None]
) -> ScoreResultado:
    pontos = 0
    por_prioridade: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    por_categoria: dict[str, dict] = {}

    for cat in checklist.categorias:
        cat_pontos = 0
        cat_total = 0
        for item in cat.itens:
            status = statuses.get(item.slug)
            cat_total += item.peso
            if status is not None:
                por_prioridade[item.prioridade][status] += 1
            if status in STATUS_PONTUA:
                pontos += item.peso
                cat_pontos += item.peso
        por_categoria[cat.categoria] = {
            "pontos": cat_pontos,
            "total_pontos": cat_total,
            "score": round(cat_pontos / cat_total * 100, 2) if cat_total else 0.0,
        }

    return ScoreResultado(
        score=round(pontos / TOTAL_PESOS_ESPERADO * 100, 2),
        pontos=pontos,
        total_pontos=TOTAL_PESOS_ESPERADO,
        por_prioridade={p: dict(v) for p, v in por_prioridade.items()},
        por_categoria=por_categoria,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/unit/test_seotec_score.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/seotec_score.py backend/tests/unit/test_seotec_score.py
rtk git commit -m "feat(seotec): health score base 940 com agregados por prioridade/categoria"
```

---

### Task 8: Workflow LangGraph + persistência + worker

**Files:**
- Create: `backend/app/agents/seotec/__init__.py` (vazio)
- Create: `backend/app/agents/seotec/workflow.py`
- Create: `backend/app/services/seotec_persistencia.py`
- Modify: `backend/app/worker.py` (nova função + registro em `WorkerSettings.functions`)
- Modify: `backend/app/config.py` (campo `seotec_upload_dir`)
- Modify: `backend/app/services/ferramenta_service.py` (adicionar `calcular_custo_seo_tecnico`)
- Test: `backend/tests/unit/test_seotec_workflow.py`
- Test: `backend/tests/unit/test_seotec_custo.py`

**Interfaces:**
- Consumes: Tasks 2, 4, 5-7; modelos da Task 3; `credito_service.confirmar_debito`/`liberar_reserva`.
- Produces:
  - `agents/seotec/workflow.py`: `construir_workflow()` (grafo compilado), `EstadoSeotec(TypedDict)`, `executar_auditoria_seotec(execucao_id: str, crawl_id: str) -> None` (entrada usada pelo worker: carrega zip do disco, roda grafo, cuida de billing e status)
  - `services/seotec_persistencia.py`: `persistir_resultados(db, auditoria, crawl, resultados: dict[str, ResultadoItem], score: ScoreResultado, faltantes: list[str]) -> None`
  - `config.settings.seotec_upload_dir: str` (default `/tmp/seotec_uploads`)
  - worker: função ARQ `executar_workflow_seotec(ctx, execucao_id, crawl_id)`
  - Caminho do zip no disco (contrato com a Task 9): `{settings.seotec_upload_dir}/{crawl_id}.zip`

- [ ] **Step 1: Add config**

Em `backend/app/config.py`, adicionar na classe de settings (junto dos demais campos simples):

```python
seotec_upload_dir: str = "/tmp/seotec_uploads"
```

- [ ] **Step 2: Add cost function (TDD)**

Teste primeiro:

```python
# backend/tests/unit/test_seotec_custo.py
from app.services.ferramenta_service import calcular_custo_seo_tecnico


def test_custo_por_fase():
    assert calcular_custo_seo_tecnico("before") == 30
    assert calcular_custo_seo_tecnico("after") == 15
```

Run: `rtk pytest tests/unit/test_seotec_custo.py -v` — Expected: FAIL (ImportError). Então, em `backend/app/services/ferramenta_service.py`, junto das demais `calcular_custo_*`:

```python
CUSTO_SEOTEC_BEFORE = 30
CUSTO_SEOTEC_AFTER = 15


def calcular_custo_seo_tecnico(fase: str) -> int:
    """SPEC_Ferramenta_Auditoria_SEO_Tecnico §3.5: before=30; after e re-crawls=15."""
    return CUSTO_SEOTEC_BEFORE if fase == "before" else CUSTO_SEOTEC_AFTER
```

Run de novo — Expected: PASS.

- [ ] **Step 3: Write the failing test (grafo puro, sem DB)**

```python
# backend/tests/unit/test_seotec_workflow.py
"""Testa o grafo SEOTEC com nós reais e persistência stubada (sem DB)."""
import pytest

from app.agents.seotec.workflow import construir_workflow
from tests.unit.helpers_seotec import montar_pacote_zip

TITLES = [{"address": "https://a/", "title": "", "title_length": 0, "ocorrencias": 1}]


@pytest.mark.asyncio
async def test_grafo_processa_pacote():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "h1": [], "internal": []})
    grafo = construir_workflow()
    estado = await grafo.ainvoke({
        "zip_bytes": zip_bytes,
        "auditoria_id": "aud-1",
        "crawl_id": "crawl-1",
        "fase_destino": "before",
        "persistir": False,
    })
    assert estado["erro"] is None
    assert estado["resultados"]["title-tag-ausente-ou-vazia"].status == "reprovado"
    assert estado["score"].score < 100
    assert "response_codes" in estado["faltantes"]


@pytest.mark.asyncio
async def test_grafo_zip_invalido_seta_erro():
    grafo = construir_workflow()
    estado = await grafo.ainvoke({
        "zip_bytes": b"lixo",
        "auditoria_id": "aud-1",
        "crawl_id": "crawl-1",
        "fase_destino": "before",
        "persistir": False,
    })
    assert estado["erro"]
    assert estado.get("resultados") in (None, {})
```

- [ ] **Step 4: Run test to verify it fails**

Run: `rtk pytest tests/unit/test_seotec_workflow.py -v`
Expected: FAIL — `ModuleNotFoundError: app.agents.seotec`

- [ ] **Step 5: Write the workflow**

```python
# backend/app/agents/seotec/workflow.py
"""Workflow SEOTEC Onda 1: validar_pacote -> motor_regras -> health_score -> persistir.

Nós de IA (analisar_ia, recomendar_ia) entram na Onda 3 entre motor_regras e
health_score (SPEC_Ferramenta_Auditoria_SEO_Tecnico §3.3). Padrão do grafo:
agents/cwv/workflow.py. `persistir=False` permite rodar o grafo puro em teste.
"""
import logging
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.services.seotec_checklist import carregar_checklist
from app.services.seotec_ingestao import validar_pacote
from app.services.seotec_motor import avaliar_pacote
from app.services.seotec_score import calcular_health_score

logger = logging.getLogger(__name__)


class EstadoSeotec(TypedDict, total=False):
    zip_bytes: bytes
    auditoria_id: str
    crawl_id: str
    fase_destino: str
    persistir: bool
    pacote: Any            # PacoteIngestao
    faltantes: list[str]
    resultados: Any        # dict[str, ResultadoItem]
    score: Any             # ScoreResultado
    erro: str | None


def _exports_requeridos() -> set[str]:
    ck = carregar_checklist()
    return {i.regra.export for i in ck.itens() if i.fonte == "sf" and i.regra is not None}


async def node_validar_pacote(estado: EstadoSeotec) -> EstadoSeotec:
    r = validar_pacote(estado["zip_bytes"], exports_requeridos=_exports_requeridos())
    if r.pacote is None:
        return {**estado, "erro": "; ".join(r.erros) or "pacote inválido"}
    return {**estado, "pacote": r.pacote, "faltantes": r.faltantes, "erro": None}


async def node_motor_regras(estado: EstadoSeotec) -> EstadoSeotec:
    if estado.get("erro"):
        return estado
    ck = carregar_checklist()
    resultados = avaliar_pacote(ck, estado["pacote"], estado["faltantes"])
    return {**estado, "resultados": resultados}


async def node_health_score(estado: EstadoSeotec) -> EstadoSeotec:
    if estado.get("erro"):
        return estado
    ck = carregar_checklist()
    statuses = {slug: r.status for slug, r in estado["resultados"].items()}
    return {**estado, "score": calcular_health_score(ck, statuses)}


async def node_persistir(estado: EstadoSeotec) -> EstadoSeotec:
    if estado.get("erro") or not estado.get("persistir", True):
        return estado
    from app.db.session import async_session_factory
    from app.models.seo_auditoria import SeoAuditoria
    from app.models.seo_crawl import SeoCrawl
    from app.services.seotec_persistencia import persistir_resultados

    async with async_session_factory() as db:
        auditoria = await db.get(SeoAuditoria, estado["auditoria_id"])
        crawl = await db.get(SeoCrawl, estado["crawl_id"])
        await persistir_resultados(
            db, auditoria, crawl, estado["resultados"], estado["score"], estado["faltantes"]
        )
        await db.commit()
    return estado


def construir_workflow():
    g = StateGraph(EstadoSeotec)
    g.add_node("validar_pacote", node_validar_pacote)
    g.add_node("motor_regras", node_motor_regras)
    g.add_node("health_score", node_health_score)
    g.add_node("persistir", node_persistir)
    g.set_entry_point("validar_pacote")
    g.add_edge("validar_pacote", "motor_regras")
    g.add_edge("motor_regras", "health_score")
    g.add_edge("health_score", "persistir")
    g.add_edge("persistir", END)
    return g.compile()


async def executar_auditoria_seotec(execucao_id: str, crawl_id: str) -> None:
    """Entrada do worker: carrega zip, roda grafo, billing + status da execução."""
    from app.config import settings
    from app.db.session import async_session_factory
    from app.models.execucao_ferramenta import ExecucaoFerramenta
    from app.models.seo_crawl import SeoCrawl
    from app.services import credito_service
    from app.services.ferramenta_service import calcular_custo_seo_tecnico

    caminho = Path(settings.seotec_upload_dir) / f"{crawl_id}.zip"

    async with async_session_factory() as db:
        crawl = await db.get(SeoCrawl, crawl_id)
        execucao = await db.get(ExecucaoFerramenta, execucao_id)
        crawl.status = "processando"
        execucao.status = "executando"
        await db.commit()
        usuario_id = str(execucao.usuario_id)
        fase_destino = crawl.fase_destino
        auditoria_id = str(crawl.auditoria_id)

    custo = calcular_custo_seo_tecnico(fase_destino)
    try:
        zip_bytes = caminho.read_bytes()
        grafo = construir_workflow()
        estado = await grafo.ainvoke({
            "zip_bytes": zip_bytes,
            "auditoria_id": auditoria_id,
            "crawl_id": crawl_id,
            "fase_destino": fase_destino,
            "persistir": True,
        })
        if estado.get("erro"):
            raise ValueError(estado["erro"])
    except Exception as exc:
        logger.exception("SEOTEC falhou execucao=%s crawl=%s", execucao_id, crawl_id)
        async with async_session_factory() as db:
            crawl = await db.get(SeoCrawl, crawl_id)
            execucao = await db.get(ExecucaoFerramenta, execucao_id)
            crawl.status = "erro"
            crawl.erro_msg = str(exc)[:500]
            execucao.status = "falhou"
            execucao.erro_msg = str(exc)[:500]
            await credito_service.liberar_reserva(db, usuario_id, custo)
            await db.commit()
        return
    finally:
        caminho.unlink(missing_ok=True)

    async with async_session_factory() as db:
        execucao = await db.get(ExecucaoFerramenta, execucao_id)
        execucao.status = "concluido"
        await credito_service.confirmar_debito(
            db, usuario_id, reservado=custo, quantidade=custo,
            descricao=f"Auditoria SEO Técnico ({fase_destino})",
            ferramenta="auditoria_seo_tecnico", execucao_id=execucao_id,
        )
        await db.commit()
```

Antes de finalizar: conferir em `backend/app/models/execucao_ferramenta.py` os valores reais usados no campo `status` (ex.: `concluido` vs `concluida`) e em `credito_service` o nome exato de `liberar_reserva` — usar os identificadores existentes, não os deste bloco, se divergirem.

- [ ] **Step 6: Write the persistence service**

```python
# backend/app/services/seotec_persistencia.py
"""Persistência dos resultados SEOTEC (upsert por (auditoria_id, item_slug))."""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seo_auditoria import SeoAuditoria
from app.models.seo_crawl import SeoCrawl
from app.models.seo_item_resultado import SeoItemResultado
from app.services.seotec_checklist import carregar_checklist
from app.services.seotec_motor import ResultadoItem
from app.services.seotec_score import ScoreResultado


async def persistir_resultados(
    db: AsyncSession,
    auditoria: SeoAuditoria,
    crawl: SeoCrawl,
    resultados: dict[str, ResultadoItem],
    score: ScoreResultado,
    faltantes: list[str],
) -> None:
    ck = carregar_checklist()
    existentes = {
        i.item_slug: i
        for i in (await db.execute(
            select(SeoItemResultado).where(SeoItemResultado.auditoria_id == auditoria.id)
        )).scalars()
    }
    campo_status = "status_antes" if crawl.fase_destino == "before" else "status_depois"

    for item in ck.itens():
        linha = existentes.get(item.slug)
        if linha is None:
            linha = SeoItemResultado(
                auditoria_id=auditoria.id,
                item_slug=item.slug,
                modo="auto" if item.fonte == "sf" else "manual",
            )
            db.add(linha)
        resultado = resultados.get(item.slug)
        if resultado is not None:
            setattr(linha, campo_status, resultado.status)
            linha.evidencias_json = {
                "total_avaliadas": resultado.total_avaliadas,
                "total_afetadas": resultado.total_afetadas,
                "amostra": resultado.amostra,
                "truncada": resultado.truncada,
            }

    if crawl.fase_destino == "before":
        auditoria.score_antes = score.score
        if auditoria.data_inicial is None:
            auditoria.data_inicial = datetime.now(UTC)
    else:
        auditoria.score_depois = score.score

    crawl.status = "parcial" if faltantes else "processado"
    crawl.contadores_json = {
        "faltantes": faltantes,
        "score": score.score,
        "por_prioridade": score.por_prioridade,
        "por_categoria": score.por_categoria,
        "itens_avaliados": len(resultados),
    }
    await db.flush()
```

- [ ] **Step 7: Register in worker**

Em `backend/app/worker.py`, seguir o padrão de `executar_consolidador_cwv` (linha ~161): adicionar

```python
async def executar_workflow_seotec(ctx, execucao_id: str, crawl_id: str):
    from app.agents.seotec.workflow import executar_auditoria_seotec

    await executar_auditoria_seotec(execucao_id, crawl_id)
```

e acrescentar `executar_workflow_seotec` à lista `WorkerSettings.functions`.

- [ ] **Step 8: Run tests**

Run: `rtk pytest tests/unit/test_seotec_workflow.py tests/unit/test_seotec_custo.py -v` — Expected: PASS.
Run: `rtk pytest tests/unit/ -k seotec -v` — Expected: todos PASS.

- [ ] **Step 9: Commit**

```bash
rtk git add backend/app/agents/seotec/ backend/app/services/seotec_persistencia.py backend/app/worker.py backend/app/config.py backend/app/services/ferramenta_service.py backend/tests/unit/test_seotec_workflow.py backend/tests/unit/test_seotec_custo.py
rtk git commit -m "feat(seotec): workflow LangGraph + persistência + worker ARQ com billing"
```

---

### Task 9: Rotas + schemas + custo

**Files:**
- Create: `backend/app/schemas/seotec.py`
- Create: `backend/app/routers/ferramentas_seo_tecnico.py`
- Modify: `backend/app/main.py` (registrar router — seguir o padrão de registro de `ferramentas_cwv_auditoria`)

**Interfaces:**
- Consumes: modelos (Task 3), ingestão (Task 4), checklist (Task 2), worker job `executar_workflow_seotec` (Task 8), `credito_service`, deps `get_db`/`get_current_user`/`rate_limit_autenticado`.
- Produces: rotas sob `/ferramentas/auditoria-seo-tecnico`:
  - `POST /auditorias` → cria (`{cliente_id, dominio}`) · `GET /auditorias?cliente_id=` → lista
  - `GET /auditorias/{id}` → detalhe (auditoria + score + status do último crawl + itens agrupados por categoria)
  - `PATCH /auditorias/{id}/itens/{slug}` → campos manuais
  - `POST /auditorias/{id}/upload` → multipart zip (fallback B), 202

- [ ] **Step 1: Write the schemas**

```python
# backend/app/schemas/seotec.py
"""Schemas da Auditoria de SEO Técnico (Onda 1)."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

StatusItem = Literal["aprovado", "atencao", "reprovado", "na", "sem_dados"]


class AuditoriaCriar(BaseModel):
    cliente_id: UUID
    dominio: HttpUrl


class AuditoriaResumo(BaseModel):
    id: UUID
    cliente_id: UUID
    dominio: str
    fase: str
    score_antes: float | None
    score_depois: float | None
    criado_em: datetime

    model_config = {"from_attributes": True}


class CrawlResumo(BaseModel):
    id: UUID
    fase_destino: str
    origem: str
    status: str
    erro_msg: str | None
    contadores_json: dict
    criado_em: datetime

    model_config = {"from_attributes": True}


class ItemResposta(BaseModel):
    item_slug: str
    nome: str
    categoria: str
    peso: int
    prioridade: str
    fonte: str
    modo: str
    status_antes: StatusItem | None
    status_depois: StatusItem | None
    evidencias_json: dict
    status_cliente: str | None
    validacao_seo: str | None
    observacao_cliente: str | None
    observacao_seo: str | None


class AuditoriaDetalhe(AuditoriaResumo):
    ultimo_crawl: CrawlResumo | None
    itens: list[ItemResposta]


class ItemPatch(BaseModel):
    status_antes: StatusItem | None = None
    status_depois: StatusItem | None = None
    status_cliente: str | None = Field(default=None, max_length=2000)
    validacao_seo: str | None = Field(default=None, max_length=2000)
    observacao_cliente: str | None = Field(default=None, max_length=5000)
    observacao_seo: str | None = Field(default=None, max_length=5000)
```

- [ ] **Step 2: Write the router**

```python
# backend/app/routers/ferramentas_seo_tecnico.py
"""Router da Auditoria de SEO Técnico (SPEC_Ferramenta_Auditoria_SEO_Tecnico §3.2).

Onda 1: CRUD de auditoria + upload manual do pacote (fallback B) + edição manual
de itens. Conector/pareamento (Onda 2), IA (Onda 3) e SSE (Onda 4) ficam fora.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.cliente import Cliente
from app.models.execucao_ferramenta import ExecucaoFerramenta
from app.models.seo_auditoria import SeoAuditoria
from app.models.seo_crawl import SeoCrawl
from app.models.seo_item_resultado import SeoItemResultado
from app.models.usuario import Usuario
from app.schemas.seotec import (
    AuditoriaCriar,
    AuditoriaDetalhe,
    AuditoriaResumo,
    CrawlResumo,
    ItemPatch,
    ItemResposta,
)
from app.services.ferramenta_service import calcular_custo_seo_tecnico
from app.services.seotec_checklist import carregar_checklist

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ferramentas/auditoria-seo-tecnico", tags=["auditoria-seo-tecnico"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


async def _auditoria_do_usuario(db: AsyncSession, auditoria_id: UUID, usuario: Usuario) -> SeoAuditoria:
    auditoria = await db.get(SeoAuditoria, auditoria_id)
    if auditoria is None or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria não encontrada")
    return auditoria


@router.post("/auditorias", status_code=201, response_model=AuditoriaResumo)
async def criar_auditoria(
    body: AuditoriaCriar,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Any:
    cliente = await db.get(Cliente, body.cliente_id)
    if cliente is None or str(cliente.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    auditoria = SeoAuditoria(
        usuario_id=usuario.id, cliente_id=body.cliente_id, dominio=str(body.dominio),
    )
    db.add(auditoria)
    await db.flush()
    return auditoria


@router.get("/auditorias", response_model=list[AuditoriaResumo])
async def listar_auditorias(
    cliente_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Any:
    q = select(SeoAuditoria).where(SeoAuditoria.usuario_id == usuario.id)
    if cliente_id:
        q = q.where(SeoAuditoria.cliente_id == cliente_id)
    q = q.order_by(SeoAuditoria.criado_em.desc()).limit(100)
    return list((await db.execute(q)).scalars())


@router.get("/auditorias/{auditoria_id}", response_model=AuditoriaDetalhe)
async def detalhe_auditoria(
    auditoria_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Any:
    auditoria = await _auditoria_do_usuario(db, auditoria_id, usuario)
    crawl = (await db.execute(
        select(SeoCrawl).where(SeoCrawl.auditoria_id == auditoria.id)
        .order_by(SeoCrawl.criado_em.desc()).limit(1)
    )).scalar_one_or_none()
    linhas = {
        r.item_slug: r
        for r in (await db.execute(
            select(SeoItemResultado).where(SeoItemResultado.auditoria_id == auditoria.id)
        )).scalars()
    }
    ck = carregar_checklist()
    itens = []
    for item in ck.itens():
        linha = linhas.get(item.slug)
        itens.append(ItemResposta(
            item_slug=item.slug, nome=item.nome, categoria=item.categoria,
            peso=item.peso, prioridade=item.prioridade, fonte=item.fonte,
            modo=linha.modo if linha else ("auto" if item.fonte == "sf" else "manual"),
            status_antes=linha.status_antes if linha else None,
            status_depois=linha.status_depois if linha else None,
            evidencias_json=linha.evidencias_json if linha else {},
            status_cliente=linha.status_cliente if linha else None,
            validacao_seo=linha.validacao_seo if linha else None,
            observacao_cliente=linha.observacao_cliente if linha else None,
            observacao_seo=linha.observacao_seo if linha else None,
        ))
    return AuditoriaDetalhe(
        **AuditoriaResumo.model_validate(auditoria).model_dump(),
        ultimo_crawl=CrawlResumo.model_validate(crawl) if crawl else None,
        itens=itens,
    )


@router.patch("/auditorias/{auditoria_id}/itens/{item_slug}", response_model=ItemResposta)
async def editar_item(
    auditoria_id: UUID,
    item_slug: str,
    body: ItemPatch,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Any:
    auditoria = await _auditoria_do_usuario(db, auditoria_id, usuario)
    ck = carregar_checklist()
    item_def = ck.itens_por_slug().get(item_slug)
    if item_def is None:
        raise HTTPException(status_code=404, detail="Item não existe no checklist")
    linha = (await db.execute(
        select(SeoItemResultado).where(
            SeoItemResultado.auditoria_id == auditoria.id,
            SeoItemResultado.item_slug == item_slug,
        )
    )).scalar_one_or_none()
    if linha is None:
        linha = SeoItemResultado(
            auditoria_id=auditoria.id, item_slug=item_slug,
            modo="auto" if item_def.fonte == "sf" else "manual",
        )
        db.add(linha)
    for campo, valor in body.model_dump(exclude_unset=True).items():
        setattr(linha, campo, valor)
    await db.flush()
    return ItemResposta(
        item_slug=item_def.slug, nome=item_def.nome, categoria=item_def.categoria,
        peso=item_def.peso, prioridade=item_def.prioridade, fonte=item_def.fonte,
        modo=linha.modo, status_antes=linha.status_antes, status_depois=linha.status_depois,
        evidencias_json=linha.evidencias_json or {}, status_cliente=linha.status_cliente,
        validacao_seo=linha.validacao_seo, observacao_cliente=linha.observacao_cliente,
        observacao_seo=linha.observacao_seo,
    )


@router.post("/auditorias/{auditoria_id}/upload", status_code=202)
async def upload_pacote(
    auditoria_id: UUID,
    arquivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("seotec_upload", max_requests=5, window_seconds=300)),
) -> dict[str, Any]:
    auditoria = await _auditoria_do_usuario(db, auditoria_id, usuario)
    if auditoria.fase == "concluida":
        raise HTTPException(status_code=409, detail="Auditoria já concluída")
    fase_destino = "before" if auditoria.fase == "before" else "after"

    conteudo = await arquivo.read()
    if len(conteudo) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Pacote acima de 50MB")

    custo = calcular_custo_seo_tecnico(fase_destino)
    from app.services import credito_service

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), custo)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Créditos insuficientes") from exc

    execucao = ExecucaoFerramenta(
        usuario_id=usuario.id, cliente_id=auditoria.cliente_id,
        ferramenta="auditoria_seo_tecnico", status="pendente",
        entrada_json={"auditoria_id": str(auditoria.id), "fase_destino": fase_destino},
    )
    db.add(execucao)
    await db.flush()
    crawl = SeoCrawl(
        auditoria_id=auditoria.id, execucao_id=execucao.id,
        fase_destino=fase_destino, origem="upload", schema_version=1,
    )
    db.add(crawl)
    await db.flush()

    destino = Path(settings.seotec_upload_dir)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{crawl.id}.zip").write_bytes(conteudo)

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow_seotec", str(execucao.id), str(crawl.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception:
        logger.exception("Falha ao enfileirar SEOTEC")
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        execucao.status = "falhou"
        crawl.status = "erro"
        crawl.erro_msg = "Falha ao enfileirar workflow"
        await db.flush()
        raise HTTPException(status_code=503, detail="Fila indisponível, tente novamente")

    return {"crawl_id": str(crawl.id), "execucao_id": str(execucao.id), "custo": custo,
            "fase_destino": fase_destino, "status": crawl.status}
```

Antes de finalizar: conferir em `backend/app/models/execucao_ferramenta.py` os nomes reais dos campos (`entrada_json`, `job_id`, valores de `status`) e ajustar; conferir a assinatura real de `rate_limit_autenticado` em `app/dependencies.py`.

- [ ] **Step 3: Register router**

Em `backend/app/main.py`, seguir exatamente o padrão de include do router `ferramentas_cwv_auditoria` (mesmo prefixo de API e dependências globais):

```python
from app.routers import ferramentas_seo_tecnico
app.include_router(ferramentas_seo_tecnico.router)
```

(Se os routers existentes recebem `prefix="/api"` ou dependências no include, replicar.)

- [ ] **Step 4: Verify app boots and tests pass**

Run: `rtk pytest tests/unit/ -k seotec -v` — Expected: todos PASS.
Run (import smoke): `python -c "from app.main import app; print(len(app.routes))"` de `backend/` — Expected: imprime número, sem traceback.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/seotec.py backend/app/routers/ferramentas_seo_tecnico.py backend/app/main.py
rtk git commit -m "feat(seotec): rotas auditorias, upload manual e edição de itens"
```

---

### Task 10: E2E — pacote fixture → auditoria completa

**Files:**
- Test: `backend/tests/e2e/test_e2e_seotec.py`

**Interfaces:**
- Consumes: tudo das Tasks 1-9; DB dev local migrado (`rtk alembic upgrade head`); helper `montar_pacote_zip`.

- [ ] **Step 1: Write the e2e test**

Padrão script-style de `tests/e2e/test_e2e_cwv.py` (roda contra o Postgres local via `async_session_factory`, sem fixtures pytest de DB):

```python
# backend/tests/e2e/test_e2e_seotec.py
"""E2E SEOTEC Onda 1: upload de pacote fixture -> workflow -> score persistido.

Pré-requisito: Postgres dev de pé + `alembic upgrade head` + 1 usuário existente.
Roda o workflow inline (sem worker ARQ) chamando executar_auditoria_seotec.
"""
import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, text

from app.config import settings
from app.db.session import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _usuario_qualquer() -> str:
    async with async_session_factory() as s:
        uid = (await s.execute(text("SELECT id FROM usuarios LIMIT 1"))).scalar()
        if uid:
            return str(uid)
        uid = str(uuid.uuid4())
        await s.execute(
            text("INSERT INTO usuarios (id, email, nome, senha_hash, email_verificado, mfa_ativo, ativo) "
                 "VALUES (:id, :email, 'Usuário E2E SEOTEC', 'x', true, false, true)"),
            {"id": uid, "email": f"e2e-seotec-{uid[:8]}@teste.local"},
        )
        await s.commit()
        return str(uid)


async def preparar(usuario_id: str) -> tuple[str, str, str, str]:
    from app.models.execucao_ferramenta import ExecucaoFerramenta
    from app.models.seo_auditoria import SeoAuditoria
    from app.models.seo_crawl import SeoCrawl

    async with async_session_factory() as s:
        cliente_id = str(uuid.uuid4())
        await s.execute(
            text("INSERT INTO clientes (id, usuario_id, nome, site_url, config_json, ativo) "
                 "VALUES (:id, :uid, 'Cliente E2E SEOTEC', NULL, '{}', true)"),
            {"id": cliente_id, "uid": usuario_id},
        )
        auditoria = SeoAuditoria(usuario_id=usuario_id, cliente_id=cliente_id,
                                 dominio="https://exemplo.com.br")
        s.add(auditoria)
        await s.flush()
        execucao = ExecucaoFerramenta(
            usuario_id=usuario_id, cliente_id=cliente_id,
            ferramenta="auditoria_seo_tecnico", status="enfileirado",
            entrada_json={"auditoria_id": str(auditoria.id), "fase_destino": "before"},
        )
        s.add(execucao)
        await s.flush()
        crawl = SeoCrawl(auditoria_id=auditoria.id, execucao_id=execucao.id,
                         fase_destino="before", origem="upload", schema_version=1)
        s.add(crawl)
        await s.flush()
        ids = (str(auditoria.id), str(crawl.id), str(execucao.id), cliente_id)
        await s.commit()
        return ids


def _pacote_fixture() -> bytes:
    from tests.unit.helpers_seotec import montar_pacote_zip

    return montar_pacote_zip({
        "page_titles": [
            {"address": "https://exemplo.com.br/", "title": "", "title_length": 0, "ocorrencias": 1},
            {"address": "https://exemplo.com.br/sobre", "title": "Sobre nós", "title_length": 9, "ocorrencias": 1},
        ],
        "meta_description": [
            {"address": "https://exemplo.com.br/", "meta_description": "x" * 200,
             "meta_description_length": 200, "ocorrencias": 1},
        ],
        "h1": [
            {"address": "https://exemplo.com.br/", "h1": "Home", "ocorrencias": 1},
        ],
        "internal": [
            {"address": "https://exemplo.com.br/", "status_code": 200, "crawl_depth": 0,
             "word_count": 800, "response_time": 0.4},
        ],
        "response_codes": [
            {"address": "https://exemplo.com.br/quebrada", "status_code": 404},
        ],
        "robots": [{"existe": True, "status_code": 200, "sitemaps_declarados": ["https://exemplo.com.br/sitemap.xml"]}],
        "sitemaps": [{"sitemap_url": "https://exemplo.com.br/sitemap.xml", "status_code": 200, "total_urls": 10}],
        "images": [],
        "redirects": [],
    })


async def rodar() -> None:
    from app.agents.seotec.workflow import executar_auditoria_seotec

    usuario_id = await _usuario_qualquer()
    auditoria_id, crawl_id, execucao_id, cliente_id = await preparar(usuario_id)

    # garante saldo reservado para o débito do workflow
    # (conferir __tablename__ real em app/models/conta_credito.py e ajustar o UPDATE)
    async with async_session_factory() as s:
        from app.services import credito_service
        conta = await credito_service.buscar_ou_criar_conta(s, usuario_id)
        conta.saldo_plano += 100
        await credito_service.reservar_creditos(s, usuario_id, 30)
        await s.commit()

    Path(settings.seotec_upload_dir).mkdir(parents=True, exist_ok=True)
    (Path(settings.seotec_upload_dir) / f"{crawl_id}.zip").write_bytes(_pacote_fixture())

    await executar_auditoria_seotec(execucao_id, crawl_id)

    from app.models.seo_auditoria import SeoAuditoria
    from app.models.seo_crawl import SeoCrawl
    from app.models.seo_item_resultado import SeoItemResultado

    async with async_session_factory() as s:
        auditoria = await s.get(SeoAuditoria, auditoria_id)
        crawl = await s.get(SeoCrawl, crawl_id)
        itens = list((await s.execute(
            select(SeoItemResultado).where(SeoItemResultado.auditoria_id == auditoria_id)
        )).scalars())

        assert crawl.status == "processado", crawl.erro_msg
        assert auditoria.score_antes is not None and 0 < float(auditoria.score_antes) < 100
        assert len(itens) == 124
        por_slug = {i.item_slug: i for i in itens}
        assert por_slug["title-tag-ausente-ou-vazia"].status_antes == "reprovado"
        assert por_slug["ha-um-robots-txt-configurado-corretamente-no-site"].status_antes == "aprovado"
        assert por_slug["erros-no-lado-do-cliente-40x"].status_antes == "reprovado"
        assert por_slug["redirecionamentos-302"].status_antes == "na"
        assert por_slug["conteudo-duplicado"].status_antes == "sem_dados"
        assert por_slug["analise-de-logfile"].modo == "manual"
        ev = por_slug["title-tag-ausente-ou-vazia"].evidencias_json
        assert ev["total_afetadas"] == 1 and ev["amostra"]

    # cleanup
    async with async_session_factory() as s:
        await s.execute(text("DELETE FROM seo_auditoria WHERE id = :id"), {"id": auditoria_id})
        await s.execute(text("DELETE FROM execucoes_ferramentas WHERE id = :id"), {"id": execucao_id})
        await s.execute(text("DELETE FROM clientes WHERE id = :id"), {"id": cliente_id})
        await s.commit()
    logger.info("[OK] E2E SEOTEC completo — score_antes=%s", auditoria.score_antes)


def test_e2e_seotec():
    asyncio.run(rodar())
```

- [ ] **Step 2: Run it**

Pré: Postgres dev de pé (memória do projeto: `make dev`, backend no host — `make up` tem bug de DB host), DB dedicado `sass2_seotec_dev` criado e migrado (`rtk alembic upgrade head` com a URL apontando para ele — ver Task 3 Step 4) e a mesma URL exportada ao rodar o pytest.

Run: `rtk pytest tests/e2e/test_e2e_seotec.py -v`
Expected: PASS. Se `crawl.status == "erro"`, o assert imprime `erro_msg` — depurar pelo motivo real (padrão: campo de `ExecucaoFerramenta` divergente na Task 8/9; corrigir lá, não no teste).

- [ ] **Step 3: Run the whole seotec suite + commit**

```bash
rtk pytest tests/unit/ -k seotec tests/e2e/test_e2e_seotec.py -v
rtk git add backend/tests/e2e/test_e2e_seotec.py
rtk git commit -m "test(seotec): e2e pacote fixture -> workflow -> score persistido"
```

---

### Task 11: Atualizar specs (status Onda 1)

**Files:**
- Modify: `docs/specs/ferramentas/auditoria-seo-tecnico/README.md` (status `📋 planejado` → `🚧 em desenvolvimento`; nota "Onda 1 implementada: upload manual + motor parcial (31 regras)")
- Modify: `docs/specs/ferramentas/auditoria-seo-tecnico/SPEC_Ferramenta_Auditoria_SEO_Tecnico.md` e `SPEC_SEOTEC_Checklist_Motor_Regras.md` (linha na tabela Histórico com o commit da onda; registrar decisão: checklist YAML em `backend/app/data/seotec_checklist/`, não `app/kb/`)
- Modify: `docs/specs/README.md` (status da capacidade)

- [ ] **Step 1: Edit the 4 files as above**
- [ ] **Step 2: Commit**

```bash
rtk git add docs/specs/
rtk git commit -m "docs(seotec): specs refletem Onda 1 implementada"
```

---

## Fora deste plano (ondas seguintes)

- **Onda 1b:** regras dos ~67 itens `fonte: sf` restantes (dados estruturados, hreflang, AMP, duplicado, segurança, custom search/extraction) — mesmo padrão: overlay + fixtures.
- **Onda 2:** conector `tools/sf-connector/` + rotas de dispositivo (SPEC_SEOTEC_Conector_Local_SF).
- **Onda 3:** analisador/recomendador IA + KB (SPEC_SEOTEC_Agentes_IA).
- **Onda 4:** ciclo de fases completo, comparativo, SSE, frontend (SPEC_SEOTEC_Ciclo_Auditoria_Health_Score + spec-mãe §3.4).
