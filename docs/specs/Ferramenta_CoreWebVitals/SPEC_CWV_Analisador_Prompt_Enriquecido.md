# SPEC #1 — Enriquecer prompt do fallback do analisador

**Status:** a aplicar · **Escopo:** backend (`agents/cwv/analisador.py`)
**Dependências:** nenhuma — é a primeira etapa antes de [[SPEC_CWV_Analisador_Tools_Pesquisa]] e [[SPEC_CWV_Analisador_Context7]].
**Esforço estimado:** ~3 h
**Prioridade:** alta — maior ROI/custo. Não envolve provider externo, não muda contrato.

## 1. Contexto e problema

`CWVAnalisadorAgent.analisar()` (`backend/app/agents/cwv/analisador.py:23-116`) tem dois caminhos:

1. **Fast-path determinístico** — audits cujo `id` casa com `audits_lighthouse` da KB → mapeamento direto.
2. **Fallback LLM** — audits residuais vão para `invoke_structured(prompt, ListaProblemas)`.

O prompt do fallback (linhas 139-163 / `_montar_prompt_analise`) hoje passa apenas:

```
- ID: <audit.id>
- Titulo: <audit.title>
- Score: <audit.score>
- DisplayValue: <audit.displayValue>
```

Mas o JSON do Lighthouse (PSI v5) para cada audit contém muito mais sinal que está sendo descartado:

| Campo Lighthouse | Hoje | Útil para? |
|---|---|---|
| `description` | ❌ | LLM entender o que o audit mede |
| `details.type` | ❌ | distinguir `opportunity` (tem savings) de `diagnostic` (info) |
| `details.overallSavingsMs` | ❌ | priorizar audits com maior potencial de ganho |
| `details.overallSavingsBytes` | ❌ | idem (bytes) |
| `details.items[].url` / `node.selector` | parcial (top 5 em `_extrair_contexto`, mas só no contexto, não no prompt) | dar elementos concretos para o LLM |
| `numericValue` + `numericUnit` | ❌ | valor bruto (ms, bytes) sem perder precisão |
| `warnings[]` | ❌ | LLM identificar borderline cases |
| `scoreDisplayMode` | ❌ | distinguir `informative` de `binary` / `numeric` |

Resultado: o LLM recebe pouco contexto e tende a (a) cair em `outros` quando o `title` é ambíguo, ou (b) sugerir `kb_codigo` errado por interpretar mal o audit. As consequências aparecem hoje como o problema #7 "Problema não catalogado" visto no E2E de 2026-05-27.

Além disso, o prompt **não dá ao LLM as descrições resumidas dos `kb_codigos`** — só os códigos secos. Para um código como `js-execucao-pesada-no-load`, o LLM precisa adivinhar o que ele significa. A KB já tem `titulo` e `descricao` curtos por entrada, mas eles não estão sendo aproveitados no prompt.

## 2. Solução

### 2.1 `_extrair_contexto` mais rico

Em `analisador.py:129-136`, expandir para capturar:

```python
def _extrair_contexto(audit: dict) -> dict:
    details = audit.get("details") or {}
    items = details.get("items") or []
    return {
        "display_value": audit.get("displayValue"),
        "title": audit.get("title"),
        "description": audit.get("description"),
        "score": audit.get("score"),
        "score_display_mode": audit.get("scoreDisplayMode"),
        "numeric_value": audit.get("numericValue"),
        "numeric_unit": audit.get("numericUnit"),
        "details_type": details.get("type"),
        "savings_ms": details.get("overallSavingsMs"),
        "savings_bytes": details.get("overallSavingsBytes"),
        "warnings": audit.get("warnings") or [],
        "items": _resumir_items(items[:5]),
    }


def _resumir_items(items: list[dict]) -> list[dict]:
    """Reduz cada item a um dict compacto (url/selector/label + valor numerico)."""
    out = []
    for it in items:
        compact = {}
        if it.get("url"):
            compact["url"] = it["url"][:200]
        node = it.get("node") if isinstance(it.get("node"), dict) else None
        if node and node.get("selector"):
            compact["selector"] = node["selector"][:150]
        if it.get("label"):
            compact["label"] = str(it["label"])[:100]
        # Métricas numéricas comuns em itens
        for k in ("wastedMs", "wastedBytes", "totalBytes", "transferSize", "duration"):
            if it.get(k) is not None:
                compact[k] = it[k]
        if compact:
            out.append(compact)
    return out
```

### 2.2 Prompt do LLM mais informativo

Reescrever `_montar_prompt_analise` (linhas 139-163) para:

1. Incluir **título + descrição curta** dos `kb_codigos` (não só os códigos secos).
2. Passar para cada audit os novos campos de contexto.
3. Adicionar instrução para usar `savings_ms`/`savings_bytes` como sinal de severidade.

Estrutura proposta do novo prompt (PT-BR, mantendo o estilo já usado no agente):

