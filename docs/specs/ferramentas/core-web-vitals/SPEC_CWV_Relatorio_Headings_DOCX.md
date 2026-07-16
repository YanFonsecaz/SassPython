# SPEC — Relatório DOCX: hierarquia de headings e sumário duplicado

**Status:** ✅ implementado
**Capacidade:** `core-web-vitals`
**Escopo:** `backend` — export HTML→DOCX e prompt do redator
**Código:** `backend/app/services/cwv_export.py`, `backend/app/agents/cwv/redator.py`
**Créditos:** não cobra
**Depende de:** [[SPEC_CWV_Relatorio_Executivo]] (S9) · [[SPEC_CWV_Export_Consolidado_Execucao]] (S3)
**Commit/Data:** — · 2026-07-15

---

## 1. Contexto (por quê)

**Defeitos visuais encontrados no DOCX real do teste E2E (auditoria Kumon, 2026-07-15;
1.065 parágrafos, 56 tabelas).** Dois sintomas, uma causa comum — markdown embutido é convertido
por `_md_to_html` (`cwv_export.py:83-87`) **sem rebaixar os níveis de heading** ao contexto onde é
inserido:

1. **"Sumário Executivo" duplicado:** `relatorio_auditoria_para_html` emite
   `<h2>Sumário executivo</h2>` e logo abaixo `_md_to_html(rel["sumario_executivo_md"])`
   (`cwv_export.py:446-447`). O LLM abre o markdown com um heading próprio (`# Sumário Executivo`)
   — o prompt não proíbe headings (`redator.py::_montar_prompt`). No DOCX aparecem dois títulos
   consecutivos quase idênticos.
2. **Hierarquia invertida:** a `documentacao_md` da KB contém `## Problema`, `## Solucao`,
   `## Referencias` (`documentador.py:119-142`). Embutida sob itens `<h3>/<h4>` do plano de ação
   (`cwv_export.py:314-317, 512-517`), vira `<h2>` → que o conversor
   `parecer_service.py::html_para_docx_bytes` mapeia para **Heading 1** (`parecer_service.py:110-117`:
   h2→Heading 1, h3→Heading 2, h4-h6→Heading 3). Resultado observado no DOCX: "Problema"/"Solucao"
   como Heading 1 **dentro** de itens Heading 2 — o sumário/navegação do Word fica sem sentido.

Cosmético, mas visível em todo relatório entregue ao cliente — e o relatório executivo é
exatamente o entregável "de consultoria" do programa NPBR.

## 2. Requisitos / Critérios de aceite

- [ ] Dado `sumario_executivo_md` começando com heading cujo texto normalizado é
      "sumário executivo" (case/acentos ignorados), quando o relatório é gerado, então esse heading
      é removido e resta apenas o `<h2>` da seção (sem duplicata no DOCX).
- [ ] Dado qualquer markdown embutido (`documentacao_md`, `recomendacao_md`,
      `diagnostico_tecnico_md`, `sumario_executivo_md`), quando convertido para HTML, então nenhum
      heading resultante tem nível **menor ou igual** ao heading da seção que o contém (ex.:
      `## Problema` sob um item `<h4>` vira `<h5>`, nunca `<h2>`).
- [ ] Dado o DOCX da auditoria gerado após a correção, então a estrutura de headings é
      monotônica: Title → Heading 1 (seções) → Heading 2 (itens numerados) → Heading 3
      (Problema/Solução/Como corrigir/Referências).
