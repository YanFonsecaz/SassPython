# SPEC — Onboarding: plano `free` automático no cadastro

**Status:** ✅ implementado
**Capacidade:** `plataforma/creditos-e-billing` (toca autenticação)
**Escopo:** `backend` — cadastro, limite de clientes, migração de backfill
**Código:** `backend/app/services/auth_service.py`, `backend/app/services/credito_service.py`, `backend/app/services/cliente_service.py`, `backend/migrations/versions/0029_*.py`
**Créditos:** não cobra (concede os créditos mensais do plano free no cadastro)
**Commit/Data:** — · 2026-07-15
**Depende de:** —

---

## 1. Contexto (por quê)

**Bug crítico de onboarding encontrado no teste E2E de produção (2026-07-15).** O
`auth_service.cadastro` cria o `Usuario` **sem `plano_id`** (`auth_service.py:202-206`) e nenhum
outro caminho no código atribui plano (verificado por busca em `services/` e `routers/`: zero
atribuições de `plano_id`). Consequências em cadeia:

1. `cliente_service.verificar_limite_clientes` retorna `False` quando `usuario.plano_id is None`
   (`cliente_service.py:66-68`) → `POST /api/clientes` responde **403 "Limite de clientes atingido
   para seu plano"** (`routers/clientes.py:47-50`). Sem cliente, **nenhuma ferramenta é utilizável**.
2. Paradoxalmente, `billing_service.comprar_pacote` **pula** a checagem `permite_extras` quando o
   usuário não tem plano (`billing_service.py:31-37`) → a conta compra créditos que nunca poderá gastar.
3. O ciclo mensal nunca renova: `renovar_ciclos_vencidos` ignora contas de usuário sem `plano_id`
   (`credito_service.py:221-223`).

**Evidência de produção:** conta `yanfonsecacorp+teste-cwv-e2e@gmail.com` cadastrada via API →
compra mock de 100 créditos OK → `POST /api/clientes` **403**. Após `UPDATE usuarios SET plano_id =
<free>` direto no Supabase, a mesma chamada respondeu **201**. Na data do teste, produção tinha 1
usuário de 3 sem plano.

O seed dos planos existe desde a migração `0001_create_auth_tables.py:30-36` (`free`: 50
créditos/mês, limite 3 clientes, `permite_extras=false`). Falta apenas usá-lo no cadastro.

## 2. Requisitos / Critérios de aceite

- [ ] Dado um cadastro novo, quando `POST /api/auth/cadastro` responde 201, então o usuário tem
      `plano_id` do plano `free`, `ContaCredito` com `saldo_plano = 50` (o `creditos_por_mes` do
      plano, não hardcoded) e uma `TransacaoCredito` `tipo="renovacao"` registrada.
- [ ] Dado um usuário recém-cadastrado, quando `POST /api/clientes`, então **201** (regressão do 403).
- [ ] Dado um usuário no plano `free` (`permite_extras=false`), quando `POST /api/billing/comprar-pacote`,
      então erro de negócio com a mensagem "Seu plano nao permite compra de creditos extras"
      (comportamento que o bug hoje deixa vazar).
- [ ] Dada a migração `0029` aplicada num banco com usuários sem plano, então todos passam a
      `plano_id = free` e as contas desses usuários com `saldo_plano = 0` recebem
      `saldo_plano = creditos_por_mes` com ciclo reiniciado (30 dias).
- [ ] Dado um banco sem o plano `free` (edge; seed removido/renomeado), quando alguém se cadastra,
      então o cadastro **não falha** — o usuário é criado sem plano e um `logger.error` é emitido
      (fail-open: signup nunca quebra por causa de seed).

## 3. Design (mapeado ao código)

### 3.1 Cadastro (`auth_service.py::cadastro`, linhas 180-225)

Após o `db.flush()` do usuário (linha 208), antes da geração de tokens:

```python
# Plano free automático (SPEC_Onboarding_Plano_Free): sem plano o usuário não
# consegue criar cliente (verificar_limite_clientes) nem renovar ciclo.
try:
    plano_result = await db.execute(
        select(Plano).where(Plano.nome == "free", Plano.ativo.is_(True))
    )
    plano_free = plano_result.scalar_one_or_none()
    if plano_free:
        usuario.plano_id = plano_free.id
        await credito_service.renovar_ciclo(db, str(usuario.id), plano_free.creditos_por_mes)
    else:
        logger.error("cadastro: plano 'free' ausente — usuário %s criado sem plano", usuario.id)
except Exception:
    logger.error("cadastro: falha ao atribuir plano free a %s", usuario.id, exc_info=True)
```

**Reuso:** `credito_service.renovar_ciclo` (`credito_service.py:177-193`) já faz tudo — cria a
conta se não existir (`buscar_ou_criar_conta`), seta `saldo_plano`, ciclo de 30 dias e registra a
`TransacaoCredito` `tipo="renovacao"`. Não criar código novo de crédito.

### 3.2 Migração de backfill (`0029_backfill_plano_free.py`, down_revision `0028`)

Duas sentenças SQL idempotentes (sem ORM, padrão das migrações de dados da casa):

```sql
UPDATE usuarios SET plano_id = (SELECT id FROM planos WHERE nome = 'free' LIMIT 1)
WHERE plano_id IS NULL;

UPDATE contas_credito c SET saldo_plano = p.creditos_por_mes,
       ciclo_inicio = CURRENT_DATE, ciclo_fim = CURRENT_DATE + INTERVAL '30 days'
FROM usuarios u JOIN planos p ON p.id = u.plano_id
WHERE c.usuario_id = u.id AND c.saldo_plano = 0 AND p.nome = 'free';
```

`downgrade`: no-op documentado (não há como distinguir quem tinha plano antes).
Conferir o nome real da tabela de contas (`ContaCredito.__tablename__`) antes de escrever.

### 3.3 Mensagem do 403 (hardening opcional)

Em `routers/clientes.py:47-50`, distinguir "sem plano" de "limite atingido": se
`usuario.plano_id is None`, detail = `"Conta sem plano ativo — contate o suporte"`. Após o fix o
caminho vira inalcançável para contas novas, mas protege contra regressões e dá diagnóstico correto.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Onde atribuir o plano | No `cadastro` (backend), transacional com a criação do usuário | Endpoint de "escolher plano" no frontend — mais código, e a conta continuaria morta até o clique |
| Créditos iniciais | Conceder os 50 do free imediatamente via `renovar_ciclo` | Esperar o job diário (`scheduler.py:171`) — usuário ficaria até 30 dias com saldo 0 (ciclo novo não está vencido) |
| Free sem extras | Manter `permite_extras=false` do seed: free **não** compra pacote | Liberar extras no free — mudaria o modelo de negócio; decidir fora desta spec |
| Falha na atribuição | Fail-open com `logger.error` (signup nunca quebra) | Abortar cadastro — trocaria um bug por outro pior |
| Backfill | Migração `0029` (roda no deploy, padrão `start.sh` → `alembic upgrade head`) | Script manual — esqueceria ambientes (foi exatamente assim que produção divergiu) |

## 5. Verificação

```bash
cd backend && uv run pytest tests/unit/test_auth.py tests/unit/test_clientes.py -q
```

- `tests/unit/test_auth.py`: novo teste — cadastro via API real (fixture `client`) → `GET
  /api/billing/plano` retorna `free`; `GET /api/creditos/saldo` retorna `saldo_plano == 50`.
- `tests/unit/test_clientes.py`: regressão — cadastro → `POST /api/clientes` → **201**
  (hoje seria 403; a fixture `usuario_teste` de `conftest.py` já cobre o fluxo de cadastro real).
- Teste do edge: monkeypatch removendo/desativando o plano free → cadastro ainda responde 201.
- E2E produção (pós-deploy): cadastrar conta descartável → criar cliente → apagar.

## 6. Não-objetivos

- Fluxo de upgrade/downgrade de plano e checkout real (gateway de pagamento) — o
  `comprar_pacote` mock continua como está.
- Escolha de plano no cadastro (UI de pricing).
- Reavaliar `permite_extras` do plano free (decisão de negócio separada).
- E-mail de verificação / onboarding guiado.

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-15 | Spec criada a partir do bug encontrado no teste E2E de produção (auditoria Kumon) | — |
