import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)


class ChecagemRevisao(BaseModel):
    aderencia_outline: int = Field(ge=0, le=100, description="Nota 0-100")
    tom_voz: int = Field(ge=0, le=100, description="Nota 0-100")
    palavras_chave: int = Field(ge=0, le=100, description="Nota 0-100")
    coerencia_textual: int = Field(ge=0, le=100, description="Nota 0-100")
    seo_on_page: int = Field(ge=0, le=100, description="Nota 0-100")
    palavras_proibidas: int = Field(ge=0, le=100, description="Nota 0-100")
    contagem_palavras: int = Field(ge=0, le=100, description="Nota 0-100")


class RevisaoArtigoSchema(BaseModel):
    aprovado: bool = Field(description="True se score >= 70")
    score_qualidade: int = Field(ge=0, le=100, description="Score geral 0-100")
    problemas: list[str] = Field(default_factory=list, description="Lista de problemas encontrados")
    sugestoes: list[str] = Field(default_factory=list, description="Lista de sugestoes de melhoria")
    feedback_para_redator: str = Field(default="", description="Feedback construtivo detalhado")
    checagens: ChecagemRevisao | None = Field(default=None, description="Notas por checagem")


class RevisorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(
            usuario_id,
            temperature=settings.artigo_revisor_temperature,
            model=settings.artigo_revisor_model,
        )

    async def executar(self, estado: dict[str, Any], session) -> dict[str, Any]:
        artigo = estado.get("artigo", {})
        brief = estado.get("brief", {})
        persona = estado.get("persona_selecionada", {})
        config_json = estado.get("cliente_config", {})

        tom_voz = persona.get("tom_voz", config_json.get("persona_global", {}).get("tom_voz", "profissional"))
        nivel_tecnico = persona.get("nivel_tecnico", config_json.get("persona_global", {}).get("nivel_tecnico", "intermediario"))
        palavras_proibidas = persona.get("palavras_proibidas", [])
        meta_palavras = estado.get("meta_palavras", 2000)

        prompt = f"""Voce e um revisor rigoroso de conteudo SEO. Analise o artigo com base no brief e na persona.

Checagens (cada uma vale uma nota 0-100):
1. aderencia_outline: Todas as secoes do outline foram cobertas? (peso 20%)
2. tom_voz: O conteudo segue o tom de voz "{tom_voz}"? (peso 20%)
3. palavras_chave: Palavras-chave foram distribuidas corretamente? (peso 15%)
4. coerencia_textual: O texto e coerente e fluido? (peso 15%)
5. seo_on_page: H1, H2/H3, meta description estao corretos? (peso 15%)
6. palavras_proibidas: Nenhuma destas palavras foi usada? {palavras_proibidas} (peso 10%)
7. contagem_palavras: Dentro da meta de {meta_palavras} palavras (+/- 10%)? (peso 5%)

Regras:
- Score >= 70: aprovado
- Score < 70: reprovado, forneça feedback construtivo para o redator

ARTIGO:
{json.dumps(artigo, ensure_ascii=False)[:3000]}

BRIEF:
{json.dumps(brief, ensure_ascii=False)[:1500]}

Nivel tecnico: {nivel_tecnico}

Preencha: aprovado, score_qualidade, problemas, sugestoes, feedback_para_redator, checagens."""

        try:
            resultado: RevisaoArtigoSchema = await self.invoke_structured(prompt, RevisaoArtigoSchema)
            revisao_dict = resultado.model_dump()
        except Exception:
            logger.warning("Structured output falhou para revisao, usando JsonOutputParser fallback")
            from langchain_core.output_parsers import JsonOutputParser

            chain = self.llm | JsonOutputParser()
            raw = await self.invoke_raw(prompt)
            revisao_dict = chain.invoke(raw.content)

        aprovado = revisao_dict.get("aprovado", False)
        score = revisao_dict.get("score_qualidade", 0)

        versao = estado.get("versao_atual", 0)
        from app.services import ferramenta_service

        await ferramenta_service.atualizar_versao_revisao(
            session,
            execucao_id=estado["execucao_id"],
            versao=versao,
            score_revisao=score,
            feedback_recebido=revisao_dict.get("feedback_para_redator", ""),
        )

        return {
            "revisao": revisao_dict,
            "aprovado_revisor": aprovado,
        }
