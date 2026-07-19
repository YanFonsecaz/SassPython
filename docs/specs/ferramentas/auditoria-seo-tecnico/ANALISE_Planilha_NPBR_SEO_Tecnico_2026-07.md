# ANÁLISE — Planilha NPBR "Auditoria de SEO Técnico" (Template Enterprise 2026)

**Status:** 🗄️ histórico (análise-base, encerrada) · **Data:** 2026-07-17
**Fonte:** `® [TEMPLATE OFICIAL ENTERPRISE - 2026] Auditoria de SEO Técnico _ NPBR.xlsx` (raiz do repo)
**Papel:** fundamenta a ferramenta [auditoria-seo-tecnico](README.md), como
[AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07](../core-web-vitals/AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md)
fundamentou o programa de paridade do CWV.

---

## 1. Inventário: 85 abas

| Grupo | Abas | Visibilidade | Papel |
|---|---|---|---|
| **Health Score** | 1 (`Health Score`) | visível | Dashboard executivo: score antes/depois, gráficos, listas de erros por prioridade |
| **Checklist** | 1 (`Checklist`) | visível | Fonte da verdade: ~125 itens × 24 colunas, todo o scoring |
| **Control** | 1 (`Control`) | oculta | Tabelas de apoio: pesos, thresholds, agregações p/ gráficos |
| **Evidência por item** | 82 | ocultas (1 visível: "O site está sendo indexado") | 1 aba por item do checklist com dados brutos + recomendação |

A planilha veio do Google Sheets (fórmulas exportadas com `__xludf.DUMMYFUNCTION`/`FILTER`).
As abas de evidência ficam ocultas e o consultor exibe apenas as que têm achados no cliente.

## 2. Aba `Checklist` — colunas (linha 3 = header)

| Col | Campo | Preenchimento |
|---|---|---|
| A | Nome do item ou categoria | fixo (template) |
| B | **STATUS ANTES** (`Reprovado`/`Atenção`/`Aprovado`/`n/a`) | manual (consultor) |
| C | **STATUS DEPOIS** | manual (consultor, pós-correção) |
| D/E | Status SITE / Status BLOG | fórmula (deriva de N/O) |
| F | Status de implementação do cliente | fórmula/manual |
| G/H | Observação cliente / Observação SEO NPBR | manual |
| I/J | Impacto DIRETO / INDIRETO (bool) | fixo |
| K | **PRIORIDADE** | fórmula: nível Q vs thresholds da Control → `Low`/`Medium`/`High`/`Very High` |
| L | IMPLEMENTAÇÃO (`Obrigatória`/`É bom ter`/`Não é essencial`) | fixo |
| M | RESPONSÁVEL (`Desenvolvedor`/`Time de marketing`/ambos) | fixo |
| N/O | Flag problema no SITE / BLOG (bool) | manual |
| P | **Data-limite sugerida** | fórmula: data inicial + `5`(VH)/`10`(H)/`20`(M)/`45`(L) dias |
| Q | **NÍVEL (peso)** 3–10 | fixo |
| R/S | SCORE ANTES / DEPOIS | fórmula: `=Q` se Aprovado/n-a, `0` se Reprovado/Atenção |
| T/U | Score SITE / BLOG | fórmula análoga |
| V/W | DESCRIÇÃO / IMPORTÂNCIA (texto didático) | fixo |
| X | CATEGORIA | fixo |

**Linha 2 (agregados):** `Q2 = SUM(níveis) = 940` pontos totais; score % antes `= R2/Q2·100`;
depois `= S2/Q2·100`. Coluna I da linha 1-2 menciona **"Impacto em IAs (Resultados LLM)"** —
o template 2026 já rotula impacto em respostas de LLMs.
**Linha 4:** `DATA INICIAL AUDITORIA` (B4) e `DATA ÚLTIMA AUDITORIA` (`C4 = B4+60`).
**Linhas de categoria** (18): `Q = SUM(filhos)`, `K = Q_cat/Q_total` (participação no score).

### Categorias e pesos (Q = soma dos itens)

