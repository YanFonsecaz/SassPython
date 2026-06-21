import logging
from functools import lru_cache
from typing import Any, TypeVar

from app.config import settings
from app.core.llm_guard import chamada_llm_com_retry

logger = logging.getLogger(__name__)

T = TypeVar("T")


@lru_cache(maxsize=16)
def _get_chat_model(provider: str, model: str, temperature: float, api_key: str):
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)
    from langchain_community.chat_models import ChatZhipuAI
    return ChatZhipuAI(model=model, temperature=temperature, api_key=api_key)


class BaseAgent:
    def __init__(self, usuario_id: str, tools: list | None = None, *, temperature: float | None = None, model: str | None = None):
        self.usuario_id = usuario_id
        self.llm = _get_chat_model(
            settings.llm_provider,
            model or settings.llm_model,
            settings.llm_temperature if temperature is None else temperature,
            settings.openai_api_key if settings.llm_provider == "openai" else settings.zhipuai_api_key,
        )
        self._tools = tools or []
        if self._tools:
            self.llm = self.llm.bind_tools(self._tools)

    async def invoke(self, chain, input_data: dict[str, Any]) -> dict[str, Any]:
        resultado = await chamada_llm_com_retry(chain, input_data, self.usuario_id)
        if isinstance(resultado, dict):
            return resultado
        return {"output": resultado.content}

    async def invoke_structured(self, prompt, schema: type[T]) -> T:
        chain = self.llm.with_structured_output(schema, method="function_calling")
        return await chamada_llm_com_retry(chain, prompt, self.usuario_id)

    async def invoke_raw(self, prompt):
        from langchain_core.messages import AIMessage

        resultado = await chamada_llm_com_retry(self.llm, prompt, self.usuario_id)
        if isinstance(resultado, AIMessage):
            return resultado
        return {"output": resultado.content}

    async def invoke_with_tools(self, messages: list, max_iter: int = 4):
        """Loop ReAct simples: LLM responde, se houver tool_call executa e re-injeta."""
        from langchain_core.messages import AIMessage, ToolMessage

        for _ in range(max_iter):
            resp = await chamada_llm_com_retry(self.llm, messages, self.usuario_id)
            if not isinstance(resp, AIMessage):
                return resp
            tool_calls = getattr(resp, "tool_calls", None) or []
            if not tool_calls:
                return resp
            messages.append(resp)
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_fn = next((t for t in self._tools if t.name == tool_name), None)
                if not tool_fn:
                    content = f"ERRO: tool {tool_name} nao existe"
                else:
                    try:
                        content = await tool_fn.ainvoke(tool_args)
                    except Exception as e:
                        content = f"ERRO ao executar {tool_name}: {e}"
                messages.append(ToolMessage(content=str(content), tool_call_id=tc["id"]))
        return resp
