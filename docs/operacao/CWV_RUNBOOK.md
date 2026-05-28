# RUNBOOK — Ferramenta Core Web Vitals (CWV)

Operação dia-a-dia da ferramenta CWV em produção. Use isso quando algo der errado.

---

## Acesso rápido

| Recurso | Onde |
|---|---|
| Health check | `GET /api/admin/cwv/health` (header `X-Admin-Token: <token>`) |
| KB reload | `POST /api/admin/cwv/kb/reload` (header `X-Admin-Token: <token>`) |
| Métricas Prometheus | `GET /metrics` |
| Logs estruturados | `event_type=cwv.*` no agregador (ELK/Loki/Datadog) |
| LangSmith traces | projeto `seo-saas`, tag implícita |
| Postmortem de bugs | [`docs/specs/Ferramenta_CoreWebVitals/SPEC_CWV_Bugs_Postmortem.md`](../specs/Ferramenta_CoreWebVitals/SPEC_CWV_Bugs_Postmortem.md) |

---

## Métricas emitidas

| Métrica | Tipo | Quando incrementa | Use para |
|---|---|---|---|
| `cwv_psi_request_total{key_index, status}` | Counter | A cada chamada PSI (ok/429/network_error/etc) | Taxa de sucesso por key |
| `cwv_psi_quota_exhausted_total{key_index}` | Counter | Quando todas as keys PSI falham | **Alerta**: > 0 nas últimas 5min |
| `cwv_analise_duracao_seconds` | Histogram | Por URL analisada (sucesso ou falha) | p50/p95 de latência |
| `cwv_problemas_por_analise` | Histogram | Após persistir cada análise com sucesso | Distribuição de gravidade |
| `cwv_pesquisador_invocacoes_total` | Counter | A cada problema enviado ao pesquisador (gpt-4.1) | Custo LLM |
| `cwv_kb_miss_total{audit_id}` | Counter | Audit sem entrada na KB | Sinaliza qual audit adicionar na KB |
| `cwv_llm_tokens_total{agente, modelo, tipo}` | Counter | **TODO** — emissor não implementado, usar LangSmith por enquanto | Custo |
| `cwv_llm_custo_usd_total{agente, modelo}` | Counter | **TODO** — depende de tokens | Custo total |

---

## Cenários

### 🚨 Cliente diz "não está rodando minha análise"

1. `GET /api/admin/cwv/health` — verificar `status: ok|degraded|down`
   - `down` → keys PSI ambas indisponíveis (ver §"Cota PSI")
   - `degraded` → `taxa_sucesso < 0.8` nas últimas 24h, ou `openai_configured: false`
2. Verificar logs do worker arq por `event_type=cwv.psi.both_keys_failed`
3. Verificar fila Redis: `redis-cli LLEN arq:queue:default`
4. Se análise específica falhou: `SELECT * FROM cwv_analise WHERE id=...` — campo `erro_msg` tem a causa
5. Se status=`falhou_psi`: provavelmente cota — ver §"Cota PSI"
6. Se status=`falhou` com motivo_falha=`timeout`: site lento ou PSI lento — verificar `cwv_analise_duracao_seconds_bucket` no Prometheus

### 🚨 Cota PSI esgotada (alerta `cwv.psi.both_keys_failed`)

**Sintoma:** todas as análises retornam erro 429 ou similar.

**Causa típica:** quota diária da Google PSI API estourou (~25k requisições/dia por key gratuita).

**Mitigação imediata:**
1. Confirmar via log: `grep "cwv.psi.both_keys_failed" /var/log/app.log | tail`
2. Trocar `API_PSI_KEY` ou `API_PSI_KEY2` no .env por uma key reserva
3. Restart do worker arq (não precisa restart do uvicorn — o cliente PSI é stateless)
4. Anunciar no canal do cliente que análises foram retomadas

**Rotação de keys:**
- Gerar nova key em https://console.cloud.google.com → API Library → PageSpeed Insights
- Adicionar key restriction: HTTP referrer ou IP do servidor
- Atualizar `.env` (nunca commitar)
- Restart worker

