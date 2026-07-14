# SPEC — Re-auditoria AFTER: fechar o ciclo da campanha

**Status:** 📋 planejado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (endpoint, hook no workflow, service) e frontend (CTA + colunas before/after)
**Código:** `backend/app/routers/ferramentas_cwv_auditoria.py`, `backend/app/services/cwv_auditoria_service.py`, `backend/app/agents/cwv/workflow.py::_run_workflow_cwv`, `frontend/src/components/cwv/cwv-auditoria-client.tsx`, `frontend/src/lib/api/cwv.ts`  ·  **Rota:** `core-web-vitals/auditoria/[auditoriaId]`
**Créditos:** **billing normal de execução CWV** — reserva `calcular_custo_cwv(n_urls*2)`, idêntico a uma análise nova (decisão travada: sem cobrança extra além da execução)
**Depende de:** `[[SPEC_CWV_Auditoria_Ciclo_De_Vida]]`, `[[SPEC_CWV_Health_Score]]`
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gap #9); colunas "STATUS AFTER NPBR" / "SCORE AFTER" da planilha

---

## 1. Contexto (por quê)

O valor da planilha NPBR está no ciclo completo: depois que o cliente implementa, a re-auditoria (AFTER) prova o resultado — cada item ganha status after e o health score é recalculado. Esta spec fecha o ciclo: um endpoint re-executa a análise nas mesmas URLs da execução BEFORE e, ao concluir, aplica os resultados no checklist da auditoria.

## 2. Requisitos / Critérios de aceite

- [ ] Dado auditoria em fase `aguardando_implementacao`, quando `POST /core-web-vitals/auditorias/{id}/reauditar`, então uma nova execução CWV é criada com as MESMAS URLs por template da execução before, com reserva de créditos idêntica à de uma análise normal (`calcular_custo_cwv(n_urls*2)`), a auditoria ganha `execucao_after_id` e fase `after`, e a resposta é 202.
- [ ] Dado que a execução after conclui e o problema X (presente no before) não aparece mais, então o item correspondente do checklist fica `status_after='pass'`.
- [ ] Dado problema persistente no after, então `status_after='fail'`.
- [ ] Dado item cuja(s) URL(s) de escopo falharam TODAS no PSI do after, então `status_after='na'` (não `pass` — ausência de dado ≠ resolvido).
- [ ] Dado que a auditoria foi deletada durante a execução do after, então a execução conclui normalmente (fail-open — o hook não pode derrubar o workflow).
- [ ] Dado after concluído, então `health_score_after` é preenchido (do `resultado_json.health_score` da execução after) e a UI mostra before → after com delta por item e no header.
- [ ] Dado auditoria em fase `before` (sem passar por `aguardando_implementacao`), quando `POST .../reauditar`, então 409; auditoria de outro usuário → 404.

## 3. Design (mapeado ao código)

### 3.1 Endpoint — `routers/ferramentas_cwv_auditoria.py`

`POST /core-web-vitals/auditorias/{auditoria_id}/reauditar` → 202:
1. Ownership (404); fase deve ser `aguardando_implementacao` (409 caso contrário); `execucao_after_id` já preenchida e execução não-falhada → 409 (re-tentar só após falha).
2. Reconstruir `urls_por_template` a partir da `entrada_json` da execução before (`execucao_before.entrada_json["urls_por_template"]` — cópia direta, é o formato canônico validado).
3. Billing idêntico ao `analisar_cwv` de `ferramentas_cwv.py`: `custo = calcular_custo_cwv(n_urls*2)` → `credito_service.reservar_creditos` (402 se insuficiente) → criar execução via `_criar_execucao_cwv` (**importar/reusar** a função de `ferramentas_cwv.py`, não duplicar) com `entrada_json = {"cliente_id": ..., "urls_por_template": <cópia>, "auditoria_id": str(auditoria_id), "fase_auditoria": "after"}` → enfileirar `executar_workflow_cwv` → em falha de enqueue, liberar reserva e marcar falha (mesmo tratamento do endpoint original).
4. Atualizar auditoria: `execucao_after_id = execucao.id`, fase → `after` (via `avancar_fase`).
5. Rate limit: mesmo `rate_limit_autenticado("cwv_reanalisar", 3, 300)` dos endpoints de análise.

**Crítico:** os campos extras (`auditoria_id`, `fase_auditoria`) são ADICIONADOS ao `entrada_json` sem alterar o shape de `urls_por_template` — `ferramenta_service._obter_reserva_estimada` lê exatamente `entrada.entrada_json["urls_por_template"]` para estimar a reserva em cancelamento/falha; divergência vaza créditos (bug histórico da `SPEC_Billing_CWV`).

### 3.2 Hook — `workflow.py::_run_workflow_cwv`

No final do fluxo de sucesso (após `execucao.status = "concluida"` e commit — ou imediatamente antes do commit final, na mesma sessão):

```python
auditoria_id = (execucao.entrada_json or {}).get("auditoria_id")
if auditoria_id:
    try:
        from app.services.cwv_auditoria_service import aplicar_resultado_after
        await aplicar_resultado_after(session, auditoria_id, execucao_id)
    except Exception:
        logger.warning("aplicar_resultado_after falhou para auditoria %s", auditoria_id, exc_info=True)
```

