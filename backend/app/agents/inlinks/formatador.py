import json
import logging
import re
from collections import Counter

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_LINE_RE = re.compile(r"^\s*#{1,6}\s.*$", re.MULTILINE)

# Tolerância de mutação de texto: a formatação só re-quebra parágrafos e adiciona
# H3 curtos — o corpo não deve variar mais que isso.
_MAX_DIFF_TOKENS_RATIO = 0.02


def _pares_links(md: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _LINK_RE.finditer(md)]


def _tokens_corpo(md: str) -> Counter:
    sem_headings = _HEADING_LINE_RE.sub(" ", md)
    return Counter(sem_headings.split())


def _mutacao_aceitavel(original: str, formatado: str) -> bool:
    if _pares_links(formatado) != _pares_links(original):
        return False
    t_orig = _tokens_corpo(original)
    t_fmt = _tokens_corpo(formatado)
    diff = sum((t_orig - t_fmt).values()) + sum((t_fmt - t_orig).values())
    total = max(1, sum(t_orig.values()))
    return diff / total <= _MAX_DIFF_TOKENS_RATIO


async def formatar_pilar(markdown: str, usuario_id: str) -> str:
    if not markdown or not markdown.strip():
        return markdown

    agente = _FormatadorAgent(usuario_id)
    prompt = _build_prompt(markdown)
    try:
        resposta = await agente._invoke_llm(prompt)
        formatado = _parse(resposta)
        if formatado and _mutacao_aceitavel(markdown, formatado):
            return formatado
        if formatado:
            logger.warning(
                "Formatador mudou links ou mutou o texto além do aceitável; usando original",
            )
    except Exception as e:
        logger.warning("Formatador falhou: %s", e)
    return markdown


class _FormatadorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings

        super().__init__(usuario_id, temperature=settings.inlinks_formatador_temperature)

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
