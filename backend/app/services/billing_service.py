from typing import Any

from sqlalchemy import select

from app.models.compra import Compra
from app.models.pacote_credito import PacoteCredito


async def listar_pacotes(db) -> list[PacoteCredito]:
    resultado = await db.execute(select(PacoteCredito).where(PacoteCredito.ativo.is_(True)).order_by(PacoteCredito.creditos))
    return list(resultado.scalars().all())


async def buscar_pacote(db, pacote_id: str) -> PacoteCredito | None:
    resultado = await db.execute(select(PacoteCredito).where(PacoteCredito.id == pacote_id, PacoteCredito.ativo.is_(True)))
    return resultado.scalar_one_or_none()


async def comprar_pacote(db, usuario_id: str, pacote_id: str) -> dict[str, Any]:
    pacote = await buscar_pacote(db, pacote_id)
    if not pacote:
        raise ValueError("Pacote nao encontrado")

    from app.models.usuario import Usuario

    usuario_result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = usuario_result.scalar_one_or_none()
    if not usuario:
        raise ValueError("Usuario nao encontrado")

    if usuario.plano_id:
        from app.models.plano import Plano

        plano_result = await db.execute(select(Plano).where(Plano.id == usuario.plano_id))
        plano = plano_result.scalar_one_or_none()
        if plano and not plano.permite_extras:
            raise ValueError("Seu plano nao permite compra de creditos extras")

    compra = Compra(
        usuario_id=usuario_id,
        tipo="addon",
        pacote_id=pacote_id,
        valor_pago=float(pacote.preco),
        status="pendente",
    )
    db.add(compra)
    await db.flush()

    from app.services import credito_service

    await credito_service.creditar_extras(
        db,
        usuario_id,
        pacote.creditos,
        descricao=f"Compra pacote {pacote.nome}: {pacote.creditos} creditos",
        pacote_id=pacote_id,
    )

    compra.status = "pago"
    await db.flush()
    return {"compra_id": str(compra.id), "creditos_adicionados": pacote.creditos}


async def listar_compras(db, usuario_id: str, limite: int = 20, offset: int = 0) -> tuple[list[Compra], int]:
    from sqlalchemy import func

    base = select(Compra).where(Compra.usuario_id == usuario_id)
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    stmt = base.order_by(Compra.criado_em.desc()).offset(offset).limit(limite)
    resultado = await db.execute(stmt)
    return list(resultado.scalars().all()), total


async def obter_plano_usuario(db, usuario_id: str) -> dict[str, Any] | None:
    from app.models.plano import Plano
    from app.models.usuario import Usuario

    usuario_result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = usuario_result.scalar_one_or_none()
    if not usuario or not usuario.plano_id:
        return None

    plano_result = await db.execute(select(Plano).where(Plano.id == usuario.plano_id))
    plano = plano_result.scalar_one_or_none()
    if not plano:
        return None

    return {
        "id": str(plano.id),
        "nome": plano.nome,
        "creditos_por_mes": plano.creditos_por_mes,
        "preco_mensal": float(plano.preco_mensal),
        "cliente_limite": plano.cliente_limite,
        "permite_extras": plano.permite_extras,
    }
