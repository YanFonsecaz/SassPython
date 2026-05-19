import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select

from app.models.conta_credito import ContaCredito
from app.models.usuario import Usuario

logger = logging.getLogger(__name__)


async def criar_conta_credito(db, usuario_id: str) -> ContaCredito:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(ContaCredito).values(
        usuario_id=usuario_id,
        saldo_plano=0,
        saldo_extras=0,
        saldo_reservado=0,
        ciclo_inicio=date.today(),
        ciclo_fim=date.today() + timedelta(days=30),
    ).on_conflict_do_nothing(index_elements=["usuario_id"])
    await db.execute(stmt)
    await db.flush()
    return await buscar_conta(db, usuario_id)


async def buscar_conta(db, usuario_id: str, for_update: bool = False) -> ContaCredito | None:
    stmt = select(ContaCredito).where(ContaCredito.usuario_id == usuario_id)
    if for_update:
        stmt = stmt.with_for_update()
    resultado = await db.execute(stmt)
    return resultado.scalar_one_or_none()


async def buscar_ou_criar_conta(db, usuario_id: str, for_update: bool = False) -> ContaCredito:
    conta = await buscar_conta(db, usuario_id, for_update=for_update)
    if conta:
        return conta
    return await criar_conta_credito(db, usuario_id)


async def obter_saldo(db, usuario_id: str) -> dict[str, Any]:
    conta = await buscar_ou_criar_conta(db, usuario_id)
    return {
        "saldo_plano": conta.saldo_plano,
        "saldo_extras": conta.saldo_extras,
        "saldo_reservado": conta.saldo_reservado,
        "saldo_disponivel": conta.saldo_disponivel,
        "saldo_total": conta.saldo_total,
        "ciclo_inicio": conta.ciclo_inicio.isoformat(),
        "ciclo_fim": conta.ciclo_fim.isoformat(),
    }


async def verificar_saldo_suficiente(db, usuario_id: str, custo: int) -> bool:
    conta = await buscar_ou_criar_conta(db, usuario_id)
    return conta.saldo_disponivel >= custo


async def reservar_creditos(
    db, usuario_id: str, quantidade: int
) -> ContaCredito:
    conta = await buscar_ou_criar_conta(db, usuario_id, for_update=True)
    if conta.saldo_disponivel < quantidade:
        raise ValueError(f"Saldo insuficiente: disponivel={conta.saldo_disponivel}, necessario={quantidade}")
    conta.saldo_reservado += quantidade
    await db.flush()
    logger.info(
        "creditos_reservados",
        extra={
            "event_type": "credito.reservado",
            "usuario_id": usuario_id,
            "quantidade": quantidade,
            "saldo_reservado": conta.saldo_reservado,
        },
    )
    return conta


async def confirmar_debito(
    db, usuario_id: str, reservado: int, quantidade: int, descricao: str, ferramenta: str | None = None, execucao_id: str | None = None
) -> ContaCredito:
    conta = await buscar_ou_criar_conta(db, usuario_id, for_update=True)

    if conta.saldo_reservado < reservado:
        logger.warning(
            "confirmar_debito: reserva inconsistente usuario=%s reservado=%d esperado=%d, ajustando",
            usuario_id, conta.saldo_reservado, reservado,
        )
        reservado = conta.saldo_reservado

    conta.saldo_reservado -= reservado

    extra_necessario = max(0, quantidade - reservado)
    if extra_necessario > 0 and conta.saldo_disponivel < extra_necessario:
        raise ValueError(
            f"Saldo insuficiente para debito: necessario={quantidade}, reservado={reservado}, "
            f"extra_necessario={extra_necessario}, disponivel={conta.saldo_disponivel}"
        )

    if conta.saldo_extras >= quantidade:
        conta.saldo_extras -= quantidade
    else:
        restante = quantidade - conta.saldo_extras
        conta.saldo_extras = 0
        conta.saldo_plano -= restante

    from app.models.transacao_credito import TransacaoCredito

    transacao = TransacaoCredito(
        conta_id=conta.id,
        tipo="debito",
        quantidade=-quantidade,
        descricao=descricao,
        ferramenta=ferramenta,
        execucao_id=execucao_id,
    )
    db.add(transacao)
    await db.flush()
    logger.info(
        "debito_confirmado",
        extra={
            "event_type": "credito.debitado",
            "usuario_id": usuario_id,
            "quantidade": quantidade,
            "ferramenta": ferramenta,
            "execucao_id": execucao_id,
            "descricao": descricao,
        },
    )
    return conta


