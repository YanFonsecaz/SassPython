# SPEC — Payload bruto do PSI (eliminar DB bloat + memória)

**Status:** pendente
**Escopo:** backend (`agents/cwv/workflow.py` + `services/cwv_persistencia.py`)
**Crédito:** não muda
**Esforço:** ~3h
**Depende de:** nada (pode ir em paralelo; coordena com SPEC-A/D no `workflow.py`)

## 1. Resumo

O payload bruto do PageSpeed/Lighthouse (tipicamente **0,5–2 MB por análise**) é:
1. **gravado** em `CwvAnalise.raw_psi_json` (JSONB) e **nunca lido** em lugar nenhum (confirmado por grep) → bloat de banco write-only;
2. **carregado em todo o estado do grafo** (`psi_resultados[...]["payload"]`), apesar de só `detectar_plataforma` precisar dele (e só de um subconjunto).

Em uma execução de 50 URLs × 2 estratégias = 100 análises → ~100 MB de JSONB gravado e ~100 MB em RAM no estado.

## 2. Estado atual e problemas

| # | Local | Problema |
|---|---|---|
| 1 | `cwv_persistencia.py:65` | `raw_psi_json=psi_resultado.get("payload", {})` grava o Lighthouse inteiro |
| 2 | nenhum leitor | `raw_psi_json` nunca é lido (write-only) |
| 3 | `workflow.py:58` (state) + `:94` | `payload` fica em `psi_resultados` por todos os nós; só `detectar_plataforma(r["payload"])` usa |

## 3. Decisão de arquitetura

- **Não gravar o payload bruto**: `raw_psi_json={}` (mesmo valor já usado no branch de falha). O `parsed` (já mapeado nas colunas `lcp_ms`, `audits_totais`, etc.) cobre tudo que é consumido.
- **Descartar o payload do estado assim que `detectar_plataformas` o usa**: o nó retorna `psi_resultados` sem o campo `payload` (o reducer default sobrescreve a chave), liberando RAM para os nós seguintes e garantindo que o payload não chegue à persistência.

### Alternativas consideradas
- **Gravar um subconjunto** (ex.: `stackPacks` + diagnósticos) em vez de `{}`: só faz sentido se houver consumidor futuro; hoje não há. Manter `{}` e reabrir se necessário.
- **Tornar a coluna nullable e gravar `None`**: exige migração; `{}` evita migração e mantém `nullable=False`.

## 4. Mudanças

### 4.1 `workflow.py` — descartar payload após uso

`node_detectar_plataformas` (`:82-102`):

```python
plataformas: dict[str, str] = {}
psi_sem_payload: dict[str, dict] = {}
for _, url, estrategia in estado["jobs"]:
    chave = _chave(url, estrategia)
    r = estado["psi_resultados"].get(chave, {})
    if r.get("ok"):
        plataformas[chave] = detectar_plataforma(r["payload"])
    else:
        plataformas[chave] = "desconhecida"
    psi_sem_payload[chave] = {k: v for k, v in r.items() if k != "payload"}
# ... contagem/evento ...
return {"plataformas": plataformas, "psi_resultados": psi_sem_payload}
```

> A partir daqui, `psi_resultados` não tem mais `payload`. `node_persistir` recebe `r` sem payload.

### 4.2 `cwv_persistencia.py` — não gravar payload

`persistir_analise` (`:65`):

```python
raw_psi_json={},   # antes: psi_resultado.get("payload", {}) — nunca era lido
```

> Como o §4.1 já remove o payload do estado, o `.get("payload", {})` retornaria `{}` de qualquer forma; deixar explícito documenta a intenção e protege caso o §4.1 não seja aplicado junto.

### 4.3 (Opcional) Migração de limpeza

Migração Alembic para liberar espaço de linhas antigas:

```sql
UPDATE cwv_analises SET raw_psi_json = '{}'::jsonb
WHERE raw_psi_json <> '{}'::jsonb;
```

(Rodar `VACUUM` depois para recuperar espaço físico. Avaliar janela — tabela pode ser grande.)

## 5. Verificação

### 5.1 Unit — persistência não grava payload

```python
async def test_persistir_nao_grava_payload(session, ...):
    psi = {"ok": True, "parsed": {...}, "payload": {"lighthouseResult": {"big": "x"*100000}}}
    aid = await persistir_analise(session, ..., psi_resultado=psi, problemas=[])
    row = await session.get(CwvAnalise, aid)
    assert row.raw_psi_json == {}
    assert row.lcp_ms == ...  # parsed continua mapeado
```

### 5.2 Unit/integração — payload sai do estado

Após `node_detectar_plataformas`, `estado["psi_resultados"][chave]` não contém `"payload"`, mas mantém `"ok"`/`"parsed"`/`"estrategia"`. Plataformas detectadas corretamente.

### 5.3 Regressão

Workflow CWV end-to-end (com PSI mockado) conclui, detecta plataforma, persiste métricas e problemas normalmente; `raw_psi_json == {}`.

## 6. Riscos

- **Perda do bruto para debug**: hoje ninguém usa, mas se quiserem reprocessar/auditar o Lighthouse cru depois, não estará salvo. Mitigação: a re-análise (`/reanalisar`) já busca PSI fresco. Se debug for necessário, gravar subconjunto pequeno (§3 alternativa).
- **Migração de limpeza** em tabela grande: `UPDATE` + `VACUUM` podem ser pesados — rodar fora de pico (opcional, fora do fix de código).

## 7. Fora de escopo

- Compressão/armazenamento externo do bruto.
- Migração obrigatória (deixada opcional).

## 8. Arquivos alterados

- `backend/app/agents/cwv/workflow.py` — `node_detectar_plataformas` descarta `payload` do estado.
- `backend/app/services/cwv_persistencia.py` — `raw_psi_json={}`.
- `backend/migrations/versions/` (opcional) — limpeza de linhas antigas.
- `backend/tests/unit/` — persistência sem payload.
