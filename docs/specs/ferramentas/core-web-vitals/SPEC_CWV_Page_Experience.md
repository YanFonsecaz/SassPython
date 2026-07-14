# SPEC — Page Experience: checagens por origem (HTTPS, SSL, redirects, headers, Safe Browsing, mobile-friendly)

**Status:** ✅ implementado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (nó novo no workflow, serviço, tabela) + frontend (seção na execução + etapa na barra de progresso)
**Código:** `backend/app/services/cwv_page_experience.py` (novo), `backend/app/models/cwv_page_experience.py` (novo), `backend/app/agents/cwv/workflow.py`, `backend/app/routers/ferramentas_cwv.py`, `backend/app/schemas/cwv.py`, `backend/app/config.py`, `backend/migrations/versions/0027_cwv_page_experience.py`, `frontend/src/components/cwv/cwv-execucao-client.tsx`, `frontend/src/lib/api/cwv.ts`  ·  **Rota:** `core-web-vitals`
**Créditos:** não cobra (decisão travada — sem mudança de billing)
**Depende de:** — (integra com `[[SPEC_CWV_Auditoria_Ciclo_De_Vida]]` quando ambas existirem)
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gaps #12-#15); aba `Checklist` linhas 9-18 da planilha NPBR

---

## 1. Contexto (por quê)

13 dos 49 itens do checklist da planilha NPBR são de **Page Experience**, não de PageSpeed: mobile-friendly, safe browsing, práticas de segurança, HTTPS, SSL, mixed content, redirect 301, pop-ups/interstitiais. A ferramenta não cobre nenhum. Esta spec cobre 7 deles com checagens determinísticas **por origem** (`scheme://host`) — não por URL, pois são propriedades do domínio. Pop-ups/interstitiais ficam para V3 (exigem análise visual). Sem GTmetrix (decisão travada).

## 2. Requisitos / Critérios de aceite

- [ ] Dado uma execução com 6 URLs de 2 origens distintas, quando o workflow roda, então `auditar_origem` executa 2 vezes (1 por origem) e a tabela `cwv_page_experience` ganha 2 linhas (UNIQUE `execucao_id, origem`).
- [ ] Dado uma origem cujo `http://` responde 302 (ou cadeia que não termina em https com 301), então `redirect_301='fail'` e `detalhes_json.redirect` traz a cadeia observada (status + location de cada salto, máx 5).
- [ ] Dado `settings.api_safe_browsing_key` vazio, então `safe_browsing='na'` e o workflow conclui normalmente.
- [ ] Dado um check que estoura o timeout individual (10s) ou lança exceção, então esse check fica `'erro'`, os demais completam e o workflow NUNCA falha por causa deste nó (fail-open).
- [ ] Dado um payload PSI cujo `network-requests` contém recurso `http://` numa página `https://`, então `mixed_content='fail'` com os recursos listados em `detalhes_json.mixed_content` (máx 10).
- [ ] Dado o audit `viewport` com score 1 em todas as análises mobile da origem, então `mobile_friendly='pass'`; score 0 em alguma → `'fail'`; audit ausente → `'na'`.
- [ ] Dado a execução concluída, quando `GET /core-web-vitals/execucao/{id}/page-experience`, então responde `{origens: [...]}` com os 7 vereditos + detalhes; e a tela da execução exibe a seção "Page Experience" com badges.
- [ ] Dado a execução em andamento, então os eventos `node_start`/`node_complete` do nó novo aparecem na barra de progresso (a UI de progresso renderiza os eventos SSE dinamicamente — basta o backend publicá-los com `detail` amigável em pt-BR).

## 3. Design (mapeado ao código)

### 3.1 Posição no grafo — `agents/cwv/workflow.py`

Novo nó **entre `coletar_psi` e `detectar_plataformas`**:

```
coletar_psi → coletar_page_experience → detectar_plataformas → analisar_seo → ...
```

Motivo: os checks de `mixed_content` e `mobile_friendly` leem o **payload bruto** (`network-requests`, audit `viewport`), e o payload é removido do estado dentro de `node_detectar_plataformas` (`psi_sem_payload`). Novo campo no `EstadoCWV`: `page_experience_por_origem: dict[str, dict]` (chave = `"https://host"`); inicializar `{}` no `estado_inicial` de `executar_workflow_cwv`.