- [ ] Dado markdown com bloco de código cercado (```) contendo linhas iniciadas por `#`, quando
      rebaixado, então o conteúdo do bloco **não** é alterado.
- [ ] Dado o prompt do redator, então ele instrui explicitamente a não usar headings markdown
      (defesa em profundidade; a correção determinística não depende disso).

## 3. Design (mapeado ao código)

### 3.1 Helper de rebaixamento (`cwv_export.py`)

```python
def _rebaixar_headings_md(md_text: str, base: int) -> str:
    """Desloca headings ATX para que o menor nível do texto vire `base` (cap h6).

    Ignora linhas dentro de blocos cercados (``` ... ```).
    """
```

Implementação: varrer linhas com um flag de fence; coletar níveis `^#{1,6}\s`; se houver headings,
`delta = base - min(niveis)`; reescrever cada heading com `min(nivel + delta, 6)`. Sem headings →
retorna o texto intacto.

E um segundo helper:

```python
def _remover_heading_titulo(md_text: str, titulo: str) -> str:
    """Remove o primeiro heading se seu texto normalizado == titulo normalizado."""
```

Normalização: `casefold()` + remoção de acentos via `unicodedata.normalize("NFKD", ...)`.

### 3.2 Pontos de aplicação (todos em `cwv_export.py`)

| Local | Linha (hoje) | Contexto pai | Chamada |
|---|---|---|---|
| Sumário executivo | 446-447 | `<h2>` | `_md_to_html(_rebaixar_headings_md(_remover_heading_titulo(md, "Sumário executivo"), 3))` |
| Diagnóstico técnico | 533-535 | `<h2>` | rebaixar para base 3 (+ remover título "Diagnóstico técnico" se presente) |
| `recomendacao_md` do consolidado | 512-513 | `<h3>` item | rebaixar para base 4 |
| `documentacao_md` sob "Como corrigir" `<h4>` | 515-517 | `<h4>` | rebaixar para base 5 |
| `doc_md` em `_capitulo_problemas` | 314-317 | `heading_tag` h2/h3/h4 dinâmico | rebaixar para `nivel(heading_tag) + 2` (fica abaixo do "Como corrigir" que é `+1`) |

O mapeamento do conversor DOCX (`parecer_service.py:110-117`) já aceita h5/h6 (→ Heading 3);
nenhuma mudança no conversor.

### 3.3 Prompt do redator (`redator.py::_montar_prompt`, linha ~156)

Acrescentar à instrução final: *"Não use títulos markdown (linhas começando com #) — escreva
apenas parágrafos e listas; os títulos das seções já existem no documento."* O fallback
determinístico (`_fallback_deterministico`) não gera headings — conferir e manter.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Onde corrigir | Determinístico no export (`_rebaixar_headings_md`) | Só instruir o LLM — LLMs ignoram instruções de formatação com frequência; a KB (`## Problema`) nem passa por LLM |
| Regra de rebaixamento | Relativa (menor nível do texto → `base`) | Delta fixo (+3) — estouraria h6 em markdown que já usa `###` e não normaliza textos que começam em `##` vs `#` |
| Duplicata do sumário | Remover só se o texto do heading bater com o título da seção | Remover sempre o primeiro heading — apagaria títulos legítimos que o LLM criar ("Visão geral") |
| Cap de nível | h6 (conversor mapeia h4-h6 → Heading 3) | Reestruturar o mapeamento do `html_para_docx_bytes` — tocaria o export do Parecer também (fora de escopo) |
| Editar `documentador.py` | Não mexer (a `documentacao_md` também é exibida sozinha na UI, onde `##` está correto) | Rebaixar na origem — quebraria a renderização standalone do problema |

## 5. Verificação

```bash
cd backend && uv run pytest tests/unit/test_cwv_export.py -q
```

- Unit `_rebaixar_headings_md`: `"## A\n### B"` base 3 → `"### A\n#### B"`; texto sem heading
  intacto; heading dentro de fence intacto; cap em `######`.
- Unit `_remover_heading_titulo`: `"# Sumário Executivo\n\ntexto"` → `"texto"`;
  `"# Visão geral\n..."` → inalterado.
- Integração: montar `relatorio_auditoria_para_html` com `sumario_executivo_md` iniciando por
  `# Sumário Executivo` e um consolidado com `documentacao_md` da KB → assert de que o HTML não
  contém `<h1>`/`<h2>` entre o `<h2>Sumário executivo</h2>` e a próxima seção, e que abaixo de
  `<h4>Como corrigir</h4>` só existem `<h5>`/`<h6>`.
- Manual: gerar o DOCX de uma auditoria real e conferir o painel de navegação do Word
  (estrutura monotônica Title → H1 → H2 → H3).

## 6. Não-objetivos

- Redesenho visual do DOCX (estilos, cores, capa) — só hierarquia/duplicação.
- Mudar o conversor `html_para_docx_bytes` (compartilhado com o Parecer).
- Alterar a `documentacao_md` na origem (KB/documentador) ou sua renderização na UI.
- Exports por análise/problema (`analise/{id}/docx`, `problema/{id}/docx`) — herdam o helper se
  usarem `_md_to_html`, mas a validação desta spec é o relatório da auditoria e o consolidado da
  execução.

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-15 | Spec criada a partir do DOCX real do E2E (auditoria Kumon): sumário duplicado + "Problema"/"Solucao" como Heading 1 sob itens Heading 2 | — |
