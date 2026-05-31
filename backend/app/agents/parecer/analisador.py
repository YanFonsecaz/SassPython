import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.parecer.modelos import get_modelo_visao
from app.core.llm_guard import chamada_llm_mensagem_com_retry
from app.schemas.parecer import AchadoImagem

logger = logging.getLogger(__name__)

SYSTEM_ANALISE = (
    "Voce e um especialista em SEO tecnico e Core Web Vitals. Recebe UM print (screenshot) de "
    "ferramentas como Chrome DevTools / PageSpeed / DOM, com uma nota curta do analista. "
    "Descreva objetivamente o que o print mostra e identifique o problema tecnico, seu impacto e "
    "onde ocorre. Nao invente dados que nao estejam visiveis. Responda em portugues."
)


def _achado_degradado(indice: int, erro: str) -> AchadoImagem:
    return AchadoImagem(
        indice_global=indice,
        o_que_mostra="Evidencia nao analisada automaticamente",
        problema="Analise automatica falhou",
        impacto=["Outro"],
        onde_ocorre="Desconhecido",
        confianca=0.0,
        degradado=True,
    )


async def analisar_imagem(usuario_id: str, indice: int, data_uri: str, nota: str) -> AchadoImagem:
    if data_uri.startswith("data:image/gif"):
        try:
            import io

            from PIL import Image as PILImage
            _header, b64 = data_uri.split(",", 1)
            import base64
            raw = base64.b64decode(b64)
            img = PILImage.open(io.BytesIO(raw))
            img.seek(0)
            png = io.BytesIO()
            img.save(png, "PNG")
            png.seek(0)
            b64_png = base64.b64encode(png.read()).decode()
            data_uri = f"data:image/png;base64,{b64_png}"
        except Exception:
            logger.warning("Falha ao converter GIF para PNG, usando original", exc_info=True)

    try:
        llm = get_modelo_visao().with_structured_output(AchadoImagem, method="function_calling")
        msgs = [
            SystemMessage(content=SYSTEM_ANALISE),
            HumanMessage(content=[
                {"type": "text", "text": f"Indice da imagem: {indice}. Nota do analista: {nota or '(sem nota)'}"},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]),
        ]
        achado = await chamada_llm_mensagem_com_retry(llm, msgs, usuario_id)
        achado.indice_global = indice
        logger.info("parecer.imagem.analisada", extra={
            "event_type": "parecer.imagem.analisada",
            "indice": indice,
            "confianca": achado.confianca,
            "ok": True,
        })
        return achado
    except Exception as e:
        logger.warning("parecer.imagem.degradada", extra={
            "event_type": "parecer.imagem.degradada",
            "indice": indice,
            "erro": str(e),
        })
        return _achado_degradado(indice, str(e))
