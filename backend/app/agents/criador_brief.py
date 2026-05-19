import json
import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

BRIEF_SYSTEM_PROMPT = """Voce e um especialista em SEO e criacao de conteudo Senior. Crie um brief completo para o redator com base nas informacoes fornecidas.

O brief deve conter:
1. titulo_sugerido: Titulo otimizado para SEO (H1)
2. meta_description: Meta description (max 160 caracteres)
3. outline: Lista de secoes com titulo e descricao do que deve ser coberto
4. palavras_chave_distribuidas: Mapa de onde cada palavra-chave deve aparecer
5. tom_voz: Descricao do tom a ser usado
6. estimativa_palavras: Quantas palavras por secao

Responda em formato JSON valido."""


class CriadorBriefAgent(BaseAgent):
    async def executar(self, estado: dict[str, Any], session) -> dict[str, Any]:
        pesquisa = estado.get("pesquisa_resultados", {})
        conteudos = estado.get("conteudos_selecionados", [])
        analise = estado.get("resumo_analise", "")
        persona = estado.get("persona_selecionada", {})
        config_json = estado.get("cliente_config", {})

        context = {
            "topico": estado["topico"],
            "palavra_chave_principal": estado["palavra_chave_principal"],
            "palavras_chave_secundarias": estado.get("palavras_chave_secundarias", []),
            "tipo_conteudo": estado.get("tipo_conteudo", "blog"),
            "meta_palavras": estado.get("meta_palavras", 2000),
            "objetivo": estado.get("objetivo", ""),
            "artigo_introdutorio": estado.get("artigo_introdutorio", ""),
            "perguntas_clientes": estado.get("perguntas_clientes", ""),
            "insights_pesquisa": pesquisa.get("insights", ""),
            "analise_conteudos": analise,
            "tom_voz": persona.get("tom_voz", config_json.get("persona_global", {}).get("tom_voz", "profissional")),
            "nivel_tecnico": persona.get("nivel_tecnico", config_json.get("persona_global", {}).get("nivel_tecnico", "intermediario")),
            "palavras_proibidas": persona.get("palavras_proibidas", []),
            "palavras_recomendadas": persona.get("palavras_recomendadas", []),
            "conteudos_referencia": json.dumps(conteudos[:3], ensure_ascii=False)[:1500],
        }

        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", BRIEF_SYSTEM_PROMPT),
            ("human", "Crie o brief para:\n{contexto}"),
        ])
        chain = prompt | self.llm | JsonOutputParser()
        resultado = await self.invoke(chain, {"contexto": json.dumps(context, ensure_ascii=False)})

        return {"brief": resultado}
