# SPEC — Auditoria (campanha): ciclo before → implementação → after

**Status:** 📋 planejado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (2 tabelas, service, router novo) + frontend (página da auditoria)
**Código:** `backend/app/models/cwv_auditoria.py` (novo), `backend/app/models/cwv_checklist_item.py` (novo), `backend/app/services/cwv_auditoria_service.py` (novo), `backend/app/routers/ferramentas_cwv_auditoria.py` (novo), `backend/app/schemas/cwv_auditoria.py` (novo), `backend/migrations/versions/0026_cwv_auditoria_checklist.py`, `frontend/src/app/(app)/ferramentas/core-web-vitals/auditoria/[auditoriaId]/page.tsx` (novo), `frontend/src/components/cwv/cwv-auditoria-client.tsx` (novo), `frontend/src/lib/api/cwv.ts`  ·  **Rota:** `core-web-vitals/auditoria/[auditoriaId]`
**Créditos:** não cobra (criação de auditoria é gratuita; execuções continuam com billing próprio)
**Depende de:** `[[SPEC_CWV_Field_Data_Retencao_Payload]]` (usa `raw_resumo_json.audits_score_map` e campos `crux_*`), `[[SPEC_CWV_Health_Score]]` (copia o health)
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gaps #9, #18); aba `Checklist` da planilha NPBR

---

## 1. Contexto (por quê)

A planilha NPBR não é um relatório pontual: é um **documento vivo**. O consultor audita (BEFORE), o cliente implementa marcando cada item (`Implementado / Em andamento / Pendente` — comentário na planilha: "CONTROLE DO CLIENTE"), e uma re-auditoria (AFTER) recalcula o health score. A ferramenta hoje só tem execuções isoladas. Esta spec cria a entidade **Auditoria** (campanha) que amarra execuções existentes num ciclo de vida com checklist colaborativo — sem alterar nada no fluxo de análise avulsa nem no billing.

## 2. Requisitos / Critérios de aceite

- [ ] Dado uma execução CWV concluída com problemas em 3 URLs, quando `POST /core-web-vitals/auditorias` com essa execução, então é criada uma auditoria em fase `before` cujo checklist tem 1 item por chave de problema dedupada, com `status_before='fail'` e `escopo_json.urls` listando as URLs afetadas.
- [ ] Dado que a execução tem `raw_resumo_json.audits_score_map` com audits saudáveis (score ≥ 0.9) mapeados na KB, então o checklist também contém itens `status_before='pass'` com `prioridade=0`.
- [ ] Dado que a execução tem field data (`crux_*_categoria`), então o checklist contém os itens `crux_lcp`, `crux_inp`, `crux_cls` com `pass` (FAST) / `fail` (AVERAGE|SLOW) / `na` (sem dados).
- [ ] Dado um item do checklist, quando `PATCH .../itens/{item_id}` com `{"status_implementacao": "em_andamento", "nota_cliente": "..."}`, então persiste e o `GET` da auditoria reflete.
- [ ] Dado uma auditoria em fase `before`, quando `PATCH` com `{"fase": "concluida"}`, então 422 (transições válidas apenas: `before→aguardando_implementacao→after→concluida`).
- [ ] Dado uma execução de outro usuário, quando `POST /auditorias`, então 404.
- [ ] Dado uma execução com `resultado_json.health_score`, então `health_score_before` é copiado na criação da auditoria.
- [ ] Dado a página `auditoria/[auditoriaId]`, então exibe fase, health before (e after quando existir), e o checklist ordenado por prioridade com dropdown de status de implementação e campo de nota editáveis.

## 3. Design (mapeado ao código)

### 3.1 Modelo — migração `0026_cwv_auditoria_checklist.py`

Tabela `cwv_auditoria` (`backend/app/models/cwv_auditoria.py`, herda `Base, UUIDPrimaryKeyMixin` como `cwv_analise.py`):

