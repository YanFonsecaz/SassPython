# POSTMORTEM — E2E com sites reais (SPEC #18 F2)

**Data:** 2026-05-28
**Responsável:** validação pré-produção
**Escopo:** rodar ferramenta CWV contra 3 URLs reais (1 marketplace, 1 e-commerce, 1 plataforma WordPress) e documentar achados.

---

## Resumo executivo

| Site | URL | Plataforma detectada | Score | Problemas | Críticos | sem_kb | pesquisados | Status |
|---|---|---|---|---|---|---|---|---|
| OLX (marketplace) | `https://www.olx.com.br/` | `nextjs` ✅ | 51 | 18 | 9 | 0 | 0 | ✅ sucesso |
| Magazine Luiza (e-commerce) | `https://www.magazineluiza.com.br/` | `nextjs` ✅ | 32 | 23 | 15 | 0 | 0 | ✅ sucesso (após fix bug 5) |
| WordPress.com (plataforma WP) | `https://wordpress.com/` | `wordpress` ✅ | 52 | 19 | 9 | 2 | 2 | ✅ sucesso |

**Conclusão:** 3/3 sites passaram pelo pipeline completo. Detecção de plataforma correta nos 3. Pesquisador disparou em audits sem KB curada (WordPress). KB curada cobriu 100% no caso brasileiro Next.js (OLX/Magalu).

---

## Bug encontrado e corrigido durante o E2E

### Bug #5 — `_resumir_items` quebrava com items não-dict

**Sintoma:** Magalu primeira tentativa falhou com `AttributeError: 'str' object has no attribute 'get'`.

**Causa raiz:** alguns audits do Lighthouse (`network-rtt`, `network-server-latency`) retornam `details.items` como **lista de strings ou números**, não dicts. Antes do SPEC #18 isso passava despercebido porque o slice `items[:5]` mascarava — agora sem limite, qualquer audit pode disparar.

**Fix:** guarda `if not isinstance(it, dict): continue` em `_resumir_items` no `app/agents/cwv/analisador.py:182`.

**Test de regressão:** `tests/cwv/test_regressions_e2e.py::test_bug5_resumir_items_ignora_itens_nao_dict`.

---

## Achados por site

### 1. OLX — `https://www.olx.com.br/` → análise `1a38bea1-7314-464d-b425-1174959111a6`

**Plataforma:** `nextjs` (detectada corretamente — Next.js + React).

**Métricas:**
- Score: 51 (precisa melhorar)
- LCP: 5.5s (ruim)
- CLS: 0.000 (bom)
- INP: 193ms (bom)
- TBT: 580ms (precisa melhorar)

**18 problemas identificados (9 críticos):** todos com KB curada via aliases (`image-delivery-insight`, `cache-insight`, `render-blocking-insight`, `font-display-insight`, `legacy-javascript-insight`, etc.).

**Destaque — `legacy-javascript-insight` com sub-items aninhados:**
```
connect.facebook.net/...    22.5 KiB
↳ @babel/plugin-transform-classes
↳ @babel/plugin-transform-regenerator
↳ Array.from
↳ Array.isArray
↳ Object.create
↳ Object.entries
... (18 polyfills no total)
```

Renderização da UI **idêntica à do PSI** (validado contra screenshot do usuário).

**Destaque — `cache-insight` com 58 recursos:** mais que web.dev (4) ou Wikipedia (4). Botão "Ver todos os 58 recursos" funcional.

**`metric_savings` populado:**
- `legacy-javascript-insight`: LCP −150ms
- `cache-insight`: LCP −300ms (e outras métricas)

### 2. Magazine Luiza — `https://www.magazineluiza.com.br/` → análise `cb255663-ed29-491a-867b-4920191eacbe`

**Plataforma:** `nextjs` (detectada corretamente — Magalu usa stack Next.js).

**Métricas:**
- Score: 32 (ruim)
- LCP: **16.5s (péssimo)** — site pesado em mobile
- CLS: 0.111 (precisa melhorar)
- INP: 548ms (ruim)

**23 problemas, 15 críticos, 0 sem KB.**

**Confirmação:** soluções específicas Next.js renderizadas no plano de ação (`React.lazy`, `next/dynamic`, `next/image`, `startTransition`).

### 3. WordPress.com — `https://wordpress.com/` → análise `657389b1-7993-4cbe-8082-76c51eab2f33`

**Plataforma:** `wordpress` ✅ (detectada corretamente — `meta generator` + WP-specific routes).

