# SPEC 08 — Code quality cleanup (low-risk refactors)

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** vários arquivos · **Severidade:** Baixa (mas alta dívida técnica)
**Cobre issues:** #18 (mutex em gather), #23 (criar_execucao hardcoded), #24 (datetime.utcnow), #25 (dead code já em SPEC 03), #26 (imports tardios), #27 (CORS já em SPEC 02), #29 (SPA via FastAPI já em SPEC 02), #30 (imports tardios), #32 (INSERT loop), #33 (saida_json vs resultado_json), #35 (status race aprovar), #38 (file size), #43 (publish_event datetime.utcnow)

Tudo aqui é mecânico/seguro. Pode rodar como **1 PR único** ou separado por tema. Sem mudança de comportamento esperada.

---

## 8.1 — Migrar `datetime.utcnow()` → `datetime.now(UTC)`

`datetime.utcnow()` é DEPRECATED em Python 3.12 e remoção planejada. Plus, retorna naive, complicando timezone.

### Ocorrências (grep + replace)
```bash
grep -rn "datetime.utcnow()" backend/app/
# resultado esperado: 20+ arquivos
```

Fix global:
```python
# Antes:
from datetime import datetime
... datetime.utcnow() ...

# Depois:
from datetime import datetime, UTC
... datetime.now(UTC) ...
```

Arquivos afetados:
- `services/auth_service.py`
- `services/ferramenta_service.py`
- `services/credito_service.py`
- `routers/ferramentas*.py`
- `routers/ferramentas_inlinks_reversos.py`
- `core/workflow_events.py`
- `worker.py`
- `agents/workflow*.py`

### Cuidado
Algumas colunas DB são `TIMESTAMP WITHOUT TIME ZONE`. Aware datetime escreve com offset que pode confundir. **Avaliar migração** das colunas para `TIMESTAMPTZ`:

```sql
-- migration alembic
ALTER TABLE execucoes_ferramentas
  ALTER COLUMN criado_em TYPE TIMESTAMPTZ USING criado_em AT TIME ZONE 'UTC',
  ALTER COLUMN concluida_em TYPE TIMESTAMPTZ USING concluida_em AT TIME ZONE 'UTC',
  ALTER COLUMN timeout_em TYPE TIMESTAMPTZ USING timeout_em AT TIME ZONE 'UTC';
-- mesma migration para outras tabelas: usuarios, sessoes, conteudos_vetores, etc.
```

---

## 8.2 — Imports tardios → top-level

### Problema (#26, #30)
- `core/embeddings.py:cosine_seguro` faz `from numpy import dot; from numpy.linalg import norm` por chamada (milhares de vezes em workflow).
- `agents/workflow_inlinks*.py:_sanitize` faz `import numpy as np` por chamada.
- Diversos `from app.services import ferramenta_service` dentro de funções de router.

### Fix
Mover para topo do arquivo. Imports tardios eram para evitar circular deps; resolver com lazy imports apenas onde **realmente** há ciclo.

```python
# core/embeddings.py (topo)
import math
import numpy as np
from numpy.linalg import norm

def cosine_seguro(a, b) -> float:
    try:
        result = float(np.dot(a, b) / (norm(a) * norm(b) + 1e-8))
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception:
        return 0.0
```

### Identificar ciclos
```bash
python3 -X importtime -c "import app.main" 2>&1 | grep -E "circular|cycle"
```

Resolver removendo dependências cruzadas em vez de tardio import.

---

## 8.3 — `criar_execucao` hardcoded `ferramenta="gerar_artigo"`

### Problema (#23)
`services/ferramenta_service.py:47-60` — função "genérica" mas hardcoded para um caso. Distribuir Inlinks tem sua própria função privada `_criar_execucao_distribuir`.

### Fix
```python
async def criar_execucao(
    db,
    usuario_id: str,
    cliente_id: str | None,
    ferramenta: str,          # ← novo parâmetro
    entrada: dict,
    timeout_seconds: int | None = None,
    creditos_reservados: int = 0,
) -> ExecucaoFerramenta:
    timeout_seconds = timeout_seconds or settings.workflow_timeout_segundos
    entrada_json = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in entrada.items()}
    execucao = ExecucaoFerramenta(
        usuario_id=usuario_id,
        cliente_id=cliente_id,
        ferramenta=ferramenta,
        status="pendente",
        entrada_json=entrada_json,
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=timeout_seconds),
        creditos_reservados=creditos_reservados,
    )
    db.add(execucao)
    await db.flush()
    return execucao
```

Eliminar `_criar_execucao_distribuir` em `routers/ferramentas_inlinks_reversos.py`, usar o genérico.

---

## 8.4 — Bulk inserts no `node_persistir`

### Problema (#32)
`workflow_inlinks_reversos.py:932-967` faz INSERT + flush por candidata. 100 candidatas = 100 round-trips.

### Fix
```python
# substitui o loop atual
versoes_para_salvar = []
inlinks_para_salvar = []

for idx, c in enumerate(candidatas):
    if c["status"] == "aplicado" and c.get("markdown_modificado"):
        versoes_para_salvar.append({
            "execucao_id": eid,
            "versao": versao_n + idx,
            "origem": f"distribuir_v{idx}"[:30],
            ...
        })

    if c["status"] in ("aplicado", "sugestao_manual"):
        inlinks_para_salvar.append(InlinkSugerido(
            execucao_id=eid,
            url_origem=c.get("url_canonica", c["url"]),
            ...
        ))

if versoes_para_salvar:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(VersaoArtigo).values(versoes_para_salvar).on_conflict_do_nothing(...)
    await session.execute(stmt)

if inlinks_para_salvar:
    session.add_all(inlinks_para_salvar)

await session.commit()  # 1 flush ao final
```

