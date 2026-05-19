import json
import logging
import re

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")


def _count_links(md: str) -> int:
    return len(_LINK_RE.findall(md))


async def formatar_pilar(markdown: str, usuario_id: str) -> str:
    if not markdown or not markdown.strip():
        return markdown

    agente = _FormatadorAgent(usuario_id)
    prompt = _build_prompt(markdown)
    try:
        resposta = await agente._invoke_llm(prompt)
        formatado = _parse(resposta)
        if formatado and _count_links(formatado) == _count_links(markdown):
            return formatado
        if formatado:
            logger.warning(
                "Formatador alterou número de links (%d -> %d); usando original",
                _count_links(markdown), _count_links(formatado),
            )
    except Exception as e:
        logger.warning("Formatador falhou: %s", e)
    return markdown


class _FormatadorAgent(BaseAgent):
    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage

        from app.core.llm_guard import chamada_llm_mensagem_com_retry

        response = await chamada_llm_mensagem_com_retry(
            self.llm, [HumanMessage(content=prompt)], self.usuario_id
        )
        return response.content


def _build_prompt(markdown: str) -> str:
    return f"""Você é um editor focado em legibilidade. Recebe um markdown de artigo
(já com inlinks aplicados) e devolve uma versão com MELHOR ESTRUTURA, sem mudar
o significado.

REGRAS:
1. Quebre parágrafos com mais de 120 palavras em parágrafos menores,
   nos pontos finais naturais (depois de "."). Não corte uma sentença
   no meio.
2. Onde o tema muda claramente, adicione um sub-heading `### Título`
   curto (3-6 palavras). Use no máximo 1 sub-heading novo a cada
   ~400 palavras.
3. NÃO mude o texto das frases. NÃO traduza. NÃO reescreva. Apenas
   reorganize a estrutura.
4. PRESERVE TODOS os links markdown `[texto](url)` exatamente como
   estão — mesma palavra-texto, mesma URL, na mesma sequência.
5. NÃO adicione listas, citações, blocos de código novos. Mantenha
   listas e blocos de código existentes.
6. Mantenha os headings existentes (H1, H2). Pode adicionar H3
   conforme regra 2, nunca remover headings.

Saída APENAS em JSON:
{{"markdown_formatado": "..."}}

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
            md = data.get("markdown_formatado", "")
            if md and len(md.strip()) > 50:
                return md
    except (json.JSONDecodeError, ValueError):
        pass
    return None
