# SPEC — Billing CWV (corrigir vazamento de reserva)

**Status:** ✅ aplicado (commit e50a3e6)
**Escopo:** backend (`ferramenta_service.py` + `agents/cwv/workflow.py`)
**Crédito:** corrige vazamento (não muda o preço cobrado)
**Esforço:** ~3h
**Depende de:** nada. Primeira do plano.

## 1. Resumo

O router CWV reserva o **custo total** (`calcular_custo_cwv(n_urls*2)`), o que é correto. Mas **todos** os caminhos de finalização liberam/confirmam apenas `CUSTO_BASE_CWV=15`. Como `confirmar_debito` faz `saldo_reservado -= reservado`, a diferença (`reserva − 15`) fica presa em `saldo_reservado` **para sempre**, em toda execução (sucesso ou falha). O `saldo_disponível` do usuário (= total − reservado) encolhe permanentemente.

Exemplo (10 URLs): reserva = `calcular_custo_cwv(20)` = 35; libera/confirma 15 → **20 créditos vazam** por execução.

## 2. Estado atual e problemas

| # | Local | Problema |
|---|---|---|
| 1 | `ferramenta_service._obter_reserva_estimada("core_web_vitals")` | retorna `CUSTO_BASE_CWV` (15), não o reservado real |
| 2 | `workflow.py:471` (`confirmar_debito`) | `reservado=custo_base` (15), mas reservou-se o total |
| 3 | `workflow.py:450, 478` (psi_total / saldo) | `liberar_reserva(…, custo_base=15)` |
| 4 | `workflow.py:337` (cliente removido) | `liberar_reserva(…, CUSTO_BASE_CWV)` |
| 5 | `workflow.py:392` (cancelamento) | já chama `_obter_reserva_estimada` → corrigido automaticamente pelo #1 |

## 3. Decisão de arquitetura

`_obter_reserva_estimada("core_web_vitals", execucao)` passa a **calcular o reservado real** a partir do `entrada_json` (`calcular_custo_cwv(n_urls*2)`), virando a fonte única. Todos os finalizes usam esse valor em `liberar_reserva` e no `reservado=` do `confirmar_debito`. (Mesma técnica do `SPEC_Billing_Inlinks.md`.)

- Reserva ≥ cobrança sempre (`n_sucesso ≤ n_urls*2`, custo monotônico) → débito libera a diferença corretamente, sem sobra presa.
- Não muda o preço (`quantidade = calcular_custo_cwv(n_sucesso)`).

## 4. Mudanças

### 4.1 `ferramenta_service.py` — reserva real do CWV

```python
def _obter_reserva_estimada(ferramenta: str, execucao: ExecucaoFerramenta) -> int:
    if ferramenta == "gerar_artigo":
        return custo_maximo_estimado()
    entrada = execucao.entrada_json or {}
    if ferramenta in ("inlinks", "inlinks_automaticos"):
        return calcular_custo_inlinks(len(entrada.get("candidatas_urls", []) or []))
    if ferramenta == "distribuir_inlinks":
        return calcular_custo_distribuir_inlinks(len(entrada.get("candidatas_urls", []) or []))
    if ferramenta == "core_web_vitals":
        upt = entrada.get("urls_por_template", {}) or {}
        n_urls = sum(len(v) for v in upt.values() if isinstance(v, list))
        return calcular_custo_cwv(n_urls * 2)
    if ferramenta == "parecer_tecnico":
        return execucao.creditos_cobrados or CUSTO_BASE_PARECER
    return 0
```

> `n_urls * 2` espelha o router (`ferramentas_cwv.py:66`) e a re-análise (`:207` reserva `calcular_custo_cwv(2)`; entrada terá 1 URL → bate).

### 4.2 `workflow.py` — `_run_workflow_cwv` usa a reserva real

No início de `_run_workflow_cwv` (após buscar `execucao`):

```python
reserva = ferramenta_service._obter_reserva_estimada("core_web_vitals", execucao)
```

- Branch psi_total (`:450`): `await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)`
- `confirmar_debito` (`:471`): `reservado=reserva` (manter `quantidade=custo`; o `descricao` pode manter `base={custo_base}` como rótulo informativo)
- `except ValueError` (`:478`): `liberar_reserva(…, reserva)`

### 4.3 `workflow.py` — branch "cliente removido"

`executar_workflow_cwv` (`:336-337`): trocar `CUSTO_BASE_CWV` por `_obter_reserva_estimada`:

```python
reserva = ferramenta_service._obter_reserva_estimada("core_web_vitals", execucao)
await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
```

> O branch `except CancelledError` (`:392`) e `finalizar_falha(..., "core_web_vitals")` (timeout/erro) já usam `_obter_reserva_estimada` → corrigidos pelo §4.1.

## 5. Verificação

### 5.1 Unit — reserva real

```python
def _exec_cwv(n): 
    return SimpleNamespace(entrada_json={"urls_por_template": {"blog": ["u"]*n}}, creditos_cobrados=0)

def test_reserva_cwv_por_urls():
    assert _obter_reserva_estimada("core_web_vitals", _exec_cwv(10)) == calcular_custo_cwv(20)  # 35
    assert _obter_reserva_estimada("core_web_vitals", _exec_cwv(50)) == CUSTO_MAX_CWV           # 100 (cap)
    assert _obter_reserva_estimada("core_web_vitals", _exec_cwv(1)) == calcular_custo_cwv(2)    # 17
```

### 5.2 Integração — sem sobra presa

Cenário: reservar `calcular_custo_cwv(20)=35`; concluir com `n_sucesso=20` (custo 35) → `saldo_reservado` volta ao valor inicial (0 a mais); débito 35. **Antes:** sobravam 20 presos.

Sucesso parcial: reservar 35, `n_sucesso=12` (custo 27) → débito 27, libera 8, `saldo_reservado` zera.

### 5.3 Regressão

`_obter_reserva_estimada` para `gerar_artigo`/`inlinks`/`distribuir_inlinks`/`parecer_tecnico` inalterado (rodar testes existentes desses).

### 5.4 Backfill (opcional)

Usuários afetados têm `saldo_reservado` inflado por execuções passadas. Script opcional para recomputar `saldo_reservado` a partir de execuções ainda em `executando`/pendentes e zerar resíduo de execuções já terminais. **Fora do escopo do fix de código** — avaliar à parte.

## 6. Riscos

- **`entrada_json` legado sem `urls_por_template`**: `.get(..., {})` → n_urls=0 → reserva `calcular_custo_cwv(0)=CUSTO_BASE_CWV=15`. Igual ao comportamento atual (seguro).
- **Coordenação**: SPEC-B/D também tocam `workflow.py`. Merge com atenção.

## 7. Fora de escopo

- Backfill de `saldo_reservado` histórico (script separado).
- Revisar parecer (avaliar se tem classe similar de bug — PR próprio).

## 8. Arquivos alterados

- `backend/app/services/ferramenta_service.py` — `_obter_reserva_estimada` (branch CWV por nº de URLs).
- `backend/app/agents/cwv/workflow.py` — `_run_workflow_cwv` e branch "cliente removido" usam a reserva real.
- `backend/tests/unit/` — teste da reserva CWV.
