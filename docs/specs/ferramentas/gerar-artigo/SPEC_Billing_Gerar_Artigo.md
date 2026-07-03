# SPEC — Billing correto do Gerar Artigo

**Status:** ✅ aplicado (commit ddbeb88)
**Escopo:** backend (workflow + serviço de cobrança)
**Crédito:** **muda a semântica de cobrança** (ler §3 — decisão de produto)
**Esforço:** ~5h
**Depende de:** nada. Deve ser a primeira do plano.

## 1. Resumo

A cobrança da ferramenta `gerar_artigo` está quebrada em 4 pontos que se reforçam:

1. As tentativas de revisão/feedback existem só no estado do LangGraph e **nunca são persistidas** na linha `ExecucaoFerramenta` → `calcular_custo_final` lê `0` sempre → **todo artigo custa fixo 20 créditos** (revisões e feedbacks saem de graça).
2. O histórico e a auditoria sempre mostram `tentativas_*=0`.
3. A imagem é cobrada (`+5`) mesmo quando a geração falhou.
4. A reserva (`CUSTO_MINIMO=20`) é menor que o custo máximo possível → **se corrigirmos só o item 1**, o débito final pode exceder o saldo e **descartar um artigo já gerado** (pior UX possível).

Esta SPEC corrige os quatro de forma coerente, com um modelo de custo simples e auditável.

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | Custo final sempre = 20 | `ferramenta_service.py:215-220` (`calcular_custo_final`) | Lê `execucao.tentativas_revisao/feedback`, que nunca são gravadas |
| 2 | Tentativas só no estado, nunca no banco | `workflow.py:94,183`; `revisor.py:99` gravam no estado; nenhum write na linha `ExecucaoFerramenta` (confirmado por grep) | Falta persistir no finalize |
| 3 | Imagem cobrada mesmo falhando | `gerador_imagem.py:54-56` engole exceção → `imagem_url=None`; `ferramenta_service.py:219` soma `CUSTO_IMAGEM` sempre | Custo não olha o resultado |
| 4 | Reserva fixa < custo máximo | `routers/ferramentas.py:62` reserva `CUSTO_MINIMO`; `ferramenta_service.py:249` confirma com `reservado=CUSTO_MINIMO` | Reserva não cobre o pior caso |
| 5 | `IntegrityError` do CHECK constraint não tratado | `finalizar_sucesso` (`:255`) só captura `ValueError` | CHECK `saldo_plano >= 0` (migração 0013) pode disparar |
| 6 | Incremento contraditório de `tentativas_revisao` e `versao_atual` | `revisor.py:99` (condicional) é sobrescrito por `workflow.py:94` (`+1`); `redator.py:73` é sobrescrito por `workflow.py:84` | Código morto/duplicado |

## 3. Decisão de arquitetura — modelo de custo

**Cobrar por número de versões geradas do artigo** (`versao_atual`), não pelos contadores `tentativas_*`.

```
custo_final = CUSTO_BASE
            + max(0, versao_atual - 1) * CUSTO_REVISAO
            + (CUSTO_IMAGEM se imagem foi gerada, senão 0)
```

- `versao_atual` = nº de execuções do nó `redigir` = nº de versões do artigo. É um sinal **limpo e confiável**: incrementado uma vez por redação, em `workflow.py:84`.
- A 1ª versão está embutida no `CUSTO_BASE` (que já inclui pesquisa+análise+brief+redação_v1+revisão_v1 = 5 chamadas LLM, batendo com `CUSTOS_TABELA["gerar_artigo_base"]`).
- Cada **regeneração** (seja por revisão automática reprovada ou por feedback humano) custa `CUSTO_REVISAO` (3). Como `revisao_automatica` e `feedback_humano` já custam o mesmo (3) na `CUSTOS_TABELA`, cobrar por versão é equivalente em preço e **elimina o duplo-contagem** atual (cada feedback hoje incrementa `tentativas_revisao` *e* `tentativas_feedback`).
- Imagem só é cobrada se entregue.