| Categoria | Q | Itens |
|---|---|---|
| Problemas de Acessibilidade/Encontrabilidade | 73 | 10 |
| Sitemaps XML da Página | 23 | 3 |
| Arquitetura | 52 | 8 |
| Problemas da URL | 24 | 3 |
| Otimização para Mobile | 9 | 1 |
| Problemas com Tags na Página/Markup | 21 | 3 |
| Tag `<title>` | 41 | 6 |
| Tag `<meta description>` | 27 | 5 |
| Headings da Página (H1–H6) | 33 | 5 |
| Dados Estruturados | 168 | 21 |
| Conteúdo do Corpo Principal | 14 | 2 |
| Conteúdo não indexável | 27 | 4 |
| Imagens de SEO | 15 | 3 |
| SEO Internacional | 117 | 13 |
| Páginas AMP | 45 | 5 |
| Potenciais Gatilhos de Conteúdo Duplicado | 68 | 8 |
| Autoridade (E-E-A-T) | 17 | 3 |
| Problemas com Links | 8 | 1 |
| Problemas com Google Search Console | 48 | 6 |
| Problemas de Segurança | 39 | 5 |
| Propriedade de SEO | 29 | 4 |
| Velocidade da Página | 42 | 5 |
| **Total** | **940** | **~125** |

### Regra de prioridade (Control A2:B5)

`Low=4 · Medium=6 · High=8 · Very High=10` → prioridade do item:
`Q≤4 → Low · 4<Q≤6 → Medium · 6<Q≤8 → High · Q>8 → Very High`.

## 3. Aba `Health Score` — dashboard

- Bloco "ERROS CRÍTICOS" com seções por prioridade (`Prioridade Muito Alta` r28+, `Prioridade Média`
  r160+, …). Cada seção: pool de linhas com `VLOOKUP` no Checklist; o consultor cola o **nome do
  item** na coluna F e as demais colunas se preenchem (SITE, BLOG, impacto DIRETO/INDIRETO,
  CATEGORIA, DESCRIÇÃO, IMPORTÂNCIA).
- Gráficos "Before NPA" / "After NPA" (Aprovado/Atenção/Reprovado por prioridade) alimentados pela
  `Control` via `COUNTIF/COUNTIFS` no Checklist (colunas B e C).

## 4. Abas de evidência (82) — padrão estrutural

Estrutura fixa observada (ex.: `Title tag ausente ou vazia`, `Dados Estruturados`,
`O site está sendo indexado`):

```
A1  Título do item          E1 «VOLTAR PARA A HOME | Health Score» (hyperlink)
A2  "Fonte: <origem>"       (Screaming Frog · GSC · SERP e Sitemap XML · GTMetrix e PSI …)
A4  Recomendação            (texto do consultor, às vezes com cenários 1/2)
A7  Diagnóstico SEO         (texto longo, quando presente)
A7+ Tabela de evidências    (colunas específicas do item + "Status cliente" + "Validação SEO")
…   Dados colados do export do Screaming Frog / prints de GSC
```

Exemplos de tabela de evidência:

- **Title tag ausente/vazia:** `Address | Title Atual | #chars (=LEN) | Title Recomendado | #chars |
  Status cliente | Validação SEO` + formatação condicional `>63` chars.
- **Dados Estruturados:** `Tipo de página | Recomendação de exemplo de código (JSON-LD completo) |
  Tipos de marcação | Rich Results elegíveis | Status Cliente | Validação SEO`.
- **O site está sendo indexado:** contagem SERP (`site:`) vs contagem do Sitemap XML + prints GSC.

As colunas **Status cliente / Validação SEO** aparecem em todas — é o workflow
consultor→cliente→validação que a ferramenta reproduz com campos editáveis.

## 5. Workflow implícito da agência

1. Roda Screaming Frog (+ GSC, SERP, PSI/GTMetrix) → cola exports nas abas de evidência.
2. Marca STATUS ANTES por item; ajusta N/O (site/blog).
3. Escreve Recomendação/Diagnóstico por aba; exibe as abas com achados.
4. Cliente implementa (Status cliente); consultor valida (Validação SEO).
5. Marca STATUS DEPOIS → Health Score compara antes/depois (score % + gráficos).

## 6. Classificação de automação (base para a ferramenta)

Números aproximados — a classificação item a item vive no YAML seed (fonte final) descrito em
[SPEC_SEOTEC_Checklist_Motor_Regras](SPEC_SEOTEC_Checklist_Motor_Regras.md) §3.3:

| Fonte | Itens (aprox.) | V1 |
|---|---|---|
| **Screaming Frog** (crawl + custom search/extraction) | ~78 | Automático (motor de regras + IA) |
| **Google Search Console** | 8 | Manual (OAuth GSC é não-objetivo V1) |
| **SERP / avaliação subjetiva / externos** (rodapé, navegação, LogFile, GTMetrix, malware…) | ~19 | Manual com apoio de dados do crawl |
| **Velocidade via PSI** | 2 | Link para a ferramenta CWV existente (status manual) |

Detalhe item a item: [SPEC_SEOTEC_Checklist_Motor_Regras](SPEC_SEOTEC_Checklist_Motor_Regras.md).