**Métricas:**
- Score: 52 (precisa melhorar)
- LCP: 11.9s (péssimo)
- CLS: 0.000 (bom)
- INP: 382ms (precisa melhorar)

**19 problemas, 9 críticos, 2 sem KB, 2 pesquisados em tempo real.**

**Destaque — pesquisador disparou para audits sem KB:**

`forced-reflow-insight` → pesquisador gerou doc curada em PT-BR explicando offsetWidth/offsetHeight:
> "O 'forced reflow' ocorre quando scripts JavaScript consultam propriedades geométricas do DOM (como `offsetWidth` ou `offsetHeight`) após alterações que invalidam o estilo da página..."

`network-dependency-tree-insight` → pesquisador gerou doc **WordPress-aware**:
> "...há cadeias de solicitações críticas (critical request chains) na sua página WordPress. Isso significa que arquivos essenciais como CSS e JS estão sendo carregados em sequência..."

Confirma que `cwv_pesquisador_max_por_analise=5` (default) está suficiente para sites reais. `gpt-4.1` produzindo docs de qualidade pra audits raros.

---

## Estatísticas agregadas dos 3 sites

| Métrica | Valor |
|---|---|
| Total problemas identificados | 60 |
| % com KB curada (direta ou via alias) | 96.6% (58/60) |
| Audits que precisaram do pesquisador | 2 (3.3%) |
| Detecção de plataforma correta | 3/3 (100%) |
| `metric_savings` populado em audits opportunity | ✅ todos |
| Sub-items aninhados renderizados (legacy-javascript) | ✅ OLX |
| Tempo médio de análise | ~70s (sem PSI lento) |
| Análises que precisaram retry | 1/3 (Magalu, devido bug 5) |

---

## Gaps identificados (não-bloqueantes)

### Alta severidade

Nenhum — fluxo completo funcional.

### Média severidade

| Gap | Onde | Recomendação |
|---|---|---|
| Coluna "Recurso" como `—` ainda em alguns audits sem `url`/`group_label` (ex: `forced-reflow-insight` antes da SPEC #18 promover `group_label`) | UI plano de ação | Verificar todos os audits sem URL — fallback para `source` ou `signal` |
| `metric_savings` desabilitado quando vem `{"LCP": 0, "FCP": 0}` (filtro `v !== 0`) | `cwv-problema-detalhes.tsx:173` | Considerado correto — apenas valores positivos |

### Baixa severidade

| Gap | Recomendação |
|---|---|
| Pesquisador usa `gpt-4.1` (caro) para apenas 2 audits raros | Considerar gpt-4.1-mini para reduzir custo |
| `network-rtt`, `network-server-latency` ignorados via filtros | OK — métricas técnicas que não viram plano |
| Sites SPA muito otimizados (Wikipedia) mostram só métricas-info | OK — esperado |

---

## Recomendações pós-postmortem

1. ✅ **Bug 5 corrigido** + regression test adicionado
2. ✅ **3 sites reais validados** — atende critério F2 da SPEC #18
3. ⏭️ **Capturar fixtures PSI JSON** dos 3 sites pra testes futuros (TODO — não bloqueante)
4. ⏭️ **Monitorar custo do pesquisador** em produção via métricas `cwv_pesquisador_invocacoes_total` (ver `CWV_RUNBOOK.md`)
5. ⏭️ **Adicionar entradas KB** para os 2 audits que disparou pesquisador, se ficarem frequentes em produção:
   - `forced-reflow-insight`
   - `network-dependency-tree-insight`

---

## Status para produção

Pelo critério "5 URLs em uma execução completam em <5min" da SPEC original:
- ❓ Não testado nesta rodada (rodei 1 URL por vez para diagnosticar). **TODO antes do go-live.**

Pelo critério F2 desta SPEC #18:
- ✅ "3 análises reais documentadas em postmortem" → **atende**.

**Recomendação:** após carga test com 5 URLs simultâneas e validação dos critérios remanescentes (F1 testes ≥70% cobertura, F3 RUNBOOK testado, F4 0 console errors), ferramenta cleared para self-service público.

---

**Tempo total da validação:** ~30 min
**Bugs encontrados/corrigidos durante o E2E:** 1 (bug 5)
**Análises perdidas por erro de código:** 1 (Magalu round 1)
**Análises perdidas por cota PSI:** 0
**Pipeline E2E end-to-end provado:** ✅ funcional para marketplace, e-commerce e plataforma WP