**Reserva = custo máximo possível**, liberando a diferença no débito:

```
custo_maximo = CUSTO_BASE
             + (workflow_max_revisoes + workflow_max_feedback) * CUSTO_REVISAO
             + CUSTO_IMAGEM
```

Com defaults (`max_revisoes=3`, `max_feedback=3`): `15 + (3+3)*3 + 5 = 38`. É um limite superior seguro de qualquer caminho real do grafo. `confirmar_debito(reservado=custo_maximo, quantidade=custo_final)` já libera a reserva inteira e debita só o real (a matemática atual de `confirmar_debito` faz isso corretamente — ver §4.4).

### Alternativas consideradas e descartadas

- **Manter a fórmula `base + tentativas_revisao*3 + tentativas_feedback*3`**: descartada porque os dois contadores se sobrepõem (cada feedback dispara um `revisar`, que incrementa `tentativas_revisao`) → cobra a mais. Exigiria desemaranhar os contadores no grafo.
- **Reservar incrementalmente (`+3` a cada `revisar`)**: mais "just-in-time", mas adiciona lógica de reserva e tratamento de falha no meio do workflow. Fica como evolução futura; reservar o máximo é mais simples e seguro agora.
- **Preço flat (sempre 20)**: seria assumir o bug como feature. A `CUSTOS_TABELA` com linhas separadas para revisão/feedback mostra que a intenção é preço escalonado.

> ✅ **Decidido (produto)**: cobrar por nº de versões **e** reservar o teto (38) estão aprovados — implementar como descrito, sem reabrir. Reservar 38 (em vez de 20) significa que o usuário precisa de 38 créditos disponíveis para iniciar (recebe o troco no fim). Se no futuro quiser reduzir a barreira de entrada, baixar `workflow_max_revisoes`/`workflow_max_feedback` reduz o teto, ou migrar para reserva incremental (ver "Alternativas").

## 4. Mudanças

### 4.1 `ferramenta_service.py` — constantes e helpers de custo

Adicionar, após as constantes existentes (`:14-17`):

```python
def custo_maximo_estimado() -> int:
    """Teto de crédito reservado para gerar_artigo (cobre o pior caminho do grafo)."""
    return (
        CUSTO_BASE
        + (settings.workflow_max_revisoes + settings.workflow_max_feedback) * CUSTO_REVISAO
        + CUSTO_IMAGEM
    )
```

Reescrever `calcular_custo_final` (`:215-220`) — passa a receber o estado final:

```python
def calcular_custo_final(versao_atual: int, imagem_gerada: bool) -> int:
    custo = CUSTO_BASE
    custo += max(0, versao_atual - 1) * CUSTO_REVISAO
    if imagem_gerada:
        custo += CUSTO_IMAGEM
    return custo
```

> Não é mais `async` e não lê do banco. Ajustar o caller (§4.3).

Atualizar `_obter_reserva_estimada` (`:223-234`) para `gerar_artigo`:

```python
if ferramenta == "gerar_artigo":
    return custo_maximo_estimado()   # antes: CUSTO_MINIMO
```

> Isso garante que falha (`finalizar_falha`), cancelamento (`cancelar_execucao`) e o handler de `CancelledError` (`workflow.py:327-329`) liberem **exatamente** o que foi reservado.

### 4.2 `routers/ferramentas.py` — reservar o teto

Trocar `CUSTO_MINIMO` por `custo_maximo_estimado()` nos dois pontos:

```python
# :59-62
from app.services.ferramenta_service import custo_maximo_estimado
reserva = custo_maximo_estimado()
try:
    await credito_service.reservar_creditos(db, str(usuario.id), reserva)
except ValueError as exc:
    raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc
...
# :84 (rollback ao falhar enfileiramento)
await credito_service.liberar_reserva(db, str(usuario.id), reserva)
```

