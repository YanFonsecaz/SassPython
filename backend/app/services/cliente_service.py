from typing import Any

from sqlalchemy import func, or_, select

from app.models.cliente import Cliente
from app.models.usuario import Usuario


async def criar_cliente(db, usuario_id: str, nome: str, site_url: str | None, config_json: dict[str, Any]) -> Cliente:
    cliente = Cliente(
        usuario_id=usuario_id,
        nome=nome,
        site_url=site_url,
        config_json=config_json,
    )
    db.add(cliente)
    await db.flush()
    return cliente


async def buscar_cliente(db, cliente_id: str, usuario_id: str) -> Cliente | None:
    resultado = await db.execute(
        select(Cliente).where(Cliente.id == cliente_id, Cliente.usuario_id == usuario_id, Cliente.ativo.is_(True))
    )
    return resultado.scalar_one_or_none()


async def listar_clientes(db, usuario_id: str, busca: str = "", limite: int = 20, offset: int = 0) -> tuple[list[Cliente], int]:
    base = select(Cliente).where(Cliente.usuario_id == usuario_id, Cliente.ativo.is_(True))
    if busca:
        base = base.where(or_(Cliente.nome.ilike(f"%{busca}%"), Cliente.site_url.ilike(f"%{busca}%")))

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    stmt = base.order_by(Cliente.nome).offset(offset).limit(limite)
    resultado = await db.execute(stmt)
    return list(resultado.scalars().all()), total


async def atualizar_cliente(db, cliente_id: str, usuario_id: str, **kwargs) -> Cliente | None:
    cliente = await buscar_cliente(db, cliente_id, usuario_id)
    if not cliente:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(cliente, key):
            setattr(cliente, key, value)
    await db.flush()
    await db.refresh(cliente)
    return cliente


async def remover_cliente(db, cliente_id: str, usuario_id: str) -> bool:
    cliente = await buscar_cliente(db, cliente_id, usuario_id)
    if not cliente:
        return False
    cliente.ativo = False
    await db.flush()
    return True


async def verificar_limite_clientes(db, usuario_id: str) -> bool:
    from app.models.plano import Plano

    usuario_result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = usuario_result.scalar_one_or_none()
    if not usuario or not usuario.plano_id:
        return False

    plano_result = await db.execute(select(Plano).where(Plano.id == usuario.plano_id))
    plano = plano_result.scalar_one_or_none()
    if not plano or plano.cliente_limite == -1:
        return True

    total = await db.execute(
        select(func.count()).select_from(
            select(Cliente).where(Cliente.usuario_id == usuario_id, Cliente.ativo.is_(True)).subquery()
        )
    )
    count = total.scalar() or 0
    return count < plano.cliente_limite