`node_coletar_page_experience(estado)`:
- Deriva origens únicas de `estado["jobs"]` (`urllib.parse.urlsplit` → `f"{scheme}://{netloc.lower()}"`).
- Para cada origem, coleta os payloads OK daquela origem de `psi_resultados` e chama `auditar_origem(origem, payloads)`; origens em paralelo via `asyncio.gather`.
- Budget do nó: `asyncio.wait_for(..., timeout=90)` no gather; estouro → tudo que faltou vira `'erro'` (fail-open), log warning.
- Eventos: `publish_event(eid, "node_start", "coletar_page_experience", f"Verificando page experience de {n} origem(ns)...")` e `node_complete` com resumo (`X pass / Y fail / Z erro`).
- Registrar no grafo em `construir_workflow()` (add_node + reencadear edges).

### 3.2 Serviço — `services/cwv_page_experience.py` (novo)

```python
VEREDITOS = ("pass", "fail", "erro", "na")

async def auditar_origem(origem: str, payloads: list[dict]) -> dict
```

Retorna `{"https": v, "ssl": v, "redirect_301": v, "security_headers": v, "safe_browsing": v, "mixed_content": v, "mobile_friendly": v, "detalhes": {...}}`. Cada check com `asyncio.wait_for(..., 10)` individual e try/except → `'erro'`:

- `check_https(origem)`: GET `https://host` (httpx, `follow_redirects=True`, User-Agent de browser real — sites atrás de WAF bloqueiam UA de bot; usar algo como `Mozilla/5.0 ... Chrome/126`). 2xx/3xx → pass; erro TLS/conexão → fail.
- `check_ssl(host)`: handshake via `ssl` stdlib + `asyncio.open_connection` (ou `ssl.create_default_context` + socket em `asyncio.to_thread`): certificado válido, cadeia confiável, `notAfter` > agora + 14 dias (expirando em <14 dias → fail com detalhe). Hostname mismatch/expirado → fail.
- `check_redirect_301(origem)`: GET `http://host` com `follow_redirects=False`, seguir manualmente até 5 saltos registrando `(status, location)`. Pass sse o primeiro salto é 301 E a cadeia termina em URL `https://` com 2xx. 302/307 no primeiro salto → fail (a planilha exige 301 permanente).
- `check_security_headers(origem)`: nos headers da resposta https: `strict-transport-security` presente E (`content-security-policy` OU `x-frame-options`) E `x-content-type-options: nosniff`. Faltando algum → fail com a lista `presentes`/`ausentes` nos detalhes.
- `check_safe_browsing(origem)`: POST `https://safebrowsing.googleapis.com/v4/threatMatches:find?key={settings.api_safe_browsing_key}` com `threatTypes: [MALWARE, SOCIAL_ENGINEERING, UNWANTED_SOFTWARE]`, `threatEntries: [{url: origem}]`. Matches vazio → pass; com matches → fail (tipos nos detalhes). Sem key → `'na'` sem request.
- `check_mixed_content(payloads)`: sem rede — varre `lighthouseResult.audits["network-requests"].details.items` dos payloads; se a página final é https e existe item `url` começando com `http://` (excluindo `localhost`) → fail com até 10 URLs.
- `check_mobile_friendly(payloads)`: sem rede — audit `viewport` dos payloads de estratégia mobile (`lighthouseResult.configSettings.formFactor == "mobile"` ou pela estratégia do job): todo score==1 → pass; algum 0 → fail; ausente → na.

Config nova em `config.py`: `api_safe_browsing_key: str = ""` (junto das outras keys, após `api_psi_key2`).

### 3.3 Persistência — migração `0027_cwv_page_experience.py`

Tabela `cwv_page_experience` (`models/cwv_page_experience.py`): `id` UUID PK, `execucao_id` UUID FK `execucoes_ferramentas.id` ON DELETE CASCADE NOT NULL, `origem Text NOT NULL`, vereditos `https, ssl, redirect_301, security_headers, safe_browsing, mixed_content, mobile_friendly` (todos `String(10) NOT NULL default 'na'`), `detalhes_json JSONB NOT NULL server_default '{}'`, `criado_em`. UNIQUE `(execucao_id, origem)`; índice em `execucao_id`.

Gravação dentro do `node_persistir` existente (mesma sessão/commit): iterar `estado["page_experience_por_origem"]` e inserir. Nova função `persistir_page_experience(session, execucao_id, origem, resultado)` em `cwv_page_experience.py` ou `cwv_persistencia.py` (preferir `cwv_persistencia.py`, onde já vivem os writers).