| Coluna | Tipo | Nota |
|---|---|---|
| `cliente_id` | UUID FK `clientes.id` NOT NULL | |
| `usuario_id` | UUID FK `usuarios.id` NOT NULL | |
| `titulo` | Text NOT NULL | default no service: `"Auditoria CWV — {AAAA-MM-DD}"` |
| `fase` | String(30) NOT NULL default `'before'` | CHECK `cwv_auditoria_fase_check` IN (`before`,`aguardando_implementacao`,`after`,`concluida`) |
| `execucao_before_id` | UUID FK `execucoes_ferramentas.id` ON DELETE SET NULL, NULL | |
| `execucao_after_id` | UUID FK idem, NULL | preenchida por `[[SPEC_CWV_Reauditoria_After]]` |
| `health_score_before` | Numeric(5,2) NULL | |
| `health_score_after` | Numeric(5,2) NULL | |
| `consolidacao_status` | String(20) NOT NULL default `'nao_executada'` | CHECK IN (`nao_executada`,`executando`,`concluida`,`falhou`) — usado por `[[SPEC_CWV_Consolidador_Cross_URL]]` |
| `relatorio_json` | JSONB NOT NULL server_default `'{}'` | preenchido por `[[SPEC_CWV_Relatorio_Executivo]]` |
| `criado_em` / `atualizado_em` | timestamptz NOT NULL server_default now() | `atualizado_em` com `onupdate` |

Índices: `ix_cwv_auditoria_cliente (cliente_id, criado_em DESC)`, `ix_cwv_auditoria_usuario (usuario_id)`.

Tabela `cwv_checklist_item` (`backend/app/models/cwv_checklist_item.py`):

| Coluna | Tipo | Nota |
|---|---|---|
| `auditoria_id` | UUID FK `cwv_auditoria.id` ON DELETE CASCADE NOT NULL | |
| `origem` | String(20) NOT NULL | CHECK IN (`psi_audit`,`page_experience`,`field_data`) |
| `item_codigo` | String(120) NOT NULL | ver 3.2; UNIQUE `(auditoria_id, item_codigo)` |
| `titulo` | Text NOT NULL | |
| `status_before` | String(10) NOT NULL | CHECK IN (`pass`,`fail`,`na`) |
| `status_after` | String(10) NULL | mesmo CHECK; NULL até o after |
| `status_implementacao` | String(20) NOT NULL default `'nao_executado'` | CHECK IN (`nao_executado`,`em_andamento`,`implementado`) |
| `nota_cliente` | Text NULL | |
| `nota_seo` | Text NULL | |
| `prioridade` | Integer NOT NULL default 0 | >0 apenas para fails (regra da planilha) |
| `esforco` | String(10) NULL | copiado dos problemas (`[[SPEC_CWV_Estimador_Esforco]]`); NULL se spec não aplicada |
| `escopo_json` | JSONB NOT NULL server_default `'{}'` | `{"urls": [...], "estrategias": [...]}` |
| `problema_consolidado_id` | UUID NULL, **sem FK** | a FK é adicionada pela migração da `[[SPEC_CWV_Consolidador_Cross_URL]]` |
| `criado_em` / `atualizado_em` | timestamptz | |

Índice: `ix_cwv_checklist_auditoria (auditoria_id, prioridade)`.

### 3.2 Geração do checklist — `cwv_auditoria_service.py` (novo)

```python
async def criar_auditoria(session, *, usuario_id, cliente_id, execucao_id, titulo=None) -> CwvAuditoria
async def gerar_checklist(session, auditoria: CwvAuditoria, execucao_id: str) -> list[CwvChecklistItem]
```

Determinístico, executado no `POST` (mesma transação):

