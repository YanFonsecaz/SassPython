# PLANO — Correções da ferramenta Inlinks

**Status:** pendente
**Origem:** análise crítica dos dois pipelines de inlinks
- `inlinks_automaticos` (`workflow_inlinks.py`): `validar_urls → extrair_pilar → extrair_candidatos → enriquecer → match_rerank → inserir → revisar → formatar → persistir`
- `distribuir_inlinks` (`workflow_inlinks_reversos.py`): inlinks reversos (pilar recebe links de candidatas)
**Público:** outra IA / dev implementando as correções
**Esforço total estimado:** ~12–16h

## 0. Como usar este plano

São 4 SPECs independentes, cada uma é um PR. Ordem recomendada abaixo. SPEC-A (billing) primeiro por impacto financeiro e por compartilhar `_obter_reserva_estimada` com as demais ferramentas.

| Ordem | SPEC | Severidade | Impacto | Esforço | Arquivo |
|---|---|---|---|---|---|
| 1 | Billing correto dos inlinks (reservar pelo custo real) | 🔴 Crítico | Receita + UX (nos 2 inlinks) | ~4h | [`SPEC_Billing_Inlinks.md`](./SPEC_Billing_Inlinks.md) |
| 2 | Curto-circuito quando o pilar falha | 🟠 Alto | Cobrança indevida + desperdício | ~3h | [`SPEC_Pilar_Falho_Curto_Circuito.md`](./SPEC_Pilar_Falho_Curto_Circuito.md) |
| 3 | `trecho_contexto` correto no inseridor | 🟠 Alto | Dado errado exibido/persistido | ~2h | [`SPEC_Inseridor_Trecho_Contexto.md`](./SPEC_Inseridor_Trecho_Contexto.md) |
| 4 | Qualidade/robustez dos agentes LLM | 🟡 Médio | Latência + qualidade dos links | ~5h | [`SPEC_Qualidade_Agentes_Inlinks.md`](./SPEC_Qualidade_Agentes_Inlinks.md) |

> SPEC-2, 3 e 4 podem ir em paralelo. SPEC-1 e SPEC-2 ambas tocam `workflow_inlinks.py` (finalize/grafo) — coordenar merge.

## 1. Resumo dos problemas (diagnóstico)

| # | Problema | Causa raiz | SPEC |
|---|---|---|---|
| 1 | Reserva subdimensionada nos 2 inlinks: reserva só a base (15), cobra até 60/115 | `calcular_custo_inlinks(len(...))` é calculado e **descartado** (`ferramentas_inlinks.py:33`; `ferramentas_inlinks_reversos.py:37`); reserva-se `CUSTO_BASE_*` | A |
| 2 | Pilar falho não curto-circuita: workflow processa candidatas à toa e cobra por resultado impossível; + evento `node_complete` duplicado | `node_extrair_pilar` não retorna em falha; grafo linear sem aresta condicional (`workflow_inlinks.py:114-117, 707-716`) | B |
| 3 | `trecho_contexto` (e `offset_chars`) desalinhados para o 2º+ inlink | `_aplicar_insercoes` extrai contexto com offset **original** no texto **já modificado** (`inseridor.py:918-922`) | C |
| 4a | Chamadas LLM por candidato em **série** (até 20× gpt-4.1) | loop sequencial (`inseridor.py:186-208`) | D |
| 4b | Parsing JSON frágil (find/rfind) no inseridor e enriquecedor | `_parse_proposta_unica` (`inseridor.py:612`), `_parse` (`enriquecedor_metadados.py:118`) — não usam `invoke_structured` | D |
| 4c | Temperatura 0.7 em tarefa de **cópia literal** (inseridor) e em **juiz** (revisor) | todos os agentes herdam `settings.llm_temperature` (`inseridor:294`, `revisor:129`, etc.) | D |
| 4d | Validações **fail-open**: embeddings None → cosine 1.0 passa; revisor falha → mantém todos | `inseridor.py:236-243`; `revisor.py:113-116` | D |

### Itens de limpeza (baixa prioridade — incorporados às SPECs acima)
- **Código morto:** `injector.injetar_inlinks` (2ª engine de inserção não usada) → remover na SPEC-C (que mexe no inseridor/injector).
- **Anotação malformada** `dict[str, Any][str, Any]` (`inseridor.py:184`) → corrigir na SPEC-C.
- **Offsets assumem `\n\n` exato** (`inseridor.py:871,785`) → mitigar na SPEC-C.
- **Modelos LLM por-agente sem cache** (reranker/enriquecedor/revisor/inseridor) → tratar na SPEC-D.

## 2. Referências

- Código: `app/agents/workflow_inlinks.py`, `workflow_inlinks_reversos.py`, `app/agents/inlinks/*.py`, `app/routers/ferramentas_inlinks*.py`, `app/services/ferramenta_service.py`.
- Doc LangChain (via MCP) — Structured output: *"Instead of parsing natural language responses, you get structured data… that your application can use directly."* (fundamenta a SPEC-D, item parsing).
- Precedente no repo: as correções equivalentes do `gerar_artigo` em [`SPEC_Billing_Gerar_Artigo.md`](./SPEC_Billing_Gerar_Artigo.md) e [`SPEC_Revisor_Determinismo.md`](./SPEC_Revisor_Determinismo.md) (temperatura por agente já foi adicionada ao `BaseAgent`).

## 3. Princípios

1. **Consistência de reserva**: valor reservado no router = liberado em falha/cancelamento = `reservado=` no `confirmar_debito`. Fonte única: `_obter_reserva_estimada`.
2. **Nunca cobrar por trabalho impossível** (pilar falho) nem descartar trabalho concluído por reserva insuficiente.
3. **Reusar o que já existe**: `BaseAgent` já suporta `temperature`/`model` por agente (adicionado na SPEC do revisor de artigo); `invoke_structured` já é usado por reranker/revisor.
4. **Não quebrar `distribuir_inlinks`, CWV e parecer** ao mexer em `_obter_reserva_estimada` (função compartilhada).