### 3.4 API + frontend

- `GET /core-web-vitals/execucao/{execucao_id}/page-experience` em `ferramentas_cwv.py`: ownership 404; responde `PageExperienceListResponse` (`schemas/cwv.py`: `PageExperienceResposta` com os 7 campos `Literal["pass","fail","erro","na"]` + `origem` + `detalhes_json`).
- Barra de progresso: **nenhuma mudança estrutural necessária** — `cwv-execucao-client.tsx` e `hooks/use-execucao.ts` renderizam `etapa_atual`/`nodeHistory` dinamicamente a partir dos eventos SSE (`node_start`/`node_progress`/`node_complete`); o nó novo aparece automaticamente desde que `publish_event` seja chamado com `detail` em pt-BR.
- `cwv-execucao-client.tsx`: seção "Page Experience" (após conclusão): por origem, 7 badges (pass verde, fail vermelho, erro âmbar "inconclusivo", na cinza) com tooltip dos detalhes. Client API: `buscarPageExperienceCwv(execucaoId)` em `lib/api/cwv.ts`.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Granularidade | Por origem (propriedades do domínio) | Por URL (7 checks × 50 URLs × 2 = desperdício e rate-limit) |
| Posição no grafo | Antes do strip do payload | Nó paralelo/fan-out LangGraph (complexidade de checkpointer sem ganho) |
| Fonte dos checks | Requests próprios + payload PSI | GTmetrix (decisão travada: fora) e Lighthouse `best-practices` (2ª chamada PSI por URL dobraria quota) |
| Bloqueio por WAF | Veredito `'erro'` (inconclusivo), nunca `'fail'` | Marcar fail (falso positivo destrói confiança do relatório) |
| Pop-ups/interstitiais | Fora (V3, LLM vision + revisão humana) | Heurística por DOM (precisão baixa) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_page_experience.py -q
```

Novo `backend/tests/unit/test_cwv_page_experience.py` (padrão `test_cwv_psi_client.py`: monkeypatch/AsyncMock em httpx, zero rede real):
1. Dedup de origens: 6 jobs / 2 origens → 2 chamadas de `auditar_origem`.
2. `check_redirect_301`: cadeia `301→https 200` → pass; `302→...` → fail com cadeia nos detalhes; loop >5 saltos → fail.
3. `check_mixed_content`: payload com recurso http → fail listando; sem recursos http → pass.
4. `check_mobile_friendly`: viewport score 1 → pass; 0 → fail; ausente → na.
5. `check_safe_browsing`: sem key → na (nenhum request feito — assert no mock); matches → fail.
6. Fail-open: check que lança → `'erro'`, demais completam.
7. `check_security_headers`: com HSTS+CSP+nosniff → pass; sem HSTS → fail com `ausentes`.

E2E manual: `make dev`, rodar análise de site real, conferir seção Page Experience e linha na tabela.

## 6. Não-objetivos

- Pop-ups/interstitiais/ads intrusivos (V3 — Inspetor Visual).
- Práticas de segurança além de headers (senhas, backups, WAF — não verificável externamente).
- Re-checagem standalone fora de uma execução CWV.
- Cobrança extra por check (decisão travada).

## 7. Avisos ao implementador

1. **O payload PSI só existe no estado antes de `node_detectar_plataformas`** — este nó DEVE ficar entre `coletar_psi` e `detectar_plataformas`; não mover.
2. Budget: nó completo ≤ 90s (timeout global do workflow é 1200s para até 100 jobs — não pressionar).
3. Fail-open em TUDO: nenhuma exceção deste nó pode derrubar o workflow (envolver o corpo do nó em try/except com log + vereditos `'erro'`).
4. A barra de progresso do frontend é dinâmica (eventos SSE) — não existe lista estática de etapas para atualizar; basta publicar os eventos do nó novo.
5. Eventos SSE via `app/core/workflow_events.py::publish_event(execucao_id, event_type, node, detail)` — mesmo padrão dos nós existentes.
6. Ownership 404 no endpoint novo.
7. Migração `0027`: conferir a última migração real antes de encadear.
8. User-Agent de browser nos requests próprios (WAFs bloqueiam UA custom); `follow_redirects=False` no check de redirect (controle manual da cadeia).

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