> Mensagem de erro 402 pode citar o valor: `f"Creditos insuficientes (necessario reservar {reserva})"`.

### 4.3 `ferramenta_service.py` — persistir tentativas e cobrar pelo real

Reescrever a assinatura e o corpo de `finalizar_sucesso` (`:237-269`):

```python
async def finalizar_sucesso(
    db,
    execucao_id: str,
    resultado_json: dict[str, Any],
    *,
    versao_atual: int,
    tentativas_revisao: int,
    tentativas_feedback: int,
) -> ExecucaoFerramenta:
    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(f"Execucao {execucao_id} nao encontrada")

    # Persistir contadores para histórico/auditoria (antes só viviam no estado do grafo)
    execucao.tentativas_revisao = tentativas_revisao
    execucao.tentativas_feedback = tentativas_feedback

    imagem_gerada = bool(resultado_json.get("imagem_url"))
    custo = calcular_custo_final(versao_atual, imagem_gerada)
    reserva = custo_maximo_estimado()

    from app.services import credito_service
    try:
        await credito_service.confirmar_debito(
            db,
            str(execucao.usuario_id),
            reservado=reserva,
            quantidade=custo,
            descricao=(
                f"Gerar artigo: {custo} creditos (base={CUSTO_BASE}, "
                f"versoes={versao_atual}, imagem={'sim' if imagem_gerada else 'nao'})"
            ),
            ferramenta="gerar_artigo",
            execucao_id=str(execucao.id),
        )
    except (ValueError, IntegrityError):          # <- também captura o CHECK constraint
        await db.rollback()                        # desfaz o débito parcial
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)
        execucao = await buscar_execucao(db, execucao_id)
        execucao.status = "falhou"
        execucao.erro_msg = "Saldo insuficiente no momento do debito"
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        return execucao

    execucao.status = "concluida"
    execucao.creditos_cobrados = custo
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    logger.info("execucao_id=%s status=concluida creditos=%d versoes=%d imagem=%s",
                execucao_id, custo, versao_atual, imagem_gerada)
    return execucao
```

Import no topo do arquivo:

```python
from sqlalchemy.exc import IntegrityError
```

> Com a reserva = teto, o `extra_necessario` de `confirmar_debito` será sempre `0` no caminho feliz (custo ≤ reserva). O bloco `except` vira defesa em profundidade.

### 4.4 `workflow.py` — passar o estado final ao finalize

Em `_run_workflow` (`:347-366`) **e** `_run_resumed_workflow` (`:428-443`), trocar a chamada:

```python
resultado = _extrair_resultado(estado_final)
await ferramenta_service.finalizar_sucesso(
    session, execucao_id, resultado,
    versao_atual=(estado_final or {}).get("versao_atual", 1),
    tentativas_revisao=(estado_final or {}).get("tentativas_revisao", 0),
    tentativas_feedback=(estado_final or {}).get("tentativas_feedback", 0),
)
```

> ⚠️ **Atenção ao caminho real**: como `aguardar_aprovacao` está sempre no fluxo, o `finalizar_sucesso` do caminho normal acontece quase sempre em `_run_resumed_workflow` (após o usuário aprovar). Aplicar a mudança **nos dois**.

### 4.5 `workflow.py` / `revisor.py` / `redator.py` — remover incremento duplicado

- `revisor.py:99`: remover a chave `"tentativas_revisao"` do dict de retorno (o nó em `workflow.py:94` é a fonte da verdade). Manter `revisao` e `aprovado_revisor`.
- `redator.py:84-88`: remover `"versao_atual": versao` do retorno (sobrescrito por `workflow.py:84`). Manter o uso local de `versao` para `salvar_versao`.
- Em `workflow.py:84` e `:94`, manter o `+1` (fonte única).

> Sem alteração de comportamento — apenas elimina código morto que confunde a leitura (e que sugeria que essa parte nunca foi testada ponta-a-ponta).