1. **Fails** — carregar `CwvProblema` de todas as `CwvAnalise` da execução; agrupar pela chave canônica de problema (mesma função de `routers/ferramentas_cwv.py::comparar_com_anterior::_chave`: `kb_codigo` > `f"audit:{audit_id}"` > `f"titulo:{titulo}"` — **extrair essa função para `cwv_auditoria_service.py::chave_problema(p)` e importar no router**, evitando duplicação). Por grupo: 1 item `origem='psi_audit'`, `item_codigo=chave`, `titulo` do problema, `status_before='fail'`, `escopo_json` com URLs/estratégias das análises de origem, `esforco` = max dos problemas (`baixo<medio<alto`), `prioridade` = min(`prioridade_ordem`) entre os problemas do grupo (renumerar sequencialmente 1..N ao final, ordenado por essa prioridade).
2. **Passes** — de `raw_resumo_json.audits_score_map` (união das análises): audits com `score >= 0.9` que têm mapeamento na KB (`cwv_kb.mapeamento_audit_kb_com_aliases()`) e cujo kb_codigo NÃO está entre os fails → item `pass` com `item_codigo=kb_codigo`, `titulo` da KB (`cwv_kb.buscar_entrada`), `prioridade=0`. Dedup por kb_codigo.
3. **Field data** — itens fixos `crux_lcp`, `crux_inp`, `crux_cls` (`origem='field_data'`): `pass` se todas as análises com dado têm categoria `FAST`; `fail` se alguma é `AVERAGE`/`SLOW`; `na` se nenhuma análise tem o dado.
4. **Page experience** — se a tabela `cwv_page_experience` (da `[[SPEC_CWV_Page_Experience]]`) tiver linhas para a execução: itens `pe_https`, `pe_ssl`, `pe_mixed_content`, `pe_redirect_301`, `pe_security_headers`, `pe_safe_browsing`, `pe_mobile_friendly` com o pior veredito entre as origens (`fail` > `erro→na` > `pass`). Se a tabela não existir ainda (spec não implementada) ou estiver vazia: **omitir** esses itens (import protegido por try/except ou checagem de existência — o checklist não pode quebrar).
5. Copiar `resultado_json["health_score"]["health_score"]` da execução para `health_score_before` (se presente).

Transições de fase: `avancar_fase(auditoria, nova_fase)` valida a ordem linear e levanta `ValueError` (→ 422 no router).

### 3.3 Router — `backend/app/routers/ferramentas_cwv_auditoria.py` (novo; registrar em `app/main.py` junto aos outros routers de ferramentas, mesmo prefixo `/api/ferramentas`)

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| POST | `/core-web-vitals/auditorias` | `{cliente_id: UUID, execucao_id: UUID, titulo?: str}` | 201 `AuditoriaResposta` |
| GET | `/core-web-vitals/auditorias?cliente_id=` | — | `{auditorias: [AuditoriaResumo]}` |
| GET | `/core-web-vitals/auditorias/{auditoria_id}` | — | `AuditoriaResposta` (com checklist ordenado por `status_before='fail'` primeiro, depois prioridade) |
| PATCH | `/core-web-vitals/auditorias/{auditoria_id}` | `{fase?: str, titulo?: str}` | `AuditoriaResposta`; 422 transição inválida |
| PATCH | `/core-web-vitals/auditorias/{auditoria_id}/itens/{item_id}` | `{status_implementacao?, nota_cliente?, nota_seo?}` | `ChecklistItemResposta` |

Validações: cliente pertence ao usuário (`_validar_cliente` — copiar padrão de `ferramentas_cwv.py`); execução pertence ao usuário e é `ferramenta='core_web_vitals'` com `status='concluida'` (senão 409); auditoria/item de outro usuário → 404.

Schemas em `backend/app/schemas/cwv_auditoria.py`: `AuditoriaCriarRequest`, `AuditoriaResposta` (inclui `checklist: list[ChecklistItemResposta]`, contadores `n_pass_before`, `n_fail_before`, `n_implementados`), `AuditoriaResumo`, `ChecklistItemResposta`, `ChecklistItemPatch`, `AuditoriaPatch` — todos com `Literal` para enums.

### 3.4 Frontend

