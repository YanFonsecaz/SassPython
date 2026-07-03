# SPEC #2 — Expandir cobertura da KB CWV

**Status:** ✅ implementado · **Escopo:** backend (`data/cwv_knowledge_base.yaml`, script de auditoria, telemetria de KB miss)
**Dependências:** beneficia-se de [[SPEC_CWV_Analisador_Prompt_Enriquecido]] (prompt enriquecido reduz alguns gaps "por confusão", deixando só os gaps reais de cobertura).
**Esforço estimado:** ~1 dia (script + 15-20 entradas YAML + revisão técnica)
**Prioridade:** alta — ataca a causa-raiz da maioria das chamadas LLM no fallback.

## 1. Contexto e problema

A KB em `backend/app/data/cwv_knowledge_base.yaml` tem hoje **34 entradas** (`grep -c "^- codigo:"`). Cobertura analisada no DB local:

```
Top kb_codigos usados (analises de teste):
  5×  js-bundle-grande
  4×  js-execucao-pesada-no-load
  4×  event-handler-pesado
  4×  js-long-task
  4×  lcp-css-bloqueante
  4×  cls-imagem-sem-dimensoes-cls
  2×  outros            ← fallback
  ...

Audits que caíram em 'outros' (kb_miss):
  1× interactive            "Time to Interactive"
  1× speed-index            "Speed Index"
```

Achados:

- **Métricas agregadas tratadas como problema:** `interactive` (TTI) e `speed-index` são **scores resumo**, não problemas acionáveis. Não deveriam virar entrada de plano de ação. Hoje viram porque o fast-path não pega (não tem `audits_lighthouse` mapeado) e o LLM honestamente diz "outros".
- **Cobertura de audits Lighthouse incompleta:** o mapeamento `audits_lighthouse` por entrada cobre ~30-40% dos audits comuns do PSI. Lighthouse v11 tem ~100+ audits; a KB hoje mapeia em torno de 40. Audits frequentes faltando incluem: `lcp-lazy-loaded`, `non-composited-animations`, `script-treemap-data`, `bf-cache`, `mainthread-work-breakdown`, `bootup-time` (já existe? checar), `third-party-summary`, `third-party-facades`, `network-rtt`, `network-server-latency`, `redirects`, `uses-text-compression`, `efficient-animated-content`, `duplicated-javascript`, `legacy-javascript`.
- **Telemetria de miss não é consolidada:** `_emit_kb_miss` (`analisador.py:119-126`) loga via `logger.warning` mas ninguém consome esses logs para priorizar quais audits adicionar.

## 2. Solução

### 2.1 Script de auditoria de gaps

Criar `backend/scripts/cwv_kb_audit.py` que:

1. Consulta o DB (`cwv_problema` + `cwv_analise`):
   - Top N `audit_id` em problemas com `kb_codigo='outros'`.
   - Top N `audit_id` listados em `audits_origem` de QUALQUER `kb_codigo` (para validar se o mapping está coerente).
2. Lista audits Lighthouse padrão (lista fixa, conferida com docs `https://github.com/GoogleChrome/lighthouse/blob/main/docs/scoring.md`).
3. Cruza: imprime `audits sem mapeamento na KB ordenados por frequência`.
4. Output em Markdown na pasta `docs/specs/Ferramenta_CoreWebVitals/relatorios/cwv_kb_gaps_YYYY-MM-DD.md` para virar input do trabalho de expansão.

Modelo do output:

```markdown
# Auditoria de gaps da KB CWV — 2026-05-27

## Audits sem entrada na KB (por frequência nas análises últimos 90 dias)

| audit_id | ocorrências | título | severidade sugerida |
|---|---|---|---|
| third-party-summary | 18 | Third-party usage | 3 |
| mainthread-work-breakdown | 12 | Minimize main-thread work | 4 |
| ... |

## Audits da KB sem ocorrência (candidatos a remover ou KB-codigo deprecated)

| kb_codigo | audits_lighthouse mapeados |
|---|---|
| jekyll-something | [jekyll-x] |
```

