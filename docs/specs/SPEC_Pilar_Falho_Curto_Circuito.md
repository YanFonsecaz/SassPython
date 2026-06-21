# SPEC — Curto-circuito quando o pilar falha (inlinks)

**Status:** pendente
**Escopo:** backend (`workflow_inlinks.py`)
**Crédito:** evita cobrança indevida (libera reserva quando o pilar falha)
**Esforço:** ~3h
**Depende de:** idealmente após (ou junto de) [`SPEC_Billing_Inlinks.md`](./SPEC_Billing_Inlinks.md), pois usa `_obter_reserva_estimada`.

## 1. Resumo

Quando a extração do pilar falha, o workflow **continua** (grafo linear) e processa todas as candidatas (scraping + metadados LLM + embeddings) à toa — não há pilar onde inserir links. No fim, `n_aplicados=0` e o usuário ainda é cobrado pelas URLs. Além disso, `node_extrair_pilar` publica **dois** eventos `node_complete` em caso de falha.

Esta SPEC: detecta a falha do pilar logo após a extração, encerra o workflow com mensagem clara e **libera a reserva** (custo 0), e corrige o evento duplicado.

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | Evento `node_complete` duplicado em falha | `workflow_inlinks.py:114-117` | falta `return`/`else` após o evento de falha |
| 2 | Workflow continua sem pilar | grafo linear `extrair_pilar → extrair_candidatos` (`:709`) | sem aresta condicional |
| 3 | Cobra por candidatas processadas mesmo sem pilar | `_finalizar_sucesso_inlinks` cobra por `n_validas` (`:825-829`) | nunca chega a aplicar nada, mas paga as URLs |
| 4 | Desperdício de LLM/embeddings | `node_enriquecer`/`node_match_rerank` rodam com pilar vazio | sem short-circuit |

## 3. Decisão de arquitetura

Adicionar **aresta condicional** após `extrair_pilar`: se `pilar_resultado.falhou` (ou `conteudo_md` vazio), ir para um nó terminal `falha_pilar` que finaliza com erro e libera a reserva; senão segue para `extrair_candidatos`.

- Curto-circuito **logo após o pilar** evita o scraping das candidatas (economia real).
- Finalização dedicada (status `falhou`, créditos 0) com mensagem acionável.

### Alternativa descartada
- Validar o pilar no **router** (antes de enfileirar): só pega o caso `pilar_markdown` vazio; quando é `pilar_url`, a falha só aparece no scraping (dentro do worker). Logo, a checagem precisa estar no workflow. (Pode-se *adicionar* uma validação leve no router como defesa extra, fora do escopo.)

## 4. Mudanças

### 4.1 `node_extrair_pilar` — corrigir evento duplicado

`workflow_inlinks.py:114-117`:

```python
if resultado.falhou:
    await publish_event(eid, "node_complete", "extrair_pilar", f"Falha ao extrair pilar: {resultado.erro}")
else:
    await publish_event(eid, "node_complete", "extrair_pilar", f"Pilar extraido: {resultado.tokens} tokens")
```

### 4.2 Novo nó terminal `falha_pilar`

```python
async def node_falha_pilar(estado: EstadoInlinks) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    eid = estado["execucao_id"]
    pilar = estado.get("pilar_resultado", {})
    erro = pilar.get("erro") or "Não foi possível extrair o conteúdo do pilar."
    await publish_event(eid, "node_complete", "falha_pilar", f"Pilar indisponível: {erro}")
    return {"resultado_final": {
        "_pilar_falhou": True,
        "erro": erro,
        "n_candidatas_validas": 0,
        "n_aplicadas": 0,
        "inlinks": [],
    }}
```

### 4.3 Roteamento condicional

```python
def _pilar_ok(estado: EstadoInlinks) -> str:
    pilar = estado.get("pilar_resultado", {})
    if pilar.get("falhou") or not (pilar.get("conteudo_md") or "").strip():
        return "falha_pilar"
    return "extrair_candidatos"

# em criar_workflow_inlinks:
workflow.add_node("falha_pilar", node_falha_pilar)
workflow.add_conditional_edges(
    "extrair_pilar", _pilar_ok,
    {"falha_pilar": "falha_pilar", "extrair_candidatos": "extrair_candidatos"},
)
workflow.add_edge("falha_pilar", END)
# remover a aresta fixa antiga: workflow.add_edge("extrair_pilar", "extrair_candidatos")
```

### 4.4 Finalize trata o pilar falho (libera reserva, custo 0)

Em `_finalizar_sucesso_inlinks` (`:799`), no início, após buscar a execução:

```python
if resultado_json.get("_pilar_falhou"):
    reserva = ferramenta_service._obter_reserva_estimada("inlinks_automaticos", execucao)
    await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)
    execucao.status = "falhou"
    execucao.creditos_cobrados = 0
    execucao.erro_msg = (
        "Não foi possível extrair o conteúdo do pilar (URL inacessível, "
        "bloqueio por robots.txt, ou conteúdo vazio). Verifique a URL/markdown do pilar."
    )
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    logger.info("%s inlinks status=falhou (pilar nao extraido), reserva liberada", _log_prefix(execucao_id))
    return
```

## 5. Verificação

### 5.1 Unit — roteamento

```python
def test_pilar_falho_roteia_para_falha():
    assert _pilar_ok({"pilar_resultado": {"falhou": True}}) == "falha_pilar"
    assert _pilar_ok({"pilar_resultado": {"conteudo_md": "   "}}) == "falha_pilar"
    assert _pilar_ok({"pilar_resultado": {"conteudo_md": "texto real"}}) == "extrair_candidatos"
```

### 5.2 Smoke do grafo

`criar_workflow_inlinks()` compila com `falha_pilar` e a aresta condicional (atualizar `tests/unit/test_workflow_syntaxerror.py` se ele cobre inlinks).

### 5.3 E2E — pilar inacessível

Mockar `extrair_pilar` para `ScrapeResult(falhou=True)`; rodar o workflow e assertar:
- `extrair_candidatos`/`enriquecer` **não** executaram (sem scraping de candidatas);
- execução `status=falhou`, `creditos_cobrados=0`, reserva liberada;
- apenas **um** `node_complete` para `extrair_pilar`.

### 5.4 Front

A barra de progresso de inlinks (`barra-progresso-workflow.tsx`, `ETAPAS_ORDER_INLINKS`) não precisa do `falha_pilar` no stepper (é terminal); confirmar que o estado `falhou` é exibido normalmente (já é).

## 6. Riscos

- **Mudança de topologia do grafo**: execuções inlinks em andamento durante deploy podem divergir do checkpoint (thread_id `inlinks_{eid}`). Deployar sem execuções inlinks pausadas (inlinks não tem human-gate, então a janela é curta).
- **Coordenação com SPEC-A**: ambas mexem em `_finalizar_sucesso_inlinks`. Fazer juntas ou rebasear com atenção.

## 7. Fora de escopo

- Validação de pilar no router (defesa extra opcional).
- Retry automático de scraping do pilar.
- Aplicar o mesmo curto-circuito ao `distribuir_inlinks` (avaliar em PR próprio se o alvo falho tem tratamento — ele já tem `alvo_invalido`).

## 8. Arquivos alterados

- `backend/app/agents/workflow_inlinks.py` — `node_extrair_pilar` (evento), `node_falha_pilar` (novo), `_pilar_ok` (roteamento), grafo, `_finalizar_sucesso_inlinks` (branch pilar falho).
- `backend/tests/unit/` — roteamento + smoke do grafo.
