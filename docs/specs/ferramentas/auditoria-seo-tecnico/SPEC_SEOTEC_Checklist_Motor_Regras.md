# SPEC — Seed do checklist (125 itens) + motor de regras determinístico

**Status:** 🚧 parcial
**Capacidade:** `auditoria-seo-tecnico`
**Escopo:** backend — `backend/app/data/seotec_checklist/*.yaml`, `backend/app/services/seotec_checklist.py`, `backend/app/services/seotec_motor.py`
**Créditos:** não cobra (motor é determinístico, zero LLM)
**Depende de:** [SPEC_SEOTEC_Conector_Local_SF](SPEC_SEOTEC_Conector_Local_SF.md) (contrato de ingestão)

---

## 1. Contexto (por quê)

O valor da planilha está no checklist: itens, pesos, prioridades, textos didáticos e o critério de
aprovação de cada um. Isso vira **seed YAML versionado** (editável por PR, como a KB do CWV) + um
**motor determinístico** que avalia cada item automatizável a partir do pacote de ingestão — sem
LLM, reprodutível e barato. A IA entra depois, só para explicar e recomendar
([SPEC_SEOTEC_Agentes_IA](SPEC_SEOTEC_Agentes_IA.md)).

## 2. Requisitos / Critérios de aceite

- [ ] Script one-off `scripts/seed_seotec_checklist.py` extrai da planilha NPBR os ~125 itens
      (nome, categoria, peso Q, prioridade, implementação, responsável, impacto direto/indireto,
      descrição, importância) e gera os YAMLs. Conferência manual antes do commit.
- [ ] Loader (`services/seotec_checklist.py`) valida schema no startup (como `cwv_kb`), expõe itens
      por slug e falha rápido em YAML inválido.
- [ ] Motor avalia todo item `fonte: sf` com `regra` definida → `Reprovado`/`Atenção`/`Aprovado`/
      `Sem dados` + evidências tipadas (contadores + amostra de URLs com colunas do item).
- [ ] Prioridade de cada item **copiada da planilha** para o YAML (a planilha contém exceções
      manuais à fórmula); a regra `Q≤4 Low · ≤6 Medium · ≤8 High · >8 Very High` fica como default
      para itens futuros sem prioridade explícita.
- [ ] 1 teste unitário por regra com fixture (CSV pequeno → status esperado).
- [ ] Item sem dados no pacote (export ausente/parcial) → `Sem dados`, nunca `Reprovado`.

## 3. Design (mapeado ao código)

### 3.1 Schema do YAML (1 arquivo por categoria)

```yaml
categoria: "Tag <title>"
itens:
  - slug: title-ausente-ou-vazia
    nome: "Title tag ausente ou vazia"
    peso: 10
    implementacao: obrigatoria          # obrigatoria | bom-ter | nao-essencial
    responsavel: [marketing, dev]
    impacto: {direto: true, indireto: false, ia: true}   # "ia" = coluna Impacto em IAs da planilha
    fonte: sf                            # sf | manual | gsc | cwv-link
    descricao: >-                        # coluna V da planilha
      A title tag das suas páginas…
    importancia: >-                      # coluna W
      Title tags são ESSENCIAIS…
    regra:
      export: page_titles
      tipo: contagem                     # contagem | limiar | existencia | proporcao | custom
      filtro: {campo: title, op: vazio}
      atencao_se: "0 < afetadas <= 5"    # opcional; default: qualquer afetada = Reprovado
    evidencia:
      colunas: [address, title, title_length]
      recomendada_ia: true               # gera coluna "recomendado" via IA? (limitado, ver Agentes)
```

### 3.2 Motor (`services/seotec_motor.py`)

Funções puras: `avaliar_item(item_def, pacote) -> ResultadoItem`. Tipos de regra:

| Tipo | Semântica | Exemplos |
|---|---|---|
| `contagem` | N linhas do export casam filtro; N>0 → Reprovado | title vazio, 40x, canonical quebrado |
| `limiar` | campo comparado a limite por linha | title >63 ou <30 chars, meta desc >155/<70, imagem >100 KB, word count baixo |
| `existencia` | recurso existe/não existe no site | robots.txt ok, sitemap declarado no robots, doctype, viewport, lang, GA tag |
| `proporcao` | % de páginas afetadas decide Reprovado/Atenção | trailing slash misto, www/non-www misto, hreflang parcial |
| `custom` | função Python nomeada p/ casos compostos | cadeias/loops de redirect, sitemap órfãs vs crawl, hierarquia de headings |

### 3.3 Mapeamento item → fonte (classificação completa dos 125)

**`fonte: sf` (automáticos, ~78 itens):**

