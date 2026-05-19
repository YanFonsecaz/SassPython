import base64
import io
import logging
from pathlib import Path

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

IMAGENS_DIR = Path(settings.uploads_dir) / "imagens"
IMAGENS_DIR.mkdir(parents=True, exist_ok=True)


def _converter_para_webp(dados: bytes, destino: Path) -> Path:
    img = Image.open(io.BytesIO(dados))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    webp_path = destino.with_suffix(".webp")
    img.save(webp_path, "WEBP", quality=85)
    if webp_path != destino:
        destino.unlink(missing_ok=True)
    return webp_path


async def persistir_imagem(imagem_url: str | None, execucao_id: str) -> str | None:
    if not imagem_url:
        return None
    destino = IMAGENS_DIR / f"{execucao_id}.png"
    try:
        if imagem_url.startswith("data:image/"):
            _, b64 = imagem_url.split(",", 1)
            destino.write_bytes(base64.b64decode(b64))
        else:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(imagem_url)
                resp.raise_for_status()
                destino.write_bytes(resp.content)
        destino = _converter_para_webp(destino.read_bytes(), destino)
        logger.info("imagem_persistida", extra={
            "event_type": "imagem.persistida",
            "execucao_id": execucao_id,
            "tamanho_bytes": destino.stat().st_size,
        })
        return f"/api/execucoes/{execucao_id}/imagem"
    except Exception as e:
        logger.warning("Falha ao persistir imagem para %s: %s", execucao_id, e)
        return imagem_url
