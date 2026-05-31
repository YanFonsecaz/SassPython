import logging

from app.config import settings

logger = logging.getLogger(__name__)

_vision_model = None
_redacao_model = None


def get_modelo_visao():
    global _vision_model
    if _vision_model is None:
        from langchain_openai import ChatOpenAI
        _vision_model = ChatOpenAI(
            model=settings.parecer_analisador_model,
            temperature=0.1,
            api_key=settings.openai_api_key,
        )
    return _vision_model


def get_modelo_redacao():
    global _redacao_model
    if _redacao_model is None:
        from langchain_openai import ChatOpenAI
        _redacao_model = ChatOpenAI(
            model=settings.parecer_documentador_model,
            temperature=0.3,
            api_key=settings.openai_api_key,
        )
    return _redacao_model