### 2.2 Distinguir "métrica agregada" de "problema acionável"

`interactive` e `speed-index` são **resultados**, não problemas. O analisador não deveria empurrá-los para o plano de ação. Solução: adicionar set de **audits ignorados** em `services/cwv_kb.py`:

```python
AUDITS_IGNORADOS = {
    "interactive",
    "speed-index",
    "largest-contentful-paint",   # já é métrica top, não problema
    "cumulative-layout-shift",
    "first-contentful-paint",
    "experimental-interaction-to-next-paint",
    "total-blocking-time",
    "metrics",
    "diagnostics",
    "screenshot-thumbnails",
    "final-screenshot",
    "full-page-screenshot",
    "network-requests",
    "network-rtt",  # informativo
    "main-thread-tasks",  # raw data
}
```

E em `analisador.py:32` filtrar antes do fast-path:

```python
audits_falhos = [a for a in audits_falhos if a.get("id") not in AUDITS_IGNORADOS]
```

### 2.3 Adicionar entradas faltantes (mínimo 15)

Lista inicial proposta — cada uma vira uma entrada YAML completa em `cwv_knowledge_base.yaml` (com `solucoes.geral` + 1-2 plataformas relevantes):

| kb_codigo (novo) | audits_lighthouse | métricas | severidade | foco |
|---|---|---|---|---|
| `js-third-party-pesado` | `third-party-summary`, `third-party-facades` | INP, TBT, LCP | 5 | analytics/chat/ads pesados |
| `js-mainthread-bloqueada` | `mainthread-work-breakdown` | INP, TBT | 4 | breakdown por categoria |
| `js-bootup-pesado` | `bootup-time` | INP, TBT | 4 | tempo total de parse+exec |
| `js-duplicado` | `duplicated-javascript` | INP, TBT, FCP | 3 | bundling duplicado |
| `js-legacy-polyfills` | `legacy-javascript` | INP, TBT | 3 | ES5 servido p/ browsers modernos |
| `lcp-lazy-loaded-error` | `lcp-lazy-loaded` | LCP | 5 | imagem LCP com `loading="lazy"` |
| `bf-cache-nao-elegivel` | `bf-cache` | navegacao | 2 | back/forward cache |
| `imagens-formato-moderno` | `modern-image-formats`, `uses-webp-images` | LCP, transfer | 3 | WebP/AVIF |
| `imagens-tamanho-correto` | `uses-responsive-images`, `unsized-images` | LCP, CLS, transfer | 4 | srcset/sizes errado |
| `imagens-offscreen` | `offscreen-images` | LCP, transfer | 3 | lazy-loading correto |
| `compressao-texto-faltando` | `uses-text-compression` | TTFB, transfer | 4 | gzip/brotli |
| `redirects-encadeados` | `redirects` | TTFB, LCP | 3 | chain de 3xx |
| `cache-eficiente` | `uses-long-cache-ttl` | navegacao repetida | 2 | Cache-Control |
| `animacoes-nao-compositadas` | `non-composited-animations` | INP, CLS | 3 | animar `top/left` em vez de `transform` |
| `dom-profundidade-alta` | `dom-size` | INP | 3 | já existe `dom-muito-grande`? checar se cobre |
| `prioridade-recursos` | `prioritize-lcp-image`, `preload-lcp-image` | LCP | 4 | `<link rel=preload>` faltando |

### 2.4 Schema da entrada YAML (já existente, só lembrete)

Conforme `services/cwv_kb.py:20-35`:

```yaml
- codigo: js-third-party-pesado
  titulo: Scripts de terceiros consumindo muito tempo de execucao
  severidade: 5
  metricas_afetadas: [INP, TBT, LCP]
  audits_lighthouse:
    - third-party-summary
    - third-party-facades
  descricao: |
    Scripts de domínios externos (analytics, chat, ads, pixels) executam JavaScript
    pesado durante o carregamento, bloqueando o main thread e adiando interatividade.
  solucoes:
    geral: |
      - Auditar scripts terceiros e remover os não-essenciais
      - Carregar com `defer` ou `async` quando não-críticos
      - Usar Partytown para mover analytics para Web Worker
      - Substituir embeds (YouTube, Twitter) por facades clicáveis
    shopify: |
      - Revisar Shopify apps instalados — cada app injeta JS
      - Mover pixels não-críticos para `Customer events` (Web Pixels)
      - Avaliar uso de `liquid-app-block` em vez de scripts globais
    wordpress: |
      - Auditar plugins que injetam scripts no `<head>`
      - Usar plugin "Plugin Organizer" para desligar plugins por página
  links_referencia:
    - titulo: web.dev — Third-party JavaScript
      url: https://web.dev/articles/third-party-javascript
    - titulo: Partytown
      url: https://partytown.builder.io/
```

### 2.5 Endpoint admin para recarregar KB

Hoje `recarregar_kb()` existe em `services/cwv_kb.py:87` mas não é exposto. Adicionar `POST /api/admin/cwv/kb/reload` (gated por flag `settings.admin_endpoints_enabled`) para forçar reload sem restart do worker — útil em produção quando adicionamos entradas.

### 2.6 Teste de validação da KB

`backend/tests/unit/test_cwv_kb.py` (criar/expandir):

- Schema válido (Pydantic já garante).
- Toda entrada tem `solucoes.geral`.
- Códigos únicos (Pydantic já garante).
- **Novo:** todos `audits_lighthouse` mapeados são audits Lighthouse reais (cross-check com lista fixa).
- **Novo:** `links_referencia[].url` começa com `https://`.

## 3. Critérios de aceitação

1. **Script roda:** `python -m scripts.cwv_kb_audit` gera o relatório em `docs/.../relatorios/`.
2. **Audits ignorados:** após filtro, `interactive` e `speed-index` não aparecem mais como problemas no plano de ação.
3. **15+ entradas novas:** a KB sobe de 34 → 49+ entradas, todas validadas (`pytest -k cwv_kb`).
4. **Taxa de fallback → outros < 10%:** medir em 20 análises reais antes/depois.
5. **Endpoint reload:** `curl -X POST /api/admin/cwv/kb/reload` retorna `{"reloaded": true}` e a nova entrada vira disponível sem restart.

## 4. Arquivos afetados

- `backend/app/data/cwv_knowledge_base.yaml` — +15 entradas mínimo.
- `backend/app/services/cwv_kb.py` — `AUDITS_IGNORADOS`, talvez helper `is_audit_ignorado`.
- `backend/app/agents/cwv/analisador.py` — filtrar `AUDITS_IGNORADOS` antes do fast-path.
- `backend/scripts/cwv_kb_audit.py` (novo) — auditoria.
- `backend/app/routers/admin.py` (novo ou existente) — endpoint reload.
- `backend/tests/unit/test_cwv_kb.py` — testes adicionais.

## 5. Fora de escopo

- Não adicionar tools ao agente (vai em [[SPEC_CWV_Analisador_Tools_Pesquisa]] / [[SPEC_CWV_Analisador_Context7]]).
- Não trocar provider LLM.
- Não internacionalizar a KB — fica em PT-BR.

## 6. Riscos

- **Entradas mal redigidas:** soluções genéricas demais perdem o valor de plataforma-específico. Mitigação: revisão técnica por entrada antes de merge, e checklist no PR.
- **Filtro de `AUDITS_IGNORADOS` muito agressivo:** se filtrarmos um audit que algumas vezes é acionável, perdemos sinal. Mitigação: começar conservador (só métricas-resumo) e ampliar com base no script de auditoria.
