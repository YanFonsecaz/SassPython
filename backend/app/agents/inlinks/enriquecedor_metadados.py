import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class MetadadosConteudo:
    tipo: str = "blog"
    categoria: str = ""
    intencao: str = "informacional"
    palavras_chave: list[str] = field(default_factory=list)
    entidades: list[str] = field(default_factory=list)
    resumo: str = ""


async def enriquecer_metadados(
    markdown: str, titulo: str, usuario_id: str
) -> MetadadosConteudo:
    agente = _EnriquecedorAgent(usuario_id)
    prompt = _build_prompt(markdown, titulo)
    try:
        resposta = await agente._invoke_llm(prompt)
        data = _parse(resposta)
        return MetadadosConteudo(
            tipo=data.get("tipo", "blog"),
            categoria=data.get("categoria", ""),
            intencao=data.get("intencao", "informacional"),
            palavras_chave=data.get("palavras_chave", []) or [],
            entidades=data.get("entidades", []) or [],
            resumo=data.get("resumo", ""),
        )
    except Exception as e:
        logger.warning("Enriquecedor falhou: %s", e)
        return MetadadosConteudo()


class _EnriquecedorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(usuario_id)
        from app.config import settings

        if settings.llm_provider == "openai" and settings.enriquecedor_llm_model:
            from langchain_openai import ChatOpenAI

            self.llm = ChatOpenAI(
                model=settings.enriquecedor_llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.openai_api_key,
            )

    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage

        from app.core.llm_guard import chamada_llm_mensagem_com_retry

        response = await chamada_llm_mensagem_com_retry(
            self.llm, [HumanMessage(content=prompt)], self.usuario_id
        )
        return response.content


def _build_prompt(markdown: str, titulo: str) -> str:
    truncated = markdown[:8000]
    return f"""Você é um analista de conteúdo SEO. Recebe título e markdown de uma
página e produz metadados estruturados.

REGRAS:
- tipo: um de [blog, produto, categoria, landing, tutorial].
- intencao: um de [informacional, comercial, transacional, navegacional].
- categoria: tema principal em 1-3 palavras (ex.: "Programação iniciante").
- palavras_chave: 7-15 termos centrais do texto. INCLUA OBRIGATORIAMENTE:
  * Substantivos do título (ex.: "loja virtual", "imobiliária", "restaurante").
  * Sinônimos técnicos e regionalismos mencionados no corpo (ex.: para "loja
    virtual" inclua "e-commerce", "dropshipping", "marketplace" SE aparecerem).
  * Termos do nicho que distinguem este artigo de artigos genéricos (ex.: para
    "abrir restaurante" inclua "alimentação", "cozinha", "delivery").
  * NÃO inclua palavras genéricas como "empresa", "negócio", "abrir", "como"
    — essas não diferenciam o conteúdo.
- entidades: nomes próprios, ferramentas, tecnologias, frameworks
  mencionados (até 10).
- resumo: 2-3 frases sobre o que a página oferece ao leitor, citando o nicho
  específico (não apenas "guia sobre empresa").

EXEMPLO de palavras_chave bem extraídas:

Título: "Como abrir uma loja virtual: guia completo"
Markdown menciona: "dropshipping", "marketplaces", "shopify", "CNPJ", "frete"

palavras_chave: ["loja virtual", "e-commerce", "dropshipping", "marketplace",
                  "shopify", "CNPJ", "frete", "vendas online"]

Note: "empresa", "negócio", "abrir" foram EXCLUÍDOS por serem genéricos.
"shopify" foi INCLUÍDO porque é termo técnico mencionado.

Saída APENAS em JSON:
{{
  "tipo": "blog",
  "categoria": "...",
  "intencao": "informacional",
  "palavras_chave": ["..."],
  "entidades": ["..."],
  "resumo": "..."
}}

Título: {titulo}

Markdown:
<<<
{truncated}
>>>"""


def _parse(response: str) -> dict[str, Any]:
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    return {}
