import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.usuario import Usuario
from app.schemas.mfa import MfaDispositivoResponse
from app.services import mfa_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/mfa/dispositivos", response_model=list[MfaDispositivoResponse])
async def listar_mfa_dispositivos(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[MfaDispositivoResponse]:
    dispositivos = await mfa_service.obter_dispositivos_usuario(db, str(usuario.id))
    return [
        MfaDispositivoResponse(
            id=str(d.id),
            nome=d.nome,
            tipo=d.tipo,
            criado_em=d.criado_em.isoformat() if d.criado_em else "",
        )
        for d in dispositivos
    ]
