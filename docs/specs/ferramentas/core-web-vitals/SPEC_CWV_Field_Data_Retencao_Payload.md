# SPEC — Field data CrUX + retenção de resumo do payload PSI

**Status:** ✅ implementado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (parse, modelo, persistência, schema) + frontend (tiles CrUX)
**Código:** `backend/app/services/cwv_psi_client.py`, `backend/app/models/cwv_analise.py`, `backend/app/services/cwv_persistencia.py`, `backend/app/schemas/cwv.py`, `backend/migrations/versions/0024_cwv_field_data_raw_resumo.py`, `frontend/src/components/cwv/cwv-metricas-resumo.tsx`, `frontend/src/types/cwv.ts`, `frontend/src/lib/api/cwv.ts`  ·  **Rota:** `core-web-vitals`
**Créditos:** não cobra (sem mudança de billing)
**Depende de:** —
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gaps #5, #6)

---

## 1. Contexto (por quê)

O critério nº 1 da auditoria da planilha NPBR é "a página passa no assessment de LCP/INP/CLS?" — que vem dos **dados de campo do CrUX** (usuários reais), não do laboratório. O payload da API PSI **já contém** esses dados (`loadingExperience` por URL e `originLoadingExperience` por origem), mas `parse_psi` os descarta e `persistir_analise` grava `raw_psi_json={}`. Hoje a ferramenta só reporta lab data.

Esta spec faz o parse reter: (a) o field data CrUX materializado em colunas para exibição e query; (b) um resumo compacto do payload (`raw_resumo_json`) que habilita specs futuras (checklist Pass/Fail completo precisa do score de TODOS os audits, não só dos falhos).

## 2. Requisitos / Critérios de aceite

- [ ] Dado um payload PSI com `loadingExperience.metrics`, quando `parse_psi` roda, então o dict retornado contém `crux_lcp_p75_ms`, `crux_inp_p75_ms`, `crux_cls_p75`, `crux_lcp_categoria`, `crux_inp_categoria`, `crux_cls_categoria`, `crux_overall_categoria` (valores `FAST|AVERAGE|SLOW`), `crux_origem_fallback=False` e a chave `resumo` (dict).
- [ ] Dado payload **sem** `loadingExperience` mas **com** `originLoadingExperience`, quando parseado, então os campos `crux_*` vêm da origem e `crux_origem_fallback=True`.
- [ ] Dado payload sem field data algum (site de baixo tráfego), quando a análise é persistida, então todos os `crux_*` são `NULL`, `raw_resumo_json.audits_score_map` existe mesmo assim, e o `GET /core-web-vitals/analise/{id}` responde `field_data_disponivel=false`.
- [ ] Dado o `resumo` gerado, então ele NUNCA contém `final-screenshot`, `full-page-screenshot`, `screenshot-thumbnails` nem `details.items` de nenhum audit; e `len(json.dumps(resumo))` ≤ 64_000 caracteres (truncar defensivamente removendo `entities` e depois `audits_score_map` se exceder).
- [ ] Dado uma análise antiga (pré-migração), quando `GET /core-web-vitals/analise/{id}` responde, então os campos novos vêm `null`/`{}` sem erro 500.
- [ ] Dado uma análise com field data, quando a página `url/[analiseId]` renderiza, então há uma seção "Dados de campo (CrUX)" com badge de categoria por métrica; sem field data, a seção mostra o aviso "Sem dados de campo para esta página — avaliação baseada em testes de laboratório".

## 3. Design (mapeado ao código)

### 3.1 Parse (`cwv_psi_client.py::parse_psi`)

O payload PSI tem, no nível raiz (irmão de `lighthouseResult`):

```json
"loadingExperience": {
  "metrics": {
    "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2244, "category": "AVERAGE", "distributions": [...]},
    "INTERACTION_TO_NEXT_PAINT":   {"percentile": 175,  "category": "FAST", ...},
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 4, "category": "FAST", ...}
  },
  "overall_category": "AVERAGE"
},
"originLoadingExperience": { ...mesmo formato... }
```