| Categoria | Itens automatizados | Export/base |
|---|---|---|
| Acessibilidade/Encontrabilidade | robots.txt correto · sitemap no robots.txt · sitemap otimizado · meta robots · página 404 adequada · erros 40x · erros 50x · páginas órfãs | `robots`, `sitemaps`, `response_codes`, `directives`, `inlinks` |
| Sitemaps XML | site tem sitemap · sitemap com links quebrados | `sitemaps` × `response_codes` |
| Arquitetura | menu em HTML (custom extraction `<nav>`) · +3 cliques (crawl depth) · hierarquia de URLs (profundidade/padrão) | `internal`, custom |
| Problemas da URL | hífens como delimitador · URL curta/compartilhável (limiar de comprimento) · palavras-chave na URL (heurística + IA) | `internal` |
| Mobile | viewport correta (custom extraction) | custom |
| Tags/Markup | doctype (custom) · meta-refresh (custom) · fonte contém metas no `<head>` | custom, `internal` |
| `<title>` | ausente/vazia · duplicado · >63 · <30 · = H1 · múltiplas | `page_titles` |
| `<meta description>` | ausente · duplicada · >155 · <70 · múltiplas | `meta_description` |
| Headings | H1 ausente · H1 duplicada entre páginas · múltiplas H1 · hierarquia de headings (custom) | `h1`, `h2`, custom |
| Dados Estruturados | uso de markup · erros de schema · avisos de schema · presença por tipo (Article, BlogPosting, Breadcrumb, Product, Organization, WebSite, … 18 tipos) | `structured_data` (validation + types) |
| Conteúdo | lorem ipsum (custom search) · word count baixo | custom, `content` |
| Não-indexável | conteúdo via HTML vs JS (JS rendering comparison) · flash (custom) · iframe (custom) · conteúdo escondido (parcial/IA) | custom, `internal` |
| Imagens | nome de arquivo com keywords (heurística) · >100 KB · ALT ausente/ruim | `images` |
| SEO Internacional | lang attr (custom) · hreflang no head · hreflang 200 · não vinculadas · links retorno ausentes/inconsistentes/não-canônicos/noindex · códigos incorretos · entradas múltiplas · auto-referência · x-default · canonical em hreflang | `hreflang` |
| AMP | /amp/ na URL · rel=canonical AMP→regular · rel=alternate regular→AMP · amp html declarado · AMP indexável | `amp`/custom |
| Conteúdo Duplicado | www vs non-www · http vs https · trailing slash · case sensitive · conteúdo duplicado (hash/near-dup do SF) · self canonical · canonical quebrado · múltiplas canonicals | `internal`, `canonicals`, `content` |
| Links | links quebrados 4xx/5xx | `response_codes` + inlinks |
| Segurança | SSL válido · HSTS · HTTPS→HTTP links · HTTPS→recursos HTTP (mixed content) | `security` |
| Propriedade SEO | redirects 302 · cadeias · loops · redirects quebrados | `redirects` (chains report) |
| Velocidade | páginas lentas (response time do crawl) | `internal` |

**`fonte: manual` (~19):** análise de LogFile · indexação eficiente (SERP `site:` vs sitemap) ·
breadcrumbs presentes/clicáveis · barra de navegação otimizada · rodapé otimizado · backlink
site↔blog · otimização de palavras-chave na URL (validação final) · H1 acima da dobra · conteúdo
escondido (confirmação visual) · biografia do autor · rel=author · avaliação de clientes ·
verificação de malware · GTMetrix · Experiência na Página (parcial CWV) · sitemaps listados no GSC.

**`fonte: gsc` (8, manuais na V1):** ações manuais · página não encontrada · bloqueadas por
robots.txt · páginas indexadas · indexação de sitemap · estatísticas de rastreamento · (2 variantes
de páginas indexadas/bloqueadas da planilha).

**`fonte: cwv-link` (2):** PSI desktop <70 · PSI mobile <50 → card com link para a ferramenta CWV
do mesmo cliente (dados já existem lá); status manual na V1.

### 3.4 Saída (evidências tipadas)

`ResultadoItem`: `{status, total_paginas_avaliadas, total_afetadas, amostra: [{address, …colunas do
item}], truncada: bool}` — persistido em `seo_item_resultado.evidencias_json` (contrato JSONB
tipado, padrão CWV).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Onde vivem os itens | YAML no git (PR para ajustar textos/pesos) | Tabela no DB + UI admin |
| Pesos | Copiados da planilha (base 940) | Re-balancear na V1 (quebraria comparabilidade com auditorias antigas da agência) |
| Itens subjetivos | `fonte: manual` honesto | Forçar heurística fraca e gerar falso Aprovado |
| Regras | Funções puras testáveis por fixture | Regras em YAML interpretado (DSL cara e opaca) |

## 5. Verificação

```bash
rtk pytest backend/tests/unit/test_seotec_motor.py          # 1 teste por regra
rtk pytest backend/tests/unit/test_seotec_checklist_seed.py # schema YAML + soma de pesos = 940
python backend/scripts/seed_seotec_checklist.py --dry-run    # regeneração confere com YAML commitado
```

## 6. Não-objetivos

Editar checklist pela UI · pesos por tenant · regras plugáveis por usuário · detecção JS rendering
completa (comparação HTML vs DOM renderizado fica no que o SF entrega).

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-18 | Onda 1 implementada (fundação de dados: seed, modelos 0030, ingestão, motor 31 regras, score, workflow, rotas, e2e) | b70c771 |
| 2026-07-17 | Spec inicial; classificação dos 125 itens | — |
