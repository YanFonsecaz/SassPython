import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.usuario import Usuario
from app.schemas.billing import (
    ComprarPacoteRequest,
    ComprasListResponse,
    MensagemResponse,
    PacotesListResponse,
    PlanoResponse,
)
from app.services import billing_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/plano", response_model=PlanoResponse)
async def obter_plano(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    plano = await billing_service.obter_plano_usuario(db, str(usuario.id))
    if not plano:
        raise HTTPException(status_code=404, detail="Plano nao encontrado")
    return plano


@router.get("/pacotes", response_model=PacotesListResponse)
async def listar_pacotes(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    pacotes = await billing_service.listar_pacotes(db)
    return {"pacotes": pacotes}


@router.post("/comprar-pacote", response_model=MensagemResponse)
async def comprar_pacote(
    body: ComprarPacoteRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        resultado = await billing_service.comprar_pacote(db, str(usuario.id), str(body.pacote_id))
        return {"mensagem": f"{resultado['creditos_adicionados']} creditos adicionados com sucesso"}
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/historico", response_model=ComprasListResponse)
async def listar_historico(
    limite: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    compras, total = await billing_service.listar_compras(db, str(usuario.id), limite=limite, offset=offset)
    return {"compras": compras, "total": total}