async def liberar_reserva(db, usuario_id: str, quantidade: int) -> ContaCredito:
    conta = await buscar_ou_criar_conta(db, usuario_id, for_update=True)

    if conta.saldo_reservado < quantidade:
        logger.warning(
            "liberar_reserva: reserva inconsistente usuario=%s reservado=%d liberar=%d, ajustando",
            usuario_id, conta.saldo_reservado, quantidade,
        )
        quantidade = max(0, conta.saldo_reservado)

    conta.saldo_reservado -= quantidade
    await db.flush()
    logger.info(
        "reserva_liberada",
        extra={
            "event_type": "credito.liberado",
            "usuario_id": usuario_id,
            "quantidade": quantidade,
            "saldo_reservado": conta.saldo_reservado,
        },
    )
    return conta


async def creditar_extras(db, usuario_id: str, quantidade: int, descricao: str, pacote_id: str | None = None) -> ContaCredito:
    conta = await buscar_ou_criar_conta(db, usuario_id)
    conta.saldo_extras += quantidade

    from app.models.transacao_credito import TransacaoCredito

    transacao = TransacaoCredito(
        conta_id=conta.id,
        tipo="credito_extra",
        quantidade=quantidade,
        descricao=descricao,
    )
    db.add(transacao)
    await db.flush()
    return conta


async def renovar_ciclo(db, usuario_id: str, creditos: int) -> ContaCredito:
    conta = await buscar_ou_criar_conta(db, usuario_id)
    conta.saldo_plano = creditos
    conta.ciclo_inicio = date.today()
    conta.ciclo_fim = date.today() + timedelta(days=30)

    from app.models.transacao_credito import TransacaoCredito

    transacao = TransacaoCredito(
        conta_id=conta.id,
        tipo="renovacao",
        quantidade=creditos,
        descricao=f"Renovacao mensal: {creditos} creditos",
    )
    db.add(transacao)
    await db.flush()
    return conta


async def listar_transacoes(db, usuario_id: str, limite: int = 50, offset: int = 0) -> tuple[list[Any], int]:
    conta = await buscar_ou_criar_conta(db, usuario_id)

    from app.models.transacao_credito import TransacaoCredito

    base = select(TransacaoCredito).where(TransacaoCredito.conta_id == conta.id)
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    stmt = base.order_by(TransacaoCredito.criado_em.desc()).offset(offset).limit(limite)
    resultado = await db.execute(stmt)
    transacoes = resultado.scalars().all()
    return list(transacoes), total


async def renovar_ciclos_vencidos(db) -> int:
    hoje = date.today()
    stmt = select(ContaCredito).where(ContaCredito.ciclo_fim < hoje)
    resultado = await db.execute(stmt)
    contas = resultado.scalars().all()
    count = 0
    from app.models.plano import Plano

    for conta in contas:
        usuario_result = await db.execute(select(Usuario).where(Usuario.id == conta.usuario_id))
        usuario = usuario_result.scalar_one_or_none()
        if not usuario or not usuario.plano_id:
            continue

        plano_result = await db.execute(select(Plano).where(Plano.id == usuario.plano_id))
        plano = plano_result.scalar_one_or_none()
        if not plano:
            continue
        conta.saldo_plano = plano.creditos_por_mes
        conta.ciclo_inicio = hoje
        conta.ciclo_fim = hoje + timedelta(days=30)
        count += 1
    return count