---

## 8.5 — Atualização atômica no `aprovar_reprovar`

### Problema (#35)
`routers/ferramentas.py:277-283` — muda status para "executando" antes de garantir enfileiramento. Race com SSE.

### Fix
```python
# Tentar enfileirar PRIMEIRO; só atualiza status se sucesso
job_id = await _enqueue_retomada(execucao_id, body.acao, body.feedback)
if not job_id:
    raise HTTPException(500, "Falha ao enfileirar retomada")

# Agora sim, atualizar status atomicamente
await ferramenta_service.atualizar_execucao(
    db, execucao_id, status="executando", job_id=job_id,
)
await db.commit()
return {"mensagem": "Acao registrada com sucesso"}
```

---

## 8.6 — Renomear `saida_json` referências → `resultado_json` (#33)

```bash
grep -rn "saida_json" backend/ docs/
# remover/atualizar referências obsoletas em comentários
```

A coluna DB é `resultado_json`. Manter consistência total.

---

## 8.7 — Split de `workflow_inlinks_reversos.py` (1059 linhas) (#38)

Extrair helpers para módulos próprios:

```
backend/app/agents/distribuir_inlinks/
├── __init__.py
├── workflow.py              # StateGraph, criar_workflow_distribuir, executar
├── nodes.py                 # node_validar_urls, node_extrair_*, etc.
├── slug_fallback.py         # _detectar_boilerplate, _construir_pseudo_alvo, etc.
├── filter.py                # node_filtrar_similaridade + helpers de override
└── state.py                 # EstadoDistribuir TypedDict
```

Cada arquivo ≤ 300 linhas. Imports e visibilidade explícitos.

Mesma divisão para `workflow_inlinks.py` (485 linhas, fronteira aceitável mas justa).

---

## 8.8 — Defesa em `inserir_em_cada` lock para gather (#18)

Mesmo com GIL protegendo `list.append`, melhor explicitar:

```python
import asyncio
resultados_lock = asyncio.Lock()
resultados: list[dict] = []

async def _inserir_candidata(idx: int, candidata: dict):
    # ... lógica ...
    async with resultados_lock:
        resultados.append({...})

tasks = [_inserir_candidata(i, c) for i, c in enumerate(candidatas_viaveis)]
await asyncio.gather(*tasks)
```

Custo desprezível, semântica clara.

---

## 8.9 — `publish_event` usa `datetime.now(UTC)` (#43)

```python
# core/workflow_events.py
from datetime import datetime, UTC

async def publish_event(...):
    payload = {
        "type": event_type,
        "node": node,
        "detail": detail,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    ...
```

---

## 8.10 — Remover dead code em `credito_service.py` (#25)

`services/credito_service.py:140` — query sobrescrita. Já mencionado em SPEC 03 §3.8 — confirmar limpeza aqui.

---

## 8.11 — Ruff / mypy estritos

```toml
# pyproject.toml
[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = [
    "E", "F", "W",          # pycodestyle, pyflakes
    "I",                     # isort
    "B",                     # flake8-bugbear
    "RUF",                   # ruff-specific
    "UP",                    # pyupgrade (sugere UTC etc)
    "ASYNC",                 # flake8-async (catches sleep in async)
    "SIM",                   # flake8-simplify
]
ignore = ["E501"]

[tool.mypy]
python_version = "3.12"
strict = true
disable_error_code = ["call-overload"]  # SQLAlchemy gera muito disso
```

```bash
ruff check app/ --fix
mypy app/
```

Aplicar fixes graduais; documentar exceções em `# noqa` ou `# type: ignore` apenas quando justificado.

---

## Critério de pronto

- [ ] Zero ocorrências de `datetime.utcnow()` em backend
- [ ] Colunas TIMESTAMP → TIMESTAMPTZ
- [ ] Imports de numpy, sqlalchemy, langchain estão no topo
- [ ] `criar_execucao(ferramenta=...)` unificada
- [ ] `node_persistir` faz bulk insert
- [ ] `aprovar_reprovar` enfileira antes de atualizar status
- [ ] `saida_json` removido (substituído por `resultado_json`)
- [ ] `workflow_inlinks_reversos.py` quebrado em subdir
- [ ] Lock explícito no `inserir_em_cada`
- [ ] `ruff check` passa em CI
- [ ] `mypy --strict` passa (com exceções documentadas)

## Riscos
- Migração TIMESTAMPTZ requer cuidado: rodar em horário de baixo tráfego, dados existentes considerados UTC.
- Split de file: imports relativos vs absolutos; testar localmente.
- mypy strict pode revelar bugs reais — bom! Mas atraso na primeira passagem.

## Ordem sugerida (incremental)

1. **datetime migration** (mecânico, baixo risco) — 30min
2. **dead code removal** — 5min
3. **imports tardios → topo** — 20min
4. **publish_event timestamp** — 1min
5. **bulk insert node_persistir** — 15min
6. **lock no gather** — 5min
7. **criar_execucao unificada** — 30min
8. **aprovar_reprovar atomicidade** — 10min
9. **file split** — 1h
10. **ruff/mypy strict** — 2-4h (graduais)
11. **TIMESTAMPTZ migration** — 30min + janela de manutenção

Total: ~4-6h cumulativos.
