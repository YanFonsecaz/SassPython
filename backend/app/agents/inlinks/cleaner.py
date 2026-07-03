import json
import logging

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


async def limpar_conteudo(markdown: str, usuario_id: str) -> str:
    if not markdown or not markdown.strip():
        return markdown

    agente = _CleanerAgent(usuario_id)
    prompt = _build_prompt(markdown)
    try:
        resposta = await agente._invoke_llm(prompt)
        limpo = _parse(resposta)
        return limpo or markdown
    except Exception as e:
        logger.warning("Cleaner falhou, usando markdown original: %s", e)
        return markdown


class _CleanerAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings

        super().__init__(usuario_id, temperature=settings.inlinks_cleaner_temperature)

    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage

        from app.core.llm_guard import chamada_llm_mensagem_com_retry

        response = await chamada_llm_mensagem_com_retry(
            self.llm, [HumanMessage(content=prompt)], self.usuario_id
        )
        return response.content


def _build_prompt(markdown: str) -> str:
    return f"""Você é um editor de conteúdo focado em SEO. Recebe um markdown extraído
de uma página web e devolve uma versão refinada.

REGRAS (sem reescrever o conteúdo):
1. Remova blocos finais do tipo "Leia também", "Veja também",
   "Posts relacionados", "Compartilhe", "Sobre o autor".
2. Remova listas de links que não fazem parte do corpo principal
   (geralmente no fim do artigo).
3. Normalize headings: sem H1 duplicado; remova linhas com apenas
   `#`, `##`, `###` sem texto.
4. NÃO invente texto. NÃO reescreva parágrafos. NÃO mude a ordem.
5. NÃO remova H2/H3 do corpo principal; só remova ruído explícito.
6. Mantenha listas, blocos de código e citações intactos.

Saída APENAS em JSON:
{{"markdown_limpo": "..."}}

Markdown original:
<<<
{markdown}
>>>"""


def _parse(response: str) -> str | None:
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            limpo = data.get("markdown_limpo", "")
            if limpo and len(limpo.strip()) > 50:
                return limpo
    except (json.JSONDecodeError, ValueError):
        pass
    return None