Atenção: `CUMULATIVE_LAYOUT_SHIFT_SCORE.percentile` vem multiplicado por 100 (ex.: `4` = CLS 0.04) — dividir por 100 ao materializar `crux_cls_p75`. `INTERACTION_TO_NEXT_PAINT` pode estar ausente em payloads antigos; nesse caso o campo fica `None` (não usar `EXPERIMENTAL_*`).

Adicionar ao dict retornado por `parse_psi`:
- `crux_*` (7 campos acima + `crux_origem_fallback: bool`) — extraídos com helper interno `_extrair_field_data(payload) -> dict`, que tenta `loadingExperience` e cai para `originLoadingExperience` (marcando fallback). Se nenhum tem `metrics` não-vazio, todos `None` e fallback `False`.
- `resumo: dict` com as chaves:
  - `loading_experience`: o objeto `loadingExperience` completo (ou `None`),
  - `origin_loading_experience`: idem,
  - `audits_score_map`: `{audit_id: score}` para todo audit com `score is not None` (sem filtrar por 0.9 — inclui os saudáveis; é o que permite montar checklist Pass/Fail completo depois),
  - `stack_packs`: lista de `id` de `lighthouseResult.stackPacks` (só nomes),
  - `entities`: lista de `name` de `lighthouseResult.entities` (só nomes, máx 30),
  - `lighthouse_version`: `lighthouseResult.lighthouseVersion`,
  - `fetch_time`: `lighthouseResult.fetchTime`,
  - `form_factor`: `lighthouseResult.configSettings.formFactor` (se houver).

### 3.2 Modelo e migração

`backend/app/models/cwv_analise.py` — novas colunas (todas NULLABLE exceto onde indicado):

| Coluna | Tipo |
|---|---|
| `raw_resumo_json` | `JSONB NOT NULL server_default '{}'::jsonb` |
| `crux_lcp_p75_ms` | `Numeric(10,2)` |
| `crux_inp_p75_ms` | `Numeric(10,2)` |
| `crux_cls_p75` | `Numeric(6,4)` |
| `crux_lcp_categoria` | `String(20)` |
| `crux_inp_categoria` | `String(20)` |
| `crux_cls_categoria` | `String(20)` |
| `crux_overall_categoria` | `String(20)` |
| `crux_origem_fallback` | `Boolean NOT NULL server_default 'false'` |

Migração `backend/migrations/versions/0024_cwv_field_data_raw_resumo.py` (conferir antes qual é a última migração real no diretório e encadear `down_revision` nela; na escrita desta spec a última é `0023_indices_site_conteudos_cliente.py`). Só `op.add_column` em `cwv_analise`; `downgrade` remove as 9 colunas.

### 3.3 Persistência e API

- `cwv_persistencia.py::persistir_analise`: no branch de sucesso, popular as novas colunas a partir de `parsed` (`raw_resumo_json=parsed.get("resumo", {})`, `crux_*=parsed.get("crux_*")`). No branch `falhou_psi`, deixar defaults.
- `cwv_persistencia.py::_analise_to_dict`: serializar os `crux_*` (float/str/None), `crux_origem_fallback` e `field_data_disponivel` (derivado: `crux_overall_categoria is not None` ou qualquer `crux_*_categoria` não-nulo). **Não** serializar `raw_resumo_json` inteiro na resposta padrão (payload de API menor); expor apenas os derivados.
- `schemas/cwv.py::AnaliseResposta`: adicionar os campos `crux_lcp_p75_ms: float | None`, `crux_inp_p75_ms: float | None`, `crux_cls_p75: float | None`, `crux_lcp_categoria: str | None`, `crux_inp_categoria: str | None`, `crux_cls_categoria: str | None`, `crux_overall_categoria: str | None`, `crux_origem_fallback: bool = False`, `field_data_disponivel: bool = False`.

### 3.4 Frontend