**Long term:**
- Setup billing na Google Cloud — quota sobe pra 25k/100segundos
- Considerar `gPagespeed Insights` self-hosted (Lighthouse local em Docker)

### 🚨 Custos LLM altos no mês

**Sintoma:** fatura OpenAI explodiu.

**Causa típica:** pesquisador (gpt-4.1) chamado demais por análises com muitos audits sem KB.

**Diagnóstico:**
```bash
# Quantos audits sem KB nos últimos 7 dias?
psql -c "SELECT audit_id, COUNT(*) FROM cwv_problema 
         WHERE kb_codigo IS NULL AND criado_em > NOW() - INTERVAL '7 days' 
         GROUP BY audit_id ORDER BY 2 DESC LIMIT 20;"
```

**Mitigação:**
1. Adicionar entrada na KB para os audit_ids mais frequentes (PR em `backend/app/services/cwv_kb_data/`)
2. Atualizar `AUDIT_ALIASES` em `backend/app/services/cwv_kb.py` se for um insight novo do PSI mapeável para KB existente
3. Reload via `POST /api/admin/cwv/kb/reload`
4. Reduzir `CWV_PESQUISADOR_MAX_POR_ANALISE` no .env (default 5 → 3)

**Custo de referência (gpt-4.1):**
- Input: $5/1M tokens
- Output: $15/1M tokens
- Doc média do pesquisador: ~800 tokens output × $0.015/1k = ~$0.01/audit pesquisado

### 🚨 Erro 500 ao abrir análise antiga

**Causa típica:** schema desatualizado (analises gravadas com formato anterior).

**Como ver:** logs do uvicorn por `ValidationError`.

**Fix:** dependendo do erro, pode precisar:
- Migration nova para preencher coluna nullable
- Ajustar schema Pydantic para aceitar campo opcional
- Documentar como conhecido se análise for muito antiga

**Histórico:** ver `SPEC_CWV_Bugs_Postmortem.md`.

### 🚨 KB modificada, mas as análises novas não pegam a mudança

**Causa:** KB é cacheada em memória no worker.

**Fix:** `POST /api/admin/cwv/kb/reload` (afeta worker em curso). Para garantia, restart do worker arq.

### 🚨 Análise trava em "executando" sem nunca completar

**Causa típica:** worker arq morreu mid-flight ou checkpointer perdeu estado.

**Diagnóstico:**
```sql
SELECT id, status, timeout_em, criado_em FROM execucoes_ferramentas 
WHERE ferramenta='core_web_vitals' AND status='executando' 
AND criado_em < NOW() - INTERVAL '30 minutes';
```

**Fix:**
- Cancelar manualmente: `UPDATE execucoes_ferramentas SET status='falhou', erro_msg='Cancelada manualmente' WHERE id=...`
- Liberar reserva de créditos do usuário (consultar `credito_service.liberar_reserva`)
- Restart worker se múltiplas execuções travadas

---

## Smoke test pós-deploy

```bash
# 1. Health
curl -H "X-Admin-Token: $TOKEN" https://app/api/admin/cwv/health | jq .status
# espera: "ok"

# 2. KB carregada
curl -H "X-Admin-Token: $TOKEN" https://app/api/admin/cwv/health | jq '.kb.entries_loaded'
# espera: >= 50

# 3. Rodar análise teste (precisa user autenticado — pular se for via cron)
# Usar web.dev como URL canária — sempre passa cota
```

---

## Owner / escalation

| Tipo | Quem | Onde |
|---|---|---|
| Bug funcional | Backend dev de plantão | github issue |
| Cota PSI | Yan (owner) | Slack #seo-saas-ops |
| Custo LLM | Yan + financeiro | Slack #financeiro |
| Cliente reclamando | Suporte → backend | Linear "INGEST" project |

---

## Não-objetivos do RUNBOOK

- Tunning de prompts (responsabilidade da KB / SPEC #11)
- Adição de novos audits (PR no `cwv_kb_data/`)
- Performance do frontend (responsabilidade do time front)

---

**Última atualização:** 2026-05-28 (pós SPEC #18)
