# SPEC — Billing correto dos Inlinks (reservar pelo custo real)

**Status:** ✅ aplicado (commit 0cbe741)
**Escopo:** backend (routers + serviço + finalize dos 2 workflows)
**Crédito:** muda a **reserva** (não o preço cobrado) — ver §3
**Esforço:** ~4h
**Depende de:** nada. Primeira do plano.

## 1. Resumo

Os dois inlinks reservam só a **base** (`CUSTO_BASE_INLINKS=15` / `CUSTO_BASE_DISTRIBUIR_INLINKS=15`) mas cobram pelo nº de URLs (até **60** / **115**). Pior: o custo correto é **calculado e descartado** no router. Como o nº de URLs é conhecido no submit, dá para reservar o valor exato e liberar a diferença no débito (mesmo padrão já aplicado ao `gerar_artigo`).

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | Custo computado e jogado fora | `ferramentas_inlinks.py:33`; `ferramentas_inlinks_reversos.py:37` | `calcular_custo_*(len(candidatas_urls))` sem atribuição |
| 2 | Reserva = só a base | `ferramentas_inlinks.py:38`; `ferramentas_inlinks_reversos.py:42` | reserva `CUSTO_BASE_*` |
| 3 | `confirmar_debito(reservado=CUSTO_BASE_*)` mas `quantidade` maior | `workflow_inlinks.py:844`; `ferramenta_service.py` (`finalizar_sucesso_distribuir_inlinks`) | reservado < quantidade → débito puxa do saldo disponível; se faltar, descarta trabalho concluído |
| 4 | Liberação inconsistente em falha/cancelamento | `_obter_reserva_estimada` retorna `CUSTO_BASE_*` (`ferramenta_service.py`) | libera menos do que foi reservado se a reserva subir |

## 3. Decisão de arquitetura

**Reservar `calcular_custo_*(len(candidatas_urls))` no submit** (custo do pior caso = todas as URLs válidas) e **cobrar pelo real** (`n_validas`) no finalize, liberando a diferença. `_obter_reserva_estimada` passa a ser a **fonte única** do valor reservado, calculado a partir de `execucao.entrada_json`.

- Reserva ≥ cobrança sempre (`n_validas ≤ n_submetidas`, custo monotônico) → nunca descarta trabalho por reserva insuficiente.
- Não muda o **preço** cobrado (continua `calcular_custo_inlinks(n_validas)`), só a reserva.

### Alternativa descartada
- Reservar incremental por URL processada: mais código no meio do workflow; reservar o teto no submit é mais simples e o teto é conhecido (≠ gerar_artigo, onde dependia de loops).

## 4. Mudanças

### 4.1 `ferramenta_service.py` — `_obter_reserva_estimada` como fonte única

```python
def _obter_reserva_estimada(ferramenta: str, execucao: ExecucaoFerramenta) -> int:
    if ferramenta == "gerar_artigo":
        return custo_maximo_estimado()
    entrada = execucao.entrada_json or {}
    n_urls = len(entrada.get("candidatas_urls", []) or [])
    if ferramenta in ("inlinks", "inlinks_automaticos"):
        return calcular_custo_inlinks(n_urls)
    if ferramenta == "distribuir_inlinks":
        return calcular_custo_distribuir_inlinks(n_urls)
    if ferramenta == "core_web_vitals":
        return CUSTO_BASE_CWV          # inalterado — fora de escopo
    if ferramenta == "parecer_tecnico":
        return execucao.creditos_cobrados or CUSTO_BASE_PARECER
    return 0
```

> Isso já corrige automaticamente os caminhos de cancelamento/timeout (`workflow_inlinks.py:762`, `workflow_inlinks_reversos.py:1115`, `cancelar_execucao`, `finalizar_falha`) que já chamam `_obter_reserva_estimada`.

### 4.2 Routers — reservar o custo real

`ferramentas_inlinks.py:33-38`:

```python
from app.services.ferramenta_service import calcular_custo_inlinks  # ja importado
reserva = calcular_custo_inlinks(len(body.candidatas_urls))
try:
    await credito_service.reservar_creditos(db, str(usuario.id), reserva)
except ValueError as exc:
    raise HTTPException(status_code=402, detail=f"Creditos insuficientes (necessario reservar {reserva})") from exc
# ... e no rollback de enfileiramento (:55):
await credito_service.liberar_reserva(db, str(usuario.id), reserva)
```

`ferramentas_inlinks_reversos.py:37-42` — análogo com `calcular_custo_distribuir_inlinks(len(body.candidatas_urls))`.

### 4.3 Finalize inlinks_automaticos — `reservado` = reserva real

