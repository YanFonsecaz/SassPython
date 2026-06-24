import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class SecaoBrief(BaseModel):
    titulo: str = Field(default="", description="Titulo da secao (H2/H3)")
    descricao: str = Field(default="", description="O que a secao deve cobrir")
    estimativa_palavras: int = Field(default=0, description="Palavras estimadas para a secao")


class BriefSchema(BaseModel):
    titulo_sugerido: str = Field(default="", description="Titulo otimizado para SEO (H1)")
    meta_description: str = Field(default="", description="Meta description (max 160 caracteres)")
    outline: list[SecaoBrief] = Field(default_factory=list, description="Secoes do artigo")
    palavras_chave_distribuidas: list[str] = Field(
        default_factory=list,
        description="Onde cada palavra-chave deve aparecer (um item por palavra)",
    )
    tom_voz: str = Field(default="", description="Descricao do tom a ser usado")


BRIEF_SYSTEM_PROMPT = """Voce e um especialista em SEO e criacao de conteudo Senior. Crie um brief completo para o redator com base nas informacoes fornecidas.

O brief deve conter:
1. titulo_sugerido: Titulo otimizado para SEO (H1)
2. meta_description: Meta description (max 160 caracteres)
3. outline: lista de secoes, cada uma com titulo, descricao do que cobrir e estimativa_palavras
4. palavras_chave_distribuidas: lista indicando onde cada palavra-chave deve aparecer (um item por palavra)
5. tom_voz: descricao do tom a ser usado

Considere `instrucoes_cliente` (instrucoes gerais e objetivo do cliente/persona), `instrucoes_adicionais` (pedidos especificos para este artigo) e o `estilo_escrita` ao montar o outline — o brief precisa refletir o que o cliente pediu.

Responda em portugues (pt-BR), em formato JSON valido."""


class CriadorBriefAgent(BaseAgent):
    async def executar(self, estado: dict[str, Any], session) -> dict[str, Any]:
        pesquisa = estado.get("pesquisa_resultados", {})
        conteudos = estado.get("conteudos_selecionados", [])
        analise = estado.get("resumo_analise", "")
        persona = estado.get("persona_selecionada", {})
        config_json = estado.get("cliente_config", {})
        persona_global = config_json.get("persona_global", {})

        from app.agents.redator import _montar_instrucoes

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
            "tom_voz": persona.get("tom_voz", persona_global.get("tom_voz", "profissional")),
            "nivel_tecnico": persona.get("nivel_tecnico", persona_global.get("nivel_tecnico", "intermediario")),
            "estilo_escrita": persona.get("estilo_escrita", persona_global.get("estilo_escrita", "didatico")),
            "instrucoes_cliente": _montar_instrucoes(persona, persona_global),
            "instrucoes_adicionais": estado.get("instrucoes_adicionais", ""),
            "palavras_proibidas": persona.get("palavras_proibidas", []),
            "palavras_recomendadas": persona.get("palavras_recomendadas", []),
            "conteudos_referencia": json.dumps(conteudos[:3], ensure_ascii=False)[:1500],
        }

        prompt = f"{BRIEF_SYSTEM_PROMPT}\n\nContexto (JSON):\n{json.dumps(context, ensure_ascii=False)}"

        try:
            estruturado: BriefSchema = await self.invoke_structured(prompt, BriefSchema)
            resultado = estruturado.model_dump()
        except Exception:
            # Mesmo fallback tolerante do redator: se o structured output falhar
            # (ex.: LLM embrulha o JSON em cerca ```), cai no JsonOutputParser.
            logger.warning("Structured output falhou para brief, usando JsonOutputParser fallback")
            from langchain_core.output_parsers import JsonOutputParser

            raw = await self.invoke_raw(prompt)
            resultado = JsonOutputParser().invoke(raw.content)

        return {"brief": resultado}
