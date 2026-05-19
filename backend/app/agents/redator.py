import json
import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

REDATOR_SYSTEM_PROMPT = """Voce e um redator profissional de conteudo SEO Senior. Redija o artigo completo seguindo o brief fornecido.

Regras obrigatórias:
1. Siga o outline do brief rigorosamente
2. Respeite o tom de voz e nivel tecnico da persona
3. NUNCA use palavras proibidas
4. Inclua palavras recomendadas quando natural
5. SEO on-page: H1 unico, H2/H3 hierarquicos, meta description
6. Respeite a meta de palavras (+/- 10%)
7. Use markdown para formatacao
8. Responda em formato JSON com: titulo, conteudo_markdown, meta_description, palavras_chave_usadas, contagem_palavras, secoes_geradas"""


class RedatorAgent(BaseAgent):
    async def executar(self, estado: dict[str, Any], session) -> dict[str, Any]:
        brief = estado.get("brief", {})
        conteudos = estado.get("conteudos_selecionados", [])
        persona = estado.get("persona_selecionada", {})
        config_json = estado.get("cliente_config", {})
        feedback = estado.get("feedback_usuario", "")

        contexto = {
            "brief": json.dumps(brief, ensure_ascii=False),
            "conteudos_referencia": json.dumps(conteudos[:3], ensure_ascii=False)[:1500],
            "tom_voz": persona.get("tom_voz", config_json.get("persona_global", {}).get("tom_voz", "profissional")),
            "nivel_tecnico": persona.get("nivel_tecnico", config_json.get("persona_global", {}).get("nivel_tecnico", "intermediario")),
            "estilo_escrita": persona.get("estilo_escrita", config_json.get("persona_global", {}).get("estilo_escrita", "didatico")),
            "palavras_proibidas": persona.get("palavras_proibidas", []),
            "palavras_recomendadas": persona.get("palavras_recomendadas", []),
            "meta_palavras": estado.get("meta_palavras", 2000),
            "tipo_conteudo": estado.get("tipo_conteudo", "blog"),
            "feedback": feedback,
        }

        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", REDATOR_SYSTEM_PROMPT),
            ("human", "{contexto}"),
        ])
        chain = prompt | self.llm | JsonOutputParser()
        resultado = await self.invoke(chain, {"contexto": json.dumps(contexto, ensure_ascii=False)})

        conteudo_md = resultado.get("conteudo_markdown", "")
        contagem = len(conteudo_md.split())

        from app.services import ferramenta_service

        versao = estado.get("versao_atual", 0) + 1
        await ferramenta_service.salvar_versao(
            session,
            execucao_id=estado["execucao_id"],
            versao=versao,
            origem="feedback_humano" if feedback else "redator_inicial",
            titulo=resultado.get("titulo", ""),
            conteudo_markdown=conteudo_md,
            contagem_palavras=contagem,
        )

        return {
            "artigo": resultado,
            "artigo_titulo": resultado.get("titulo", ""),
            "versao_atual": versao,
        }