- `lib/api/cwv.ts`: `criarAuditoriaCwv`, `listarAuditoriasCwv`, `buscarAuditoriaCwv`, `atualizarAuditoriaCwv`, `atualizarItemChecklistCwv` + tipos.
- Página nova `auditoria/[auditoriaId]/page.tsx`: fina, monta `<CwvAuditoriaClient />` (com `generateStaticParams` placeholder, padrão de `execucao/[id]/page.tsx`).
- `cwv-auditoria-client.tsx`: lê o id via `usePathname()` (**nunca** `useParams()` — export estático); header com título, fase (badge), health before/after; tabela/lista do checklist: título, escopo (nº de URLs, tooltip com a lista), badges before/after (Pass verde / Fail vermelho / N/A cinza), dropdown `status_implementacao` (salva no change com toast), notas em popover/textarea com botão salvar; agrupar por `origem` (seções "Page Speed Insights", "Dados de campo", "Page Experience") espelhando a organização da planilha.
- Botão "Criar auditoria a partir desta execução" em `cwv-execucao-client.tsx` quando `status==='concluida'` → cria e navega via `router.push`.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Amarração | Auditoria **referencia** execuções (`execucao_before_id`) | Workflow próprio de auditoria (duplicaria billing/eventos; análise avulsa continua idêntica) |
| Geração do checklist | Determinística no POST | LLM (dado estruturado já existe; LLM entra só na consolidação — spec S8) |
| Router | Arquivo novo `ferramentas_cwv_auditoria.py` | Inflar `ferramentas_cwv.py` (~520 linhas) |
| Concorrência no PATCH de item | Last-write-wins | Optimistic lock (excesso para o caso de uso: 1 cliente + 1 consultor) |
| Snapshot | Checklist é snapshot no momento da criação | Recalcular on-read (checklist deve ser estável enquanto o cliente trabalha) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_auditoria.py -q
```

Novo `backend/tests/unit/test_cwv_auditoria.py`:
1. `gerar_checklist` com problemas repetidos em 3 URLs → 1 item fail com escopo de 3 URLs e prioridade renumerada.
2. `audits_score_map` com audit saudável mapeado na KB → item pass; audit saudável que também aparece como fail → NÃO vira pass (fail vence).
3. Field data FAST/AVERAGE/ausente → pass/fail/na.
4. Execução sem tabela de page experience → checklist sem itens `pe_*`, sem exceção.
5. `avancar_fase`: cadeia válida ok; pulo de fase → ValueError.
6. Rotas: POST com execução de outro usuário → 404; execução não concluída → 409; PATCH item persiste; UNIQUE `(auditoria_id, item_codigo)` respeitado.

E2E manual: criar auditoria de uma execução real, marcar 2 itens como implementado, recarregar → estado persiste.

## 6. Não-objetivos

- Consolidação cross-URL, relatório executivo e re-auditoria — specs próprias (S8, S9, S10) que dependem desta.
- Permissões multi-usuário/portal do cliente (o "cliente" edita através da mesma conta do consultor nesta fase).
- Editar URLs da auditoria depois de criada (criar outra auditoria).

## 7. Avisos ao implementador

1. Migração `0026`: conferir `ls backend/migrations/versions/` e encadear na última **real** (a numeração 0024-0028 desta série está reservada no README; se outra spec da onda ainda não criou a dela, ajustar `down_revision` para a última existente de fato).
2. `problema_consolidado_id` fica **sem FK** nesta migração — a FK chega na migração da S8 (evita dependência circular entre specs).
3. Ownership 404 (nunca 403) em todas as rotas; `_validar_cliente` copiado do padrão existente.
4. Registrar o router novo em `app/main.py` — sem isso as rotas não existem (verificar como os routers `ferramentas_*.py` são incluídos e replicar).
5. Export estático Next.js: página dinâmica precisa de `generateStaticParams` placeholder + leitura do id via `usePathname()` no client component.
6. Import de `cwv_page_experience` (S6) deve ser tolerante à ausência — as specs podem ser implementadas em qualquer ordem dentro das ondas.
7. Não tocar em billing: o POST de auditoria não reserva nem cobra créditos.

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
