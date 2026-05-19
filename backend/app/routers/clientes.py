import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.usuario import Usuario
from app.schemas.cliente import (
    ClienteCreateRequest,
    ClienteListResponse,
    ClienteResponse,
    ClienteUpdateRequest,
    MensagemResponse,
)
from app.services import cliente_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=ClienteListResponse)
async def listar_clientes(
    busca: str = Query(default=""),
    limite: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    clientes, total = await cliente_service.listar_clientes(db, str(usuario.id), busca=busca, limite=limite, offset=offset)
    return {"clientes": clientes, "total": total}


@router.post("", response_model=ClienteResponse, status_code=201)
async def criar_cliente(
    body: ClienteCreateRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    limite_ok = await cliente_service.verificar_limite_clientes(db, str(usuario.id))
    if not limite_ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Limite de clientes atingido para seu plano")

    cliente = await cliente_service.criar_cliente(
        db,
        usuario_id=str(usuario.id),
        nome=body.nome,
        site_url=body.site_url,
        config_json=body.config_json.model_dump(),
    )
    return cliente


@router.get("/{cliente_id}", response_model=ClienteResponse)
async def buscar_cliente(
    cliente_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    cliente = await cliente_service.buscar_cliente(db, cliente_id, str(usuario.id))
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return cliente


@router.put("/{cliente_id}", response_model=ClienteResponse)
async def atualizar_cliente(
    cliente_id: str,
    body: ClienteUpdateRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    update_data = body.model_dump(exclude_none=True)

    cliente = await cliente_service.atualizar_cliente(db, cliente_id, str(usuario.id), **update_data)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return cliente


@router.delete("/{cliente_id}", response_model=MensagemResponse)
async def remover_cliente(
    cliente_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    removido = await cliente_service.remover_cliente(db, cliente_id, str(usuario.id))
    if not removido:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return {"mensagem": "Cliente removido com sucesso"}
