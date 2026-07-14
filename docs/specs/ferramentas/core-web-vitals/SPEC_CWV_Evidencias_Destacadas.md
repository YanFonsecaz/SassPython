# SPEC — Evidências destacadas com thresholds (paridade com as abas de problema)

**Status:** ✅ implementado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (mapa de thresholds + export) e frontend (seção Evidências)
**Código:** `backend/app/services/cwv_export.py`, `backend/app/schemas/cwv.py`, `frontend/src/components/cwv/cwv-problema-detalhes.tsx`  ·  **Rota:** `core-web-vitals`
**Créditos:** não cobra
**Depende de:** —
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gap #5); abas ocultas da planilha NPBR (ex.: "Avoid Long Tasks on the Main Thread")

---

## 1. Contexto (por quê)

Nas abas de problema da planilha NPBR, a tabela de evidências traz o **threshold no cabeçalho** — ex.: `Task Duration (< 100 ms per task)`, `Total CPU Time (< 200 ms)` — para o cliente entender de imediato o quão longe cada recurso está do ideal. A ferramenta já persiste as evidências (`cwv_problema.contexto_especifico.items`, extraídas em `agents/cwv/analisador.py::_resumir_items`), mas as renderiza como tabela genérica "Recurso/Detalhe/Desperdiçado/Total", sem referência de meta e sem destaque na UI.

## 2. Requisitos / Critérios de aceite

- [ ] Dado um problema com `audit_id="long-tasks"` e items, quando renderizado na UI e no DOCX, então o bloco de evidências exibe o threshold "< 100 ms por tarefa" no cabeçalho.
- [ ] Dado um audit sem entrada no mapa de thresholds, então a tabela renderiza com cabeçalho genérico, sem threshold e sem erro.
- [ ] Dado um problema sem `items`, então a seção Evidências não aparece (nem título vazio).
- [ ] Dado items com apenas `label`/`snippet` (sem `url`), então a linha renderiza usando os fallbacks existentes, sem célula "None".
- [ ] Dado a UI do problema (`cwv-problema-detalhes.tsx`), então existe uma seção "Evidências" ANTES de "Como corrigir", com linhas ordenadas por desperdício (`wastedMs` ou `wastedBytes`, decrescente).

## 3. Design (mapeado ao código)

### 3.1 Mapa de thresholds — `cwv_export.py`

Novo dict módulo-level (determinístico, valores em pt-BR — fonte: documentação Lighthouse/web.dev e cabeçalhos da planilha NPBR):

```python
THRESHOLDS_POR_AUDIT: dict[str, str] = {
    "long-tasks": "< 100 ms por tarefa",
    "mainthread-work-breakdown": "< 2 s de trabalho na main thread",
    "bootup-time": "< 2 s de execução de JS",
    "total-blocking-time": "TBT < 200 ms",
    "server-response-time": "TTFB < 600 ms",
    "render-blocking-resources": "0 recursos bloqueantes",
    "unused-javascript": "desperdício < 20 KB por arquivo",
    "unused-css-rules": "desperdício < 20 KB por arquivo",
    "uses-long-cache-ttl": "TTL de cache ≥ 30 dias",
    "total-byte-weight": "página < 1,6 MB",
    "dom-size": "< 800 nós no DOM",
    "third-party-summary": "bloqueio por terceiros < 250 ms",
    "largest-contentful-paint": "LCP < 2,5 s",
    "cumulative-layout-shift": "CLS < 0,1",
    "interaction-to-next-paint": "INP < 200 ms",
    "first-contentful-paint": "FCP < 1,8 s",
    "modern-image-formats": "imagens em WebP/AVIF",
    "uses-optimized-images": "0 KB de desperdício por compressão",
    "uses-responsive-images": "imagem ≤ tamanho exibido",
    "offscreen-images": "imagens fora da tela com lazy load",
    "unminified-javascript": "JS minificado (0 KB de desperdício)",
    "unminified-css": "CSS minificado (0 KB de desperdício)",
    "uses-text-compression": "compressão gzip/brotli ativa",
    "redirects": "0 redirecionamentos encadeados",
    "critical-request-chains": "cadeias críticas curtas (≤ 2 níveis)",
    "layout-shifts": "nenhum shift > 0,05",
    "legacy-javascript": "0 polyfills desnecessários",
    "duplicated-javascript": "0 módulos duplicados",
    "efficient-animated-content": "vídeo no lugar de GIF",
    "font-display": "font-display: swap/optional",
    "prioritize-lcp-image": "imagem LCP com fetchpriority=high",
    "lcp-lazy-loaded": "imagem LCP sem lazy load",
    "unsized-images": "width/height explícitos em todas as imagens",
}

def threshold_do_audit(audit_id: str | None) -> str | None: ...
```