Fail-open: exceção logada, execução intocada.

### 3.3 Service — `cwv_auditoria_service.py::aplicar_resultado_after(session, auditoria_id, execucao_after_id)`

1. Carregar auditoria (se não existe → return silencioso) e itens do checklist.
2. Carregar problemas + análises da execução after; construir: conjunto de chaves de problema presentes (`chave_problema`, a mesma da criação), mapa de audits saudáveis (`raw_resumo_json.audits_score_map`, score ≥ 0.9 → kb via `mapeamento_audit_kb_com_aliases`), field data (`crux_*_categoria`) e page experience (tabela da S6, se existir).
3. Para cada item por `origem`:
   - `psi_audit`: chave presente nos problemas do after → `fail`; ausente E (kb do item aparece saudável no `audits_score_map` OU as URLs do escopo têm análise de sucesso) → `pass`; todas as URLs do escopo falharam no PSI → `na`.
   - `field_data`: mesma regra da criação (FAST→pass, AVERAGE/SLOW→fail, sem dado→na).
   - `page_experience`: pior veredito das origens no after (`fail` > `erro→na` > `pass`); sem linhas → manter `status_after=NULL`? Não: `na`.
4. Itens com `status_after='pass'` e `status_implementacao != 'implementado'`: NÃO alterar o status de implementação (é controle do cliente), apenas registrar.
5. `health_score_after` ← `execucao_after.resultado_json["health_score"]["health_score"]` (se presente).
6. Publicar evento SSE final: `publish_event(execucao_id, "node_complete", "aplicar_after", f"Checklist atualizado: {n_pass} resolvidos, {n_fail} persistentes")`.

### 3.4 Frontend

- `lib/api/cwv.ts`: `reauditarCwv(auditoriaId)` → 202 com id da execução.
- `cwv-auditoria-client.tsx`: CTA "Re-auditar (verificar implementações)" quando fase `aguardando_implementacao` — mostra o custo antes (reusar `buscarCustoCwv`), confirma, chama o POST e navega para `execucao/[id]` (barra de progresso existente). Na volta, o checklist mostra colunas Before | After com badges e delta no header (`health_score_before → health_score_after`, seta verde/vermelha). Itens resolvidos (fail→pass) com destaque visual (fundo success suave, padrão do empty-state existente).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Billing | Execução normal, sem desconto/extra | Re-auditoria grátis (custo real de PSI/LLM existe) ou produto pago à parte (decisão travada: preço atual) |
| Aplicação do resultado | Hook fail-open no fim do workflow | Job separado disparado pelo front (frágil: usuário fecha a aba e o after nunca aplica) |
| URLs do after | Cópia exata do before | Permitir editar URLs (quebraria a comparabilidade item a item) |
| Ausência de dado no after | `na` | `pass` (falso positivo de melhoria) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_reauditoria.py -q
```

Novo `backend/tests/unit/test_cwv_reauditoria.py`:
1. `aplicar_resultado_after` puro com fixtures: problema sumiu → pass; persistiu → fail; URLs do escopo falharam → na.
2. Field data after AVERAGE → item `crux_*` fail; sem dado → na.
3. Auditoria inexistente → return silencioso, sem exceção.
4. `health_score_after` copiado quando presente; ausente → NULL.
5. Rota: fase errada → 409; ownership → 404; reserva calculada = `calcular_custo_cwv(n*2)` (mock de `credito_service`, padrão `test_cwv_custo.py`); `entrada_json` contém `auditoria_id` E `urls_por_template` com shape idêntico ao before (assert de igualdade).
6. Hook: exceção dentro de `aplicar_resultado_after` não altera o status da execução (fail-open).

E2E manual: criar auditoria → avançar fase → re-auditar → conferir before/after e health delta.

## 6. Não-objetivos

- Múltiplos ciclos after (after do after) — 1 ciclo por auditoria nesta fase; nova rodada = nova auditoria.
- Comparação de métricas contínuas (LCP before vs after por URL) — já existe em `/comparacao` por análise; a UI da auditoria pode linkar.
- Agendamento automático do after (monitoramento) — roadmap V3.

## 7. Avisos ao implementador

1. **Billing intocável:** `_obter_reserva_estimada` lê `entrada_json["urls_por_template"]` — os campos novos (`auditoria_id`, `fase_auditoria`) são irmãos, nunca alterar o shape desse campo.
2. Hook fail-open: auditoria deletada/corrompida NUNCA falha a execução (try/except largo + log).
3. Reusar `_criar_execucao_cwv` e o fluxo de enqueue/rollback de `ferramentas_cwv.py::analisar_cwv` — não reimplementar.
4. A chave de comparação de problemas é `cwv_auditoria_service.chave_problema` (a mesma da criação do checklist e do `/comparacao`) — uma chave divergente faria todo item parecer resolvido.
5. Ownership 404; rate limit igual ao reanalisar existente.
6. Export estático Next.js: navegação client-side via `router.push`, sem rotas novas.

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
