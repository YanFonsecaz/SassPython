# SPEC — Estimador de esforço de implementação por problema

**Status:** ✅ implementado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (mapa determinístico + coluna) e frontend (badge)
**Código:** `backend/app/agents/cwv/priorizador.py`, `backend/app/models/cwv_problema.py`, `backend/app/services/cwv_persistencia.py`, `backend/app/schemas/cwv.py`, `backend/migrations/versions/0025_cwv_problema_esforco.py`, `frontend/src/components/cwv/cwv-plano-acao.tsx`, `frontend/src/components/cwv/cwv-problema-detalhes.tsx`  ·  **Rota:** `core-web-vitals`
**Créditos:** não cobra
**Depende de:** —
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gap #21)

---

## 1. Contexto (por quê)

A planilha (e qualquer plano de ação de consultoria) responde não só "o que corrigir primeiro" mas "quanto custa corrigir". A ferramenta tem severidade e prioridade, mas não esforço — o cliente não consegue separar o quick-win (trocar formato de imagem) do projeto (reescrever bundle JS). Esta spec adiciona `esforco ∈ {baixo, medio, alto}` determinístico por problema; o ajuste fino contextual por LLM fica no consolidador (`[[SPEC_CWV_Consolidador_Cross_URL]]`).

## 2. Requisitos / Critérios de aceite

- [ ] Dado um problema com `kb_codigo='imagens-formato-moderno'`, quando priorizado, então `esforco='baixo'`.
- [ ] Dado um problema com `kb_codigo='js-bundle-grande'`, então `esforco='alto'`.
- [ ] Dado um problema sem KB (`kb_codigo=None`) com `audit_id` de família conhecida (ex.: `unused-javascript`), então o esforço deriva do fallback por família; família desconhecida → `None`.
- [ ] Dado TODA entrada da KB (`app/data/cwv_knowledge_base.yaml`), então existe esforço definido no mapa (teste de completude falha se uma entrada nova da KB não for classificada).
- [ ] Dado uma análise persistida, quando `GET /core-web-vitals/analise/{id}`, então cada problema traz `esforco`; problemas antigos (pré-migração) trazem `null` sem erro.
- [ ] Dado o plano de ação na UI, então cada problema exibe badge de esforço (baixo/médio/alto) ao lado da severidade.

## 3. Design (mapeado ao código)

### 3.1 Mapa e função — `agents/cwv/priorizador.py`

```python
ESFORCO_POR_KB: dict[str, str] = {
    # baixo: config/atributo/plugin — sem refactor de código
    "imagens-formato-moderno": "baixo", "imagens-tamanho-correto": "baixo",
    "imagens-offscreen": "baixo", "lcp-imagem-lazy-load": "baixo",
    "lcp-imagem-sem-dimensoes": "baixo", "cls-imagem-sem-dimensoes-cls": "baixo",
    "lcp-preload-faltando": "baixo", "preconnect-origens": "baixo",
    "ttfb-compress-faltando": "baixo", "cache-headers-inadequados": "baixo",
    "js-nao-minificado": "baixo", "viewport-faltando": "baixo",
    "https-redirecionamento": "baixo", "document-write-evitado": "baixo",
    "js-passive-listeners-faltando": "baixo", "user-timing": "baixo",
    "lcp-imagem-grande": "baixo", "eficiente-conteudo-animado": "baixo",
    "meta-description-faltando": "baixo", "imagens-sem-alt": "baixo",
    # medio: mexe em tema/infra pontual
    "lcp-fonte-bloqueante": "medio", "cls-fonte-web-flash": "medio",
    "fcp-render-blocking": "medio", "lcp-css-bloqueante": "medio",
    "recurso-render-blocking-extra": "medio", "lcp-script-no-head": "medio",
    "ttfb-sem-cache-cdn": "medio", "ttfb-redirect-chain": "medio",
    "servidor-tempo-resposta-lento": "medio", "lcp-ttfb-alto": "medio",
    "https-mixed-content": "medio", "cls-iframe-sem-dimensoes": "medio",
    "cls-ad-injetado": "medio", "polyfill-desnecessario": "medio",
    "js-duplicado": "medio", "prioridade-recursos": "medio",
    "cls-animacao-sem-transform": "medio", "animacoes-nao-compositadas": "medio",
    "fcp-critical-path-longo": "medio", "cookies-thirdparty": "medio",
    "bf-cache-nao-elegivel": "medio", "performance-budget": "medio",
    "service-worker-sem-estrategia-cache": "medio",
    # alto: refactor de código/arquitetura
    "js-bundle-grande": "alto", "js-bloqueante-thirdparty": "alto",
    "js-long-task": "alto", "js-execucao-pesada-no-load": "alto",
    "dom-muito-grande": "alto", "dom-profundidade-alta": "alto",
    "event-handler-pesado": "alto", "cls-conteudo-injetado-dinamicamente": "alto",
    # informativos/genéricos
    "outros": None-like → usar "medio",
    "metrica-lcp-info": "medio", "metrica-fcp-info": "medio",
    "metrica-tti-info": "medio", "metrica-si-info": "medio", "metrica-inp-info": "medio",
}
```

