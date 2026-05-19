import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.usuario import Usuario
from app.schemas.credito import SaldoResponse, TransacoesListResponse
from app.services import credito_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/saldo", response_model=SaldoResponse)
async def obter_saldo(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    saldo = await credito_service.obter_saldo(db, str(usuario.id))
    return saldo


@router.get("/transacoes", response_model=TransacoesListResponse)
async def listar_transacoes(
    limite: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    transacoes, total = await credito_service.listar_transacoes(db, str(usuario.id), limite=limite, offset=offset)
    return {"transacoes": transacoes, "total": total}
