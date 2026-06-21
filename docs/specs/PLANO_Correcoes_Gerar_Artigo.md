# PLANO — Correções da ferramenta Gerar Artigo

**Status:** pendente
**Origem:** análise crítica do pipeline `gerar_artigo` (LangGraph: `pesquisar → analisar → criar_brief → redigir → revisar → ⟳ → aguardar_aprovacao → ⟳ → salvar_vetorial → gerar_imagem`)
**Público:** outra IA / dev implementando as correções
**Esforço total estimado:** ~10–14h

## 0. Como usar este plano

São 4 SPECs independentes, cada uma é um PR. Implemente **na ordem abaixo** (há uma dependência forte: SPEC-A muda o modelo de custo e a reserva; as demais não dependem dela, mas A é a de maior impacto e deve ir primeiro). Cada SPEC tem critérios de aceite e testes próprios.

| Ordem | SPEC | Severidade | Impacto | Esforço | Arquivo |
|---|---|---|---|---|---|
| 1 | Billing correto do gerar-artigo | 🔴 Crítico | Receita + integridade de dados + UX | ~5h | [`SPEC_Billing_Gerar_Artigo.md`](./SPEC_Billing_Gerar_Artigo.md) |
| 2 | Pesquisador não-bloqueante | 🔴 Crítico | Estabilidade do worker (multi-tenant) | ~2h | [`SPEC_Pesquisador_Nao_Bloqueante.md`](./SPEC_Pesquisador_Nao_Bloqueante.md) |
| 3 | Determinismo do revisor | 🟠 Alto | Qualidade/consistência do gate | ~2h | [`SPEC_Revisor_Determinismo.md`](./SPEC_Revisor_Determinismo.md) |
| 4 | Robustez do workflow + SSE | 🟡 Médio | Corretude de eventos + escala do progresso | ~3h | [`SPEC_Robustez_Workflow_SSE.md`](./SPEC_Robustez_Workflow_SSE.md) |

> SPEC-2, 3 e 4 podem ser feitas em paralelo entre si. SPEC-1 deve ser revisada primeiro porque mexe na semântica de cobrança (decisão de produto embutida).

## 1. Resumo dos problemas (diagnóstico)

| # | Problema | Causa raiz | SPEC |
|---|---|---|---|
| 1 | **Todo artigo custa exatamente 20 créditos**, independentemente de quantas revisões/feedbacks ocorreram | `execucao.tentativas_revisao`/`tentativas_feedback` (colunas do banco) **nunca são escritas** a partir do estado do LangGraph; `calcular_custo_final` lê sempre `0` | A |
| 2 | Histórico/auditoria sempre mostram `tentativas_*=0` e descrição "revisoes=0, feedbacks=0" | Mesma causa do #1 | A |
| 3 | Imagem é cobrada (`+5`) mesmo quando a geração falhou (`imagem_url=None`) | `calcular_custo_final` soma `CUSTO_IMAGEM` incondicionalmente | A |
| 4 | Reserva (`CUSTO_MINIMO=20`) **subdimensionada** vs. custo variável → ao corrigir #1, débito pode exceder o saldo e **descartar artigo já gerado** | Reserva fixa não cobre o pior caso; só `ValueError` é tratado (CHECK constraint lança `IntegrityError` não-capturado) | A |
| 5 | Incremento de `tentativas_revisao` com lógica contraditória (revisor calcula condicional, workflow sobrescreve com `+1`); idem `versao_atual` | Código duplicado/morto nos nós | A |
| 6 | **SerpAPI e pytrends (síncronos) rodam dentro de nós `async`** → bloqueiam a event loop; `asyncio.gather` não paraleliza; 1 job de pesquisa congela os outros (worker tem `arq_max_jobs=20` na mesma loop) | Chamadas bloqueantes sem `asyncio.to_thread` | B |
| 7 | O **revisor (juiz de qualidade) roda com `temperature=0.7`** → score não-determinístico, gate `score>=70` instável; arquitetura não permite temperatura por agente | Todos os agentes herdam o `settings.llm_temperature` global; `_get_chat_model` não recebe override por agente | C |
| 8 | Efeitos colaterais (eventos SSE / writes) **antes** do `interrupt()` → re-executam no resume (doc oficial do LangGraph) → eventos duplicados | `node_aguardar_aprovacao` publica/escreve antes do `interrupt` | D |
| 9 | Bugs menores: `pubsub.subscribe` duplicado; `aget_state` duplicado em branch morto; mensagem "5 minutos" com timeout real de 10 min; SSE faz polling do DB a cada 1s por cliente | Resíduos / redundância | D |

## 2. Referências consultadas

- Código: `backend/app/agents/{workflow,redator,revisor,pesquisador,gerador_imagem,base}.py`, `backend/app/services/{ferramenta_service,credito_service}.py`, `backend/app/routers/ferramentas.py`.
- Doc oficial LangGraph (via MCP):
  - *Re-execution and idempotency* — "the affected node runs again from the start of its function. Code and side effects before the pause run again."
  - *Side effects called before `interrupt` must be idempotent*.
  - *Default reducer* — sem `Annotated`, o canal é sobrescrito (last-write-wins) — confirma que os incrementos sequenciais funcionam, mas que código duplicado vira morto.

## 3. Princípios para a implementação

1. **Não quebrar o fluxo de aprovação humana** (`interrupt`/`Command(resume=...)`) — é o coração da ferramenta.
2. **Consistência de reserva**: o valor reservado, o liberado (falha/cancelamento) e o `reservado=` passado a `confirmar_debito` devem ser **o mesmo**. Inconsistência vaza créditos reservados.
3. **Fail-safe de cobrança**: o usuário nunca deve perder um artigo gerado por falta de saldo no débito final — a reserva tem que cobrir o pior caso.
4. **Tudo verificável**: cada SPEC entrega testes (unit/e2e) que provam o comportamento.
