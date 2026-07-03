# SPEC 03 — Créditos: atomicidade e auditabilidade

**Status:** 🗄️ histórico — auditoria aplicada · **Escopo:** `models/conta_credito`, `services/credito_service`, `services/ferramenta_service`, routers + migration · **Severidade:** Alta
**Cobre issues:** #4 (race over-spend — também parte do SPEC 01 como P0), #34 (race de criação de ContaCredito), parte de #25 (dead code), além de melhorias de auditoria.

**Depende de:** SPEC_01 §1.4 (reserva atômica) — esta SPEC formaliza e expande aquele fix.

---

## 3.1 — Modelo: `saldo_reservado` + UNIQUE constraint

### Mudança de schema

```sql
-- migration alembic
ALTER TABLE contas_creditos
  ADD COLUMN saldo_reservado INTEGER NOT NULL DEFAULT 0
    CHECK (saldo_reservado >= 0);

CREATE UNIQUE INDEX IF NOT EXISTS ix_contas_creditos_usuario_id_unique
  ON contas_creditos (usuario_id);

-- Garantir saldo nunca negativo (defesa em profundidade)
ALTER TABLE contas_creditos
  ADD CONSTRAINT chk_saldo_plano_nao_negativo CHECK (saldo_plano >= 0),
  ADD CONSTRAINT chk_saldo_extras_nao_negativo CHECK (saldo_extras >= 0);
```

Atualizar `ContaCredito` model com `saldo_reservado: Mapped[int]` e property:
```python
@hybrid_property
def saldo_disponivel(self) -> int:
    return self.saldo_plano + self.saldo_extras - self.saldo_reservado
```

---

## 3.2 — `reservar_creditos` atômico

```python
# services/credito_service.py

async def reservar_creditos(db: AsyncSession, usuario_id: str, quantidade: int) -> bool:
    """Reserva atomica. Retorna True se sucesso, False se saldo insuficiente.

    Idempotente: caller deve gerar reservation_id e armazenar para evitar dupla-reserva.
    """
    stmt = (
        update(ContaCredito)
        .where(
            ContaCredito.usuario_id == usuario_id,
            (ContaCredito.saldo_plano + ContaCredito.saldo_extras - ContaCredito.saldo_reservado)
                >= quantidade,
        )
        .values(saldo_reservado=ContaCredito.saldo_reservado + quantidade)
        .returning(ContaCredito.id)
    )
    result = await db.execute(stmt)
    sucesso = result.scalar_one_or_none() is not None
    await db.flush()
    return sucesso


async def confirmar_debito(
    db: AsyncSession,
    usuario_id: str,
    quantidade_reservada: int,
    quantidade_final: int,
    descricao: str,
    ferramenta: str,
    execucao_id: str,
) -> ContaCredito:
    """Confirma debito: tira do reservado + debita do saldo. Sobra (reservada - final) volta livre."""
    if quantidade_final > quantidade_reservada:
        raise ValueError(f"Custo final {quantidade_final} > reservado {quantidade_reservada}")

    conta = await buscar_conta(db, usuario_id)
    if not conta:
        raise ValueError("Conta nao encontrada")

    # Decrementar reservado completamente (libera o que sobrou)
    conta.saldo_reservado -= quantidade_reservada

    # Debitar do saldo (preferindo extras, depois plano)
    if conta.saldo_extras >= quantidade_final:
        conta.saldo_extras -= quantidade_final
    else:
        restante = quantidade_final - conta.saldo_extras
        conta.saldo_extras = 0
        conta.saldo_plano -= restante

    from app.models.transacao_credito import TransacaoCredito
    db.add(TransacaoCredito(
        conta_id=conta.id, tipo="debito", quantidade=-quantidade_final,
        descricao=descricao, ferramenta=ferramenta, execucao_id=execucao_id,
    ))
    await db.flush()
    return conta


async def liberar_reserva(db: AsyncSession, usuario_id: str, quantidade: int) -> None:
    """Libera reserva (sem debitar). Usado em falha/cancelamento."""
    await db.execute(
        update(ContaCredito)
        .where(ContaCredito.usuario_id == usuario_id)
        .values(saldo_reservado=ContaCredito.saldo_reservado - quantidade)
    )
    await db.flush()
```

---

## 3.3 — Integração nos routers

```python
# routers/ferramentas.py - gerar_artigo
custo_max = CUSTO_BASE + CUSTO_REVISAO * 3 + CUSTO_REVISAO * 3 + CUSTO_IMAGEM  # pior caso

reservou = await credito_service.reservar_creditos(db, str(usuario.id), custo_max)
if not reservou:
    raise HTTPException(402, "Creditos insuficientes")

try:
    execucao = await ferramenta_service.criar_execucao(db, ..., creditos_reservados=custo_max)
    # ... enfileirar ...
    if enfileirou_falhou:
        await credito_service.liberar_reserva(db, str(usuario.id), custo_max)
        raise
except Exception:
    await credito_service.liberar_reserva(db, str(usuario.id), custo_max)
    raise
```

Idem para `criar_distribuir_inlinks` e `criar_inlinks_automaticos`.

---

## 3.4 — `finalizar_sucesso` usa `confirmar_debito`