> A lista acima é diretriz; o implementador DEVE conferir os códigos reais em `app/data/cwv_knowledge_base.yaml` (57 entradas na escrita desta spec) e cobrir todos — o teste de completude é o guarda.

Fallback por família de `audit_id` (substring): `image|img` → baixo; `css|font|cache|compress|redirect|preconnect|preload|viewport` → medio... na verdade: `FALLBACK_FAMILIA = [("image","baixo"),("font","medio"),("css","medio"),("cache","baixo"),("compression","baixo"),("redirect","medio"),("javascript","alto"),("script","alto"),("dom","alto"),("server","medio"),("third-party","medio")]` — primeira substring que casar; nenhum → `None`.

```python
def estimar_esforco(kb_codigo: str | None, audit_id: str | None) -> str | None
```

Aplicação em `priorizar_problemas` (nó `node_priorizar` já chama): para cada problema, `p["esforco"] = estimar_esforco(p.get("kb_codigo"), p.get("audit_id"))`.

### 3.2 Persistência e API

- `models/cwv_problema.py`: coluna `esforco String(10) NULL` + CHECK `cwv_problema_esforco_check` IN (`baixo`,`medio`,`alto`). Migração `0025_cwv_problema_esforco.py` (add_column + constraint; downgrade remove).
- `cwv_persistencia.py::persistir_analise`: gravar `esforco=p.get("esforco")`; `_analise_to_dict`: serializar.
- `schemas/cwv.py::ProblemaResposta`: `esforco: str | None = None`.

### 3.3 Frontend

- `types`/`lib/api/cwv.ts`: campo `esforco` no problema.
- `cwv-plano-acao.tsx` e `cwv-problema-detalhes.tsx`: badge "Esforço: baixo/médio/alto" (baixo=verde, médio=âmbar, alto=vermelho outline — distinto visualmente da severidade para não confundir).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Fonte | Mapa determinístico por kb_codigo | LLM por problema (custo/variância para classificação estável) — LLM ajusta só no consolidado (S8) |
| Localização | `priorizador.py` (nó determinístico de scoring) | Campo na KB YAML (esforço depende de plataforma/contexto menos que a solução; manter KB focada em conteúdo) |
| Escala | 3 níveis | T-shirt 5 níveis / horas (falsa precisão) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_priorizador.py -q
```

Estender `backend/tests/unit/test_cwv_priorizador.py`:
1. **Completude**: para cada `codigo` em `cwv_kb.carregar_kb().entradas`, `estimar_esforco(codigo, None)` retorna valor não-nulo (espelha o padrão do teste de completude de `AUDIT_METRICAS` em `test_cwv_documentador.py`).
2. Casos diretos: `imagens-formato-moderno`→baixo, `js-bundle-grande`→alto.
3. Fallback por família: `(None, "unused-javascript")`→alto; `(None, "audit-desconhecido-xyz")`→None.
4. `priorizar_problemas` popula `esforco` em todos os problemas (com e sem KB).
5. Persistência: problema antigo sem campo → `esforco=null` na serialização.

## 6. Não-objetivos

- Ajuste contextual do esforço por plataforma/evidências (LLM) — vai no consolidador (S8), que usa `max` dos grupos como base.
- Estimativa em horas/custo financeiro.

## 7. Avisos ao implementador

1. Migração `0025`: conferir a última migração real em `backend/migrations/versions/` antes de encadear `down_revision` (a série 0024-0028 está reservada, mas outra spec da onda pode não ter sido implementada ainda).
2. O mapa deve cobrir **todos** os códigos reais da KB — ler `app/data/cwv_knowledge_base.yaml` na implementação, não confiar apenas na lista desta spec (a KB pode ter ganhado entradas).
3. Não alterar a fórmula de prioridade existente (`severidade × Σ pesos`) — esforço é campo informativo nesta spec, não entra no score.
4. Testes sem rede/DB — funções puras.

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
