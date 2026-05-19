import logging
import re
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.usuario import Usuario
from app.services import ferramenta_service

logger = logging.getLogger(__name__)

router = APIRouter()

IMAGENS_DIR = Path(settings.uploads_dir) / "imagens"


def _slugify(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9\-_ ]", "", s).strip().replace(" ", "-").lower()
    return s or "imagem"


@router.get("/execucoes/{execucao_id}/imagem")
async def baixar_imagem(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> FileResponse:
    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao or str(execucao.usuario_id) != str(usuario.id):
        raise HTTPException(404, "Execucao nao encontrada")
    destino_webp = IMAGENS_DIR / f"{execucao_id}.webp"
    destino_jpg = IMAGENS_DIR / f"{execucao_id}.jpg"
    destino_png = IMAGENS_DIR / f"{execucao_id}.png"
    for caminho, mime, ext in [
        (destino_webp, "image/webp", ".webp"),
        (destino_jpg, "image/jpeg", ".jpg"),
        (destino_png, "image/png", ".png"),
    ]:
        if caminho.exists():
            titulo = (execucao.resultado_json or {}).get("artigo_titulo", "imagem")
            filename = _slugify(titulo)[:80] + ext
            return FileResponse(
                caminho,
                media_type=mime,
                filename=filename,
                headers={"Cache-Control": "private, max-age=3600"},
            )
    raise HTTPException(404, "Imagem nao disponivel")