## 5. Verificação

### 5.1 Unit — custo

`backend/tests/unit/test_credito_service.py` (ou novo `test_calcular_custo_artigo.py`):

```python
def test_custo_primeira_versao_com_imagem():
    assert calcular_custo_final(versao_atual=1, imagem_gerada=True) == 20

def test_custo_tres_versoes_sem_imagem():
    assert calcular_custo_final(versao_atual=3, imagem_gerada=False) == 15 + 2*3  # 21

def test_imagem_falha_nao_cobra():
    assert calcular_custo_final(versao_atual=1, imagem_gerada=False) == 15

def test_custo_maximo_cobre_pior_caso(monkeypatch):
    # qualquer versao_atual <= max_revisoes+max_feedback deve caber na reserva
    teto = custo_maximo_estimado()
    pior = calcular_custo_final(
        versao_atual=settings.workflow_max_revisoes + settings.workflow_max_feedback,
        imagem_gerada=True,
    )
    assert pior <= teto
```

### 5.2 Integração — reserva/débito coerentes

- Reservar `custo_maximo` (38), finalizar com `versao_atual=1, imagem=True` (custo 20) → `saldo_reservado` volta a 0 e `saldo_total` cai 20 (não 38). (Cobre a matemática de `confirmar_debito`.)
- Finalizar com `versao_atual=4` → cobra `15 + 3*3 + 5 = 29`; reserva liberada corretamente.

### 5.3 E2E — contadores persistem

`backend/tests/e2e/test_e2e_workflow.py`: rodar um workflow que force ≥1 reprovação de revisor (mockar revisor para `aprovado=False` na 1ª, `True` na 2ª), aprovar como usuário, e assertar:
- `execucao.tentativas_revisao > 0` no banco (não mais 0);
- `execucao.creditos_cobrados == calcular_custo_final(versao_atual_final, imagem)`;
- `resultado_json` presente.

### 5.4 Saldo insuficiente no débito

Forçar saldo entre `custo_maximo` e o débito impossível (ex.: liberar a reserva por fora antes do finalize) → `finalizar_sucesso` marca `falhou` com `"Saldo insuficiente no momento do debito"` e **não** deixa `saldo_*` negativo (CHECK não dispara 500).

## 6. Riscos

- **Reserva maior (38)**: usuários com saldo baixo podem ver 402 onde antes passava. Mitigação: documentar; knob via `workflow_max_*`. Aceitável — é o comportamento correto.
- **Mudança de assinatura de `finalizar_sucesso`**: buscar todos os callers (`grep -rn "finalizar_sucesso(" backend`). Hoje só `workflow.py` chama a versão de artigo (as de inlinks usam funções próprias).
- **`db.rollback()` no `except`**: garante que um débito parcial não fique pendente; reabrir a execução após rollback (já feito no código acima com novo `buscar_execucao`).

## 7. Fora de escopo

- Reserva incremental just-in-time.
- Reembolso retroativo de artigos cobrados a menos no passado.
- Mudar a `CUSTOS_TABELA` exibida (manter como está; opcionalmente alinhar a descrição num PR de docs).

## 8. Arquivos alterados

- `backend/app/services/ferramenta_service.py` — `custo_maximo_estimado`, `calcular_custo_final` (sync, por versão), `_obter_reserva_estimada`, `finalizar_sucesso` (assinatura + persistência + `IntegrityError`).
- `backend/app/routers/ferramentas.py` — reservar `custo_maximo_estimado()` (2 pontos).
- `backend/app/agents/workflow.py` — passar `versao_atual/tentativas_*` ao finalize nos 2 caminhos.
- `backend/app/agents/revisor.py` — remover `tentativas_revisao` do retorno.
- `backend/app/agents/redator.py` — remover `versao_atual` do retorno.
- `backend/tests/unit/test_credito_service.py` (ou novo) + `backend/tests/e2e/test_e2e_workflow.py`.