```python
# services/ferramenta_service.py
async def finalizar_sucesso(db, execucao_id: str, resultado_json: dict) -> ExecucaoFerramenta:
    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(...)

    custo_final = await calcular_custo_final(execucao)
    reservado = execucao.creditos_reservados or custo_final  # fallback p/ execucoes legacy

    await credito_service.confirmar_debito(
        db, str(execucao.usuario_id),
        quantidade_reservada=reservado,
        quantidade_final=custo_final,
        descricao=f"Gerar artigo: {custo_final} creditos",
        ferramenta="gerar_artigo",
        execucao_id=str(execucao.id),
    )

    execucao.status = "concluida"
    execucao.creditos_cobrados = custo_final
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    return execucao


async def finalizar_falha(db, execucao_id: str, erro_msg: str) -> ExecucaoFerramenta:
    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(...)

    if execucao.creditos_reservados:
        await credito_service.liberar_reserva(
            db, str(execucao.usuario_id), execucao.creditos_reservados
        )

    execucao.status = "falhou"
    execucao.erro_msg = erro_msg[:1000]
    execucao.creditos_cobrados = 0
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    return execucao
```

Idem para `cancelar_execucao` (libera reserva) e `finalizar_sucesso_distribuir_inlinks` (4 branches que zeram créditos liberam a reserva).

---

## 3.5 — Coluna `creditos_reservados` em `execucoes_ferramentas`

```sql
ALTER TABLE execucoes_ferramentas
  ADD COLUMN creditos_reservados INTEGER NOT NULL DEFAULT 0;
```

Necessário para `finalizar_falha` saber quanto liberar.

---

## 3.6 — `criar_conta_credito` idempotente

### Problema (#34)
Duas requests para um novo usuário criam duas contas; UNIQUE constraint mata uma → 500.

### Fix
```python
async def criar_conta_credito(db, usuario_id: str) -> ContaCredito:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(ContaCredito).values(
        usuario_id=usuario_id,
        saldo_plano=0, saldo_extras=0, saldo_reservado=0,
        ciclo_inicio=date.today(),
        ciclo_fim=date.today() + timedelta(days=30),
    ).on_conflict_do_nothing(index_elements=["usuario_id"])
    await db.execute(stmt)
    await db.flush()

    # buscar (gerado ou existente)
    r = await db.execute(select(ContaCredito).where(ContaCredito.usuario_id == usuario_id))
    return r.scalar_one()
```

---

## 3.7 — Reconciliação noturna

Job cron (apscheduler ou arq cron) que valida:
- `saldo_reservado` == sum(creditos_reservados de execucoes em status pendente/enfileirado/executando)
- Soma de `TransacaoCredito` por conta == `saldo_plano + saldo_extras` ajustado por renovações

Se divergir, log + alerta + dump para investigação.

```python
# scheduler.py
@scheduled_job("cron", hour=3, minute=0)
async def reconciliar_creditos():
    async with async_session_factory() as db:
        # ... validação ...
        for divergencia in achados:
            logger.error("reconciliacao_credito_divergencia", extra=divergencia)
```

---

## 3.8 — Remover dead code (#25)

`credito_service.py:140` — query duplicada para `Usuario` imediatamente sobrescrita por `Plano`. Limpar.

---

## Verificação

### Teste 1: race over-spend
```python
# pytest
async def test_race_over_spend():
    # Saldo 30; 3 jobs paralelos custando 20 cada (pior caso reservado)
    tasks = [client.post("/api/ferramentas/gerar-artigo", json=...) for _ in range(3)]
    responses = await asyncio.gather(*tasks)
    sucessos = sum(1 for r in responses if r.status_code == 202)
    falhas = sum(1 for r in responses if r.status_code == 402)
    assert sucessos == 1 and falhas == 2
```

### Teste 2: refund on failure
```python
async def test_refund_on_failure():
    saldo_antes = (await get_saldo()).saldo_total
    # submete job que vai falhar (URL invalida, etc.)
    await client.post("/api/ferramentas/distribuir-inlinks", json={"url_alvo": "invalid"})
    await aguardar_conclusao()
    saldo_depois = (await get_saldo()).saldo_total
    assert saldo_antes == saldo_depois  # nada cobrado
```

### Teste 3: idempotência de criar_conta
```python
async def test_create_conta_concurrent():
    novo_user_id = "..."
    tasks = [criar_conta_credito(db, novo_user_id) for _ in range(5)]
    contas = await asyncio.gather(*tasks)
    ids = {c.id for c in contas}
    assert len(ids) == 1  # mesma conta retornada
```

---

## Critério de pronto

- [ ] Coluna `saldo_reservado` + UNIQUE constraint em produção
- [ ] Coluna `creditos_reservados` em `execucoes_ferramentas`
- [ ] Endpoints reservam antes de enfileirar
- [ ] `finalizar_sucesso/falha/cancel` ajustam reserva corretamente
- [ ] `criar_conta_credito` idempotente
- [ ] Job de reconciliação rodando
- [ ] Teste de race passa
- [ ] Teste de refund passa

## Riscos
- Migration em prod precisa rodar com `CONCURRENTLY` para o índice unique.
- Dados legacy: execuções já concluídas têm `creditos_reservados=0` — `finalizar_falha` precisa lidar com isso (fallback: não libera).
- Pior caso `custo_max` para reserva pode ser conservador demais; usuário com saldo apertado vê 402 quando teria saldo suficiente para custo real. Aceita-se.