- `frontend/src/types/cwv.ts` + `frontend/src/lib/api/cwv.ts::CwvAnaliseResposta`: espelhar os campos novos.
- `frontend/src/components/cwv/cwv-metricas-resumo.tsx`: nova subseção "Dados de campo (CrUX — usuários reais)" acima ou ao lado dos tiles de lab existentes. Por métrica (LCP/INP/CLS): valor p75 formatado + badge de categoria (FAST=verde, AVERAGE=âmbar, SLOW=vermelho — usar os mesmos tokens de cor dos tiles de classificação existentes). Se `crux_origem_fallback`, exibir nota "dados da origem (domínio), não desta URL específica". Se `!field_data_disponivel`, exibir o aviso de fallback lab (critério de aceite 6).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Armazenamento do payload | Resumo compacto (5–15KB) em `raw_resumo_json` novo | Guardar payload inteiro (500KB–2MB por análise) ou reutilizar `raw_psi_json` (coluna legada `{}` NOT NULL, referenciada em specs históricas — não tocar) |
| Screenshot | **Descartar** `final-screenshot` (base64 50–150KB) | Guardar no Postgres — incha TOAST ×2 estratégias ×N URLs; se o Inspetor Visual (V3) precisar, será object storage |
| Field data na resposta | Colunas materializadas | Parse de JSONB no frontend (frágil, sem índice) |
| INP ausente | Campo `None` | Usar `EXPERIMENTAL_INTERACTION_TO_NEXT_PAINT` (obsoleto) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_psi_client.py -q
.venv/bin/alembic upgrade head   # com Postgres local (make dev)
```

Testes a escrever em `tests/unit/test_cwv_psi_client.py` (seguir o padrão existente de payloads dict inline):
1. `test_parse_psi_field_data_url_level` — payload com `loadingExperience` completo → `crux_*` corretos, CLS dividido por 100, `crux_origem_fallback=False`.
2. `test_parse_psi_field_data_fallback_origem` — só `originLoadingExperience` → valores da origem, fallback `True`.
3. `test_parse_psi_sem_field_data` — nenhum → todos `None`, `resumo.audits_score_map` presente.
4. `test_parse_psi_resumo_sem_screenshot` — payload com `final-screenshot`/`full-page-screenshot` nos audits → `resumo` não contém nenhuma string base64 (assert substring `data:image` ausente no `json.dumps(resumo)`).
5. `test_parse_psi_resumo_cap_tamanho` — payload inflado → `len(json.dumps(resumo)) <= 64_000`.

E2E manual: rodar análise em site com tráfego (ex.: grande e-commerce) → tiles CrUX aparecem; site pequeno → aviso de fallback lab.

## 6. Não-objetivos

- CrUX History API (evolução 25 semanas) — V2, ver README.
- Exibir screenshot na UI — descartado nesta fase (ver Decisões).
- Usar field data no health score ou no checklist — specs `SPEC_CWV_Health_Score` e `SPEC_CWV_Auditoria_Ciclo_De_Vida` consomem o que esta spec produz.
- Backfill de análises antigas (ficam com campos `null`).

## 7. Avisos ao implementador

1. **`raw_psi_json` é `{}` NOT NULL e NÃO deve ser reutilizado** — criar `raw_resumo_json` novo com `server_default`.
2. **O payload bruto é removido do estado do workflow em `node_detectar_plataformas`** (`workflow.py`, `psi_sem_payload`). Tudo desta spec acontece dentro de `parse_psi` (que roda no `node_coletar_psi`), então o `resumo` viaja dentro de `parsed` e sobrevive ao strip. Não devolver `payload` de nenhum nó.
3. Migração: conferir `ls backend/migrations/versions/` e encadear `down_revision` na última migração **real** (pode ter avançado além de 0023).
4. Testes sem rede real (payloads dict inline, padrão `test_cwv_psi_client.py`).
5. Frontend usa export estático (`output: "export"`): componentes leem o id da URL via `usePathname()`, nunca `useParams()` — padrão já usado em `cwv-url-client.tsx`.

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
| 2026-07-14 | Revisão: migração 0024 corrigida para JSONB (era sa.JSON); server_default dos models JSONB normalizados para o padrão da casa (`"{}"`) | — |