`workflow_inlinks.py:_finalizar_sucesso_inlinks` (`:799-867`): substituir todo uso de `CUSTO_BASE_INLINKS` como valor de reserva por `reserva = ferramenta_service._obter_reserva_estimada("inlinks_automaticos", execucao)`:

```python
reserva = ferramenta_service._obter_reserva_estimada("inlinks_automaticos", execucao)

if n_processadas == 0:
    await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)  # era CUSTO_BASE_INLINKS
    ...

# no confirmar_debito:
await credito_service.confirmar_debito(
    db, str(execucao.usuario_id),
    reservado=reserva,                       # era CUSTO_BASE_INLINKS
    quantidade=custo,                        # calcular_custo_inlinks(n_validas), com base waived se n_aplicados==0
    ...
)
# no except ValueError:
await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)  # era CUSTO_BASE_INLINKS
```

> O cálculo de `custo` (base waived quando `n_aplicados == 0`) **não muda**. Só o `reservado=`/liberação passam a refletir a reserva real. Como `reserva ≥ custo`, o `confirmar_debito` libera a diferença corretamente.

### 4.4 Finalize distribuir_inlinks — idem

`ferramenta_service.py:finalizar_sucesso_distribuir_inlinks` (`:326-410`): trocar todos os `CUSTO_BASE_DISTRIBUIR_INLINKS` usados como reserva (liberação nas branches `alvo_invalido`, `n_validas==0`, `n_aplicadas+n_sugestoes==0`, e o `reservado=` + `except`) por:

```python
reserva = _obter_reserva_estimada("distribuir_inlinks", execucao)
```

e usar `reserva` em todas as `liberar_reserva(...)` e no `reservado=` do `confirmar_debito`.

## 5. Verificação

### 5.1 Unit — `_obter_reserva_estimada`

```python
def _fake_exec(urls): 
    e = SimpleNamespace(entrada_json={"candidatas_urls": urls}, creditos_cobrados=0)
    return e

def test_reserva_inlinks_por_n_urls():
    assert _obter_reserva_estimada("inlinks_automaticos", _fake_exec(["u"]*10)) == calcular_custo_inlinks(10)  # 25
    assert _obter_reserva_estimada("inlinks_automaticos", _fake_exec(["u"]*100)) == CUSTO_MAX_INLINKS          # 60 (cap)

def test_reserva_distribuir_por_n_urls():
    assert _obter_reserva_estimada("distribuir_inlinks", _fake_exec(["u"]*50)) == calcular_custo_distribuir_inlinks(50)
```

### 5.2 Integração — reserva cobre o débito

- Reservar `calcular_custo_inlinks(20)=35`; finalizar com `n_validas=20, n_aplicados>0` (custo 35) → `saldo_reservado` zera, débito 35.
- Reservar 35; finalizar com `n_validas=5` (custo 20) → débito 20, libera 15.
- `n_validas=0` → libera os 35 (não só 15).
- Saldo entre base e custo real (ex.: 20 disponível, 100 URLs) → **router** retorna 402 no submit (não deixa começar), em vez de falhar no fim.

### 5.3 Regressão — não quebrar CWV/parecer

`_obter_reserva_estimada("core_web_vitals", exec)` e `("parecer_tecnico", exec)` mantêm o valor anterior. Rodar os testes de CWV/parecer existentes.

## 6. Riscos

- **Reserva maior no submit**: usuários com saldo entre 15 e o custo real agora recebem 402 (correto — não podem pagar). Documentar.
- **`entrada_json` sem `candidatas_urls`**: `_obter_reserva_estimada` usa `.get(..., [])` → reserva = base (15) no pior caso de dado ausente. Seguro.
- **Coordenação com SPEC-B**: ambas tocam `workflow_inlinks.py`. SPEC-B adiciona caminho de falha do pilar que também usa `_obter_reserva_estimada` (já coberto).

## 7. Fora de escopo

- Revisar reserva de CWV/parecer (mesma classe de bug? avaliar em PR próprio).
- Reembolso retroativo.

## 8. Arquivos alterados

- `backend/app/services/ferramenta_service.py` — `_obter_reserva_estimada` (inlinks/distribuir por nº de URLs); `finalizar_sucesso_distribuir_inlinks` (reserva real).
- `backend/app/routers/ferramentas_inlinks.py` — reservar `calcular_custo_inlinks(...)`.
- `backend/app/routers/ferramentas_inlinks_reversos.py` — reservar `calcular_custo_distribuir_inlinks(...)`.
- `backend/app/agents/workflow_inlinks.py` — `_finalizar_sucesso_inlinks` usa reserva real.
- `backend/tests/unit/` — teste de `_obter_reserva_estimada`.