Aplicar aliases: reusar `app/services/cwv_kb.py::AUDIT_ALIASES` para resolver ids `-insight` antes do lookup.

### 3.2 Renderização backend (DOCX)

- `_tabela_recursos(items)` ganha parâmetro opcional `audit_id: str | None = None`; quando o threshold existe, o título da tabela vira parágrafo `<p><strong>Evidências</strong> — meta: {threshold}</p>` antes do `<table data-causas>`; ordenar `items` por `wastedMs`/`wastedBytes` decrescente antes de truncar.
- `problema_para_html` e `relatorio_para_html` passam `audit_id` do problema (`p["audit_id"]` ou `ctx["audit_id"]`).

### 3.3 API e frontend

- `schemas/cwv.py::ProblemaResposta`: novo campo derivado `threshold: str | None = None` — populado em `cwv_persistencia._analise_to_dict` chamando `threshold_do_audit` (import de `cwv_export`; se preferir evitar import cruzado, mover mapa+helper para `app/services/cwv_kb.py` — decisão do implementador, registrar no Histórico).
- `frontend/src/components/cwv/cwv-problema-detalhes.tsx`: seção "Evidências" (título + badge "meta: {threshold}") renderizando os items (`contexto_especifico.items`) em tabela: Recurso (url/label/selector truncado), Desperdício (`wastedMs`→ms, `wastedBytes`→KB), Total. Ordenada por desperdício; máx 10 linhas + contagem do restante. Só renderiza se `items.length > 0`.
- `frontend/src/lib/api/cwv.ts` / `types/cwv.ts`: campo `threshold` no tipo do problema.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Fonte dos thresholds | Mapa determinístico curado em código | LLM por problema (custo/variância para dado fixo) ou coluna na KB YAML (thresholds são por audit, não por entrada KB — várias entradas compartilham audit) |
| Idioma | pt-BR direto no mapa | i18n (produto é pt-BR) |
| Ordenação | Por desperdício decrescente | Ordem original do Lighthouse (esconde os piores) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_export_evidencias.py tests/test_cwv_export.py -q
```

Novo `backend/tests/unit/test_cwv_export_evidencias.py`:
1. `threshold_do_audit("long-tasks")` → "< 100 ms por tarefa"; audit desconhecido → `None`; alias `-insight` resolve.
2. HTML de problema `long-tasks` com items contém "meta:" e o threshold.
3. Problema sem items → HTML sem seção de evidências.
4. Items ordenados por `wastedMs` decrescente no HTML gerado.
5. Cobertura: todo `audit_id` listado em `cwv_kb.py::AUDIT_ALIASES` (valores) tem lookup sem exceção (não precisa ter threshold, só não pode quebrar).

Frontend: teste existente de `cwv-problema-detalhes` (há `__tests__/` em `components/cwv`) ganha caso com/sem items.

## 6. Não-objetivos

- Estratégia de correção **por recurso** (coluna "Strategies" da planilha) — roadmap V2 (recomendação personalizada com recursos nomeados).
- Alterar `_resumir_items` do analisador (a extração atual já é suficiente).

## 7. Avisos ao implementador

1. Tabelas no DOCX sempre via `_html_table` (`<table data-causas>`) — markdown solto é descartado pelo parser de `html_para_docx_bytes`.
2. Não quebrar os testes existentes de `tests/test_cwv_export.py` (a tabela genérica atual continua sendo o fallback sem threshold).
3. `items` tem formatos heterogêneos por audit — usar exatamente os fallbacks de chave já existentes em `_tabela_recursos` (`url|label`, `wastedBytes|wastedMs`, `totalBytes|totalMs`).
4. Frontend com export estático: sem novas rotas dinâmicas nesta spec; apenas componente.

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
