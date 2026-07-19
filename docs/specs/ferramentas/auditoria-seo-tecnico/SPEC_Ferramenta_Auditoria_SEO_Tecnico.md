# SPEC — Ferramenta Auditoria de SEO Técnico (spec-mãe)

**Status:** 🚧 parcial
**Capacidade:** `auditoria-seo-tecnico`
**Escopo:** ambos — backend (workflow, rotas, modelos, worker) + frontend (páginas da ferramenta) + conector local
**Código:** `backend/app/agents/seotec/*`, `backend/app/routers/ferramentas_seo_tecnico.py`, `backend/app/services/seotec_*`, `backend/app/models/seo_*.py`, `frontend/src/app/(dashboard)/ferramentas/auditoria-seo-tecnico/*`, `frontend/src/components/seotec/*`
**Créditos:** `30` (auditoria before) · `15` (re-crawl after) — proposta, confirmar em `calcular_custo_seo_tecnico()`
**Depende de:** [SPEC_SEOTEC_Conector_Local_SF](SPEC_SEOTEC_Conector_Local_SF.md) · [SPEC_SEOTEC_Checklist_Motor_Regras](SPEC_SEOTEC_Checklist_Motor_Regras.md) · [SPEC_SEOTEC_Agentes_IA](SPEC_SEOTEC_Agentes_IA.md) · [SPEC_SEOTEC_Ciclo_Auditoria_Health_Score](SPEC_SEOTEC_Ciclo_Auditoria_Health_Score.md)

---

## 1. Contexto (por quê)

A agência audita SEO técnico com a planilha NPBR (~125 itens, 85 abas): processo manual de colar
exports do Screaming Frog, marcar status, escrever recomendações e montar o comparativo
antes/depois. A ferramenta automatiza esse fluxo para **todos os tenants do SaaS**, cada um usando o
**próprio Screaming Frog licenciado**: o crawl acontece na máquina do usuário, os dados sobem
normalizados, e o backend (motor de regras + agentes IA) preenche checklist, diagnósticos,
recomendações e o Health Score — com o mesmo modelo de antes/depois da planilha. Público: usuários
não técnicos (PRD); a UI esconde a mecânica (código de pareamento + 1 comando no conector).

## 2. Requisitos / Critérios de aceite

- [ ] Dado um tenant com conector pareado, quando ele clica "Rodar crawl" e executa `sf-connector run`,
      então uma auditoria fase `before` é criada com checklist preenchido, evidências e health score.
- [ ] Dado um pacote de exports subido manualmente (fallback), então o mesmo pipeline processa
      idêntico (mesma rota de ingestão).
- [ ] Dado o processamento concluído, todos os itens `fonte=sf` têm status
      `Reprovado`/`Atenção`/`Aprovado`/`Sem dados` + evidências; itens `fonte∈{gsc,manual}` aparecem
      como "Manual — preencher".
- [ ] Dado um item reprovado, então há diagnóstico e recomendação gerados por IA (KB + fallback LLM).
- [ ] Dado o ciclo `before → implementacao → after`, quando o re-crawl after processa, então cada
      item ganha status DEPOIS + delta e o health score exibe antes vs. depois.
- [ ] Dado qualquer execução, créditos seguem reserva→confirma/refund (padrão `credito_service`).
- [ ] Multi-tenant: auditoria pertence a `cliente_id` do usuário; nenhum dado vaza entre tenants.
- [ ] Progresso em tempo real via SSE (padrão `workflow_events`).

## 3. Design (mapeado ao código)

### 3.1 Modelos (novas tabelas)

| Tabela | Campos-chave | Notas |
|---|---|---|
| `seo_auditoria` | `id`, `usuario_id`, `cliente_id`, `dominio`, `fase` (`before`/`implementacao`/`after`/`concluida`), `score_antes`, `score_depois`, `data_inicial`, `data_conclusao`, `execucao_id` | campanha; espelha `cwv_auditoria` (ver `SPEC_CWV_Auditoria_Ciclo_De_Vida`) |
| `seo_crawl` | `id`, `auditoria_id`, `fase_destino`, `origem` (`conector`/`upload`), `sf_versao`, `schema_version`, `contadores_json`, `status` (`recebido`/`processando`/`processado`/`erro`/`parcial`), `criado_em` | 1 linha por ingestão |
| `seo_item_resultado` | `id`, `auditoria_id`, `item_slug`, `status_antes`, `status_depois`, `modo` (`auto`/`manual`), `diagnostico`, `recomendacao`, `evidencias_json` (JSONB **tipado** — padrão `SPEC_CWV_Contratos_JSONB_Tipados`), `status_cliente`, `validacao_seo`, `observacao_cliente`, `observacao_seo`, `atualizado_em` | 1 linha por item do checklist por auditoria |

Definição dos itens (categoria, peso, prioridade, textos didáticos, regra) **não vai para o DB**:
vive em YAML versionado (`backend/app/data/seotec_checklist/*.yaml`), carregado como a KB do CWV
(`services/cwv_kb.py` → novo `services/seotec_checklist.py`). Ver
[SPEC_SEOTEC_Checklist_Motor_Regras](SPEC_SEOTEC_Checklist_Motor_Regras.md).

### 3.2 Rotas (`routers/ferramentas_seo_tecnico.py`)

Prefixo alinhado ao slug (mesmo padrão dos routers existentes):

