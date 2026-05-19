# mypy baseline

## Estado atual (após SPEC 10)

| Métrica | Valor |
|---|---|
| Total de erros | 324 (vs 524 inicial, -38%) |
| Arquivos com erro | 53 / 92 |

## Top categorias

```
135 [no-untyped-def]      missing type annotations
 46 [no-any-return]        returns Any to typed function
 43 [no-untyped-call]      call to untyped function
 31 [arg-type]             wrong argument type
 18 [call-overload]        SQLAlchemy/LangGraph overload mismatch
 11 [assignment]
  7 [untyped-decorator]
  7 [name-defined]
  6 [misc]
  5 [return-value]
```

## Política de typing (definida em `pyproject.toml`)

- **Global**: `strict = false` + `strict_optional = true` + `check_untyped_defs = true`
- **Strict por módulo** (já passando):
  - `app.config`
  - `app.core.seguranca`
  - `app.core.rate_limit`
  - `app.core.user_cache`
- **Models**: `disable_error_code = ["name-defined"]` (forward refs SQLAlchemy)

## Como rodar

```bash
python3 -m mypy app/
```

## Como subir a régua

Quando um módulo for tipado completamente, mover para `[[tool.mypy.overrides]] strict = true` em `pyproject.toml`.

Prioridade sugerida para próximos sprints:
1. `app/services/*` (~50 erros) — serviços puros, fáceis de tipar
2. `app/routers/*` (~30 erros) — return types via Pydantic
3. `app/core/*` restantes (~40 erros)
4. `app/agents/*` (~150 erros) — mais complexo, deixar por último
5. `app/agents/inlinks/*` (~80 erros)

## Histórico

- 2026-05-16: 524 erros (baseline)
- 2026-05-16 (SPEC 10): 324 erros (-200, type-arg corrigido em massa via sed)