```text
Voce e um especialista em Core Web Vitals analisando audits do Lighthouse.
Mapeie cada audit falho para o codigo da base de conhecimento mais especifico.

Plataforma: shopify
Metricas atuais: LCP=14100ms, CLS=0.111, INP=292ms, FCP=5700ms, TTFB=320ms, TBT=1000ms

## Base de conhecimento (use APENAS estes codigos)

- lcp-imagem-grande — Imagem LCP excede 100KB ou nao otimizada (LCP)
- lcp-css-bloqueante — CSS render-blocking atrasa o paint inicial (LCP, FCP)
- js-bundle-grande — Bundle JavaScript excessivamente grande (INP, TBT)
- ... (resto, formato `codigo — titulo (metricas)`)
- outros — Audit nao se encaixa em nenhum codigo acima

## Audits falhos a classificar

### audit: largest-contentful-paint-element
- Titulo: Largest Contentful Paint element
- Descricao: This is the largest contentful element painted within the viewport.
- Score: 0 (numeric)
- Valor: 14100 ms (display: "14.1 s")
- Tipo de detalhe: table
- Ganho potencial: — (audit informativo, sem savings)
- Top elementos:
  - selector: "main > section.hero > img"
  - url: "https://thefirealarmsupplier.com/cdn/shop/files/hero.jpg"

### audit: third-party-summary
- ...

## Instrucoes

- Para cada audit, escolha o kb_codigo mais especifico (preferir mais especifico a mais generico).
- Use `savings_ms` ou `savings_bytes` para priorizar — audits com >500ms ou >100KB de ganho sao alta severidade.
- Se NENHUM codigo se encaixa, use 'outros' e descreva no campo `contexto_especifico.audit_id` qual era o audit.
- NAO invente kb_codigo fora da lista acima.
- Inclua em `contexto_especifico` os elementos/URLs especificos afetados (max 3).
- Retorne todos os problemas identificados (um audit pode mapear para um problema; varios audits podem consolidar no mesmo codigo).
```

### 2.3 Listagem da KB com título + descrição curta

Adicionar uma função helper em `services/cwv_kb.py`:

```python
def listar_kb_codigos_descritos(max_desc_chars: int = 80) -> list[dict]:
    """Codigos com titulo + descricao curta (1 linha) para prompts."""
    kb = carregar_kb()
    out = []
    for e in kb.entradas:
        desc_curta = e.descricao.split("\n")[0][:max_desc_chars]
        out.append({
            "codigo": e.codigo,
            "titulo": e.titulo,
            "descricao_curta": desc_curta,
            "metricas_afetadas": e.metricas_afetadas,
        })
    return out
```

E usar em `analisador.py:53`:

```python
kb_descritos = listar_kb_codigos_descritos()
kb_codigos_validos = {c["codigo"] for c in kb_descritos}
prompt = _montar_prompt_analise(audits_para_llm, kb_descritos, plataforma, metricas)
```

### 2.4 Métrica: log do tamanho do prompt

Adicionar `logger.info("CWV analisador prompt size: %d chars, %d audits", len(prompt), len(audits_para_llm))` antes do `invoke_structured` para podermos calibrar `MAX_AUDITS_RESIDUAIS_LLM` (hoje 15) se necessário.

## 3. Critérios de aceitação

1. **Mais campos no prompt:** novos campos do Lighthouse aparecem no prompt do fallback (verificar via log de debug ou snapshot test).
2. **KB com descrição:** prompt mostra `codigo — titulo (metricas)` em vez de só `- codigo`.
3. **Sem aumento >2× no tamanho médio do prompt:** medir antes/depois em 5 análises reais; alvo `<25k chars` para não explodir custo OpenAI.
4. **Sem regressão funcional:** `pytest backend/tests/unit/test_cwv_analisador.py` continua verde (criar testes se ainda não existem — atualmente em `backend/tests/`).
5. **Anti-alucinação preservado:** validação `kb_codigo not in kb_codigos_validos → descarta` continua ativa.
6. **Re-rodar E2E** sobre URL com ≥1 audit residual e confirmar que o `kb_codigo` escolhido pelo LLM é coerente com `description` do audit.

## 4. Arquivos afetados

- `backend/app/agents/cwv/analisador.py` — `_extrair_contexto`, `_montar_prompt_analise`, novo `_resumir_items`.
- `backend/app/services/cwv_kb.py` — nova função `listar_kb_codigos_descritos`.
- `backend/tests/unit/test_cwv_analisador.py` (criar se não existir) — testes para o novo prompt.

## 5. Fora de escopo

- Adicionar tools ao LLM (vai em [[SPEC_CWV_Analisador_Tools_Pesquisa]]).
- Expandir KB (vai em [[SPEC_CWV_KB_Expansao_Gaps]]).
- Mudar provider OpenAI ou modelo.

## 6. Métricas pós-deploy a observar

- Taxa de fallback `→ outros` (esperar **queda** porque o LLM agora tem mais contexto para escolher código específico).
- Custo médio em tokens da chamada do analisador (esperar **alta moderada** ~30-50%, justificada).
- Taxa de `kb_codigo` descartado por alucinação (esperar manutenção em ~0%).
