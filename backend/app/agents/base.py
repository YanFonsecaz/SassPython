import logging
from functools import lru_cache
from typing import Any, TypeVar

from app.config import settings
from app.core.llm_guard import chamada_llm_com_retry

logger = logging.getLogger(__name__)

T = TypeVar("T")


@lru_cache(maxsize=8)
def _get_chat_model(provider: str, model: str, temperature: float, api_key: str):
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)
    from langchain_community.chat_models import ChatZhipuAI
    return ChatZhipuAI(model=model, temperature=temperature, api_key=api_key)


class BaseAgent:
    def __init__(self, usuario_id: str):
        self.usuario_id = usuario_id
        self.llm = _get_chat_model(
            settings.llm_provider, settings.llm_model,
            settings.llm_temperature,
            settings.openai_api_key if settings.llm_provider == "openai" else settings.zhipuai_api_key,
        )

    async def invoke(self, chain, input_data: dict[str, Any]) -> dict[str, Any]:
        resultado = await chamada_llm_com_retry(chain, input_data, self.usuario_id)
        if isinstance(resultado, dict):
            return resultado
        return {"output": resultado.content}

    async def invoke_structured(self, prompt, schema: type[T]) -> T:
        chain = self.llm.with_structured_output(schema)
        return await chamada_llm_com_retry(chain, prompt, self.usuario_id)

    async def invoke_raw(self, prompt):
        from langchain_core.messages import AIMessage

        resultado = await chamada_llm_com_retry(self.llm, prompt, self.usuario_id)
        if isinstance(resultado, AIMessage):
            return resultado
        return {"output": resultado.content}