| Rota | Método | Papel |
|---|---|---|
| `/ferramentas/auditoria-seo-tecnico/auditorias` | GET/POST | listar/criar campanha |
| `/ferramentas/auditoria-seo-tecnico/auditorias/{id}` | GET/PATCH | detalhe · avançar fase · editar campos manuais |
| `/ferramentas/auditoria-seo-tecnico/auditorias/{id}/itens/{slug}` | GET/PATCH | detalhe do item · status manual, status_cliente, validacao_seo, observações |
| `/ferramentas/auditoria-seo-tecnico/pareamento` | POST | emite código de pareamento (curta validade) |
| `/ferramentas/auditoria-seo-tecnico/conector/*` | POST | troca código→token de dispositivo · receita · upload de chunks · finalizar ingestão (auth por token de dispositivo; ver spec do conector) |
| `/ferramentas/auditoria-seo-tecnico/auditorias/{id}/upload` | POST | fallback B: upload manual `.zip` |
| `/ferramentas/auditoria-seo-tecnico/auditorias/{id}/eventos` | GET (SSE) | progresso do processamento |

### 3.3 Workflow (worker ARQ + LangGraph linear, padrão `agents/cwv/workflow.py`)

```
validar_pacote → motor_regras → analisar_ia → recomendar_ia → health_score → persistir → END
```

| Nó | Responsabilidade | Onde |
|---|---|---|
| `validar_pacote` | schema_version, contadores, completude por export | `services/seotec_ingestao.py` |
| `motor_regras` | status determinístico + evidências por item `fonte=sf` | `services/seotec_motor.py` |
| `analisar_ia` | diagnóstico por item reprovado/atenção (lotes) | `agents/seotec/analisador.py` |
| `recomendar_ia` | recomendação por item (KB → fallback LLM) | `agents/seotec/recomendador.py` + `services/seotec_kb.py` |
| `health_score` | fórmula da planilha (base 940) por fase | `services/seotec_score.py` |
| `persistir` | grava `seo_item_resultado` + score na `seo_auditoria` | `services/seotec_persistencia.py` |

Infra reusada tal qual: `services/ferramenta_service.py` (lifecycle execução),
`services/credito_service.py`, `core/workflow_events.py` (SSE), `core/llm_guard.py`,
`agents/checkpointer.py`, `app/worker.py`.

### 3.4 Frontend

| Página/Componente | Conteúdo |
|---|---|
| `auditoria-seo-tecnico/page.tsx` | painel de auditorias (fase, score, delta) + CTA criar |
| `auditoria-seo-tecnico/[id]/page.tsx` | header: gauge Health Score antes/depois + gráficos por prioridade (recharts, reusar padrões `components/cwv/`) · tabs por categoria · tabela do checklist (status, prioridade, responsável, prazo = data crawl + 5/10/20/45 dias) |
| `components/seotec/item-drawer.tsx` | detalhe do item (= aba oculta): fonte, diagnóstico, recomendação, tabela de evidências paginada, campos editáveis (status manual, status_cliente, validacao_seo, observações) |
| `components/seotec/comparativo.tsx` | antes/depois por categoria e item, badges de mudança |
| `auditoria-seo-tecnico/conector/page.tsx` | instalação, código de pareamento, status do último crawl, upload manual |
| `lib/api/seotec.ts` | client tipado das rotas |

### 3.5 Cobrança

`calcular_custo_seo_tecnico(fase)` em `services/ferramenta_service.py`: `before=30`, `after=15`
(re-crawls intermediários na fase `implementacao` cobram como after). Reserva no aceite da ingestão,
confirma no `persistir`, refund em erro — idêntico ao CWV (`SPEC_Billing_CWV`).

## 4. Decisões & alternativas

Ver tabela consolidada no [README](README.md). Adicionais desta spec:

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Definição dos itens | YAML versionado no git (seed extraído da planilha) | tabela `seo_checklist_def` no DB (migraria a cada ajuste editorial) |
| Granularidade site/blog | 1 status por item (colunas N/O da planilha fora da V1) | duplicar checklist por propriedade |
| Orquestração | LangGraph `ainvoke` linear | reutilizar workflow CWV com branches (acoplaria ferramentas) |

## 5. Verificação

```bash
# unit: motor de regras, score, ingestão
rtk pytest backend/tests/unit/test_seotec_motor.py backend/tests/unit/test_seotec_score.py
# e2e: pacote fixture → auditoria completa
rtk pytest backend/tests/e2e/test_e2e_seotec.py
# manual: parear conector local (make dev), sf-connector run contra site pequeno, conferir UI
```

## 6. Não-objetivos

Os do [README](README.md), mais: agendamento de crawls recorrentes · comparação entre auditorias de
clientes diferentes · edição da receita de exports pela UI.

## 7. Ordem de implementação sugerida (ondas)

1. **Onda 1 — fundação de dados:** seed YAML do checklist + modelos/migração + contrato de ingestão
   + upload manual (fallback B) + motor de regras. *Valor: auditoria funciona via upload, sem IA.*
2. **Onda 2 — conector:** `sf-connector` (pair/run, MCP stdio + fallback CLI) + rotas de dispositivo.
3. **Onda 3 — IA:** analisador + recomendador + KB por item.
4. **Onda 4 — ciclo e UI final:** fases before/after + comparativo + polish do front.

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-18 | Onda 1 implementada (fundação de dados: seed, modelos 0029, ingestão, motor 31 regras, score, workflow, rotas, e2e); decisão: checklist YAML vive em `backend/app/data/seotec_checklist/`, não `app/kb/` | b70c771 |
| 2026-07-17 | Spec inicial (design aprovado em brainstorming) | — |
