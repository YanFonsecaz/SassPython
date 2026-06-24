import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)


class ChecagemRevisao(BaseModel):
    aderencia_outline: int = Field(ge=0, le=100, description="Nota 0-100")
    tom_voz: int = Field(ge=0, le=100, description="Nota 0-100 (tom, nivel tecnico e estilo)")
    aderencia_instrucoes: int = Field(ge=0, le=100, description="Nota 0-100 (instrucoes do cliente/persona, instrucoes do artigo e feedback do usuario)")
    palavras_chave: int = Field(ge=0, le=100, description="Nota 0-100")
    coerencia_textual: int = Field(ge=0, le=100, description="Nota 0-100")
    seo_on_page: int = Field(ge=0, le=100, description="Nota 0-100")
    palavras_proibidas: int = Field(ge=0, le=100, description="Nota 0-100")
    palavras_recomendadas: int = Field(ge=0, le=100, description="Nota 0-100")
    contagem_palavras: int = Field(ge=0, le=100, description="Nota 0-100")


class RevisaoArtigoSchema(BaseModel):
    aprovado: bool = Field(default=False, description="Ignorado: a aprovacao e derivada do score no codigo")
    score_qualidade: int = Field(ge=0, le=100, description="Media ponderada das checagens, 0-100")
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
        from app.agents.redator import _montar_instrucoes

        artigo = estado.get("artigo", {})
        brief = estado.get("brief", {})
        persona = estado.get("persona_selecionada", {})
        config_json = estado.get("cliente_config", {})
        persona_global = config_json.get("persona_global", {})

        tom_voz = persona.get("tom_voz", persona_global.get("tom_voz", "profissional"))
        nivel_tecnico = persona.get("nivel_tecnico", persona_global.get("nivel_tecnico", "intermediario"))
        estilo_escrita = persona.get("estilo_escrita", persona_global.get("estilo_escrita", "didatico"))
        palavras_proibidas = persona.get("palavras_proibidas", [])
        palavras_recomendadas = persona.get("palavras_recomendadas", [])
        instrucoes = _montar_instrucoes(persona, persona_global)
        instrucoes_adicionais = estado.get("instrucoes_adicionais", "")
        feedback_usuario = estado.get("feedback_usuario", "")
        meta_palavras = estado.get("meta_palavras", 2000)
        score_min = settings.artigo_revisor_score_min

        prompt = f"""Voce e um revisor rigoroso de conteudo SEO. Analise o artigo com base no brief, na persona e nas instrucoes. Responda em portugues (pt-BR).

Checagens (cada uma vale uma nota 0-100):
1. aderencia_outline: Todas as secoes do outline foram cobertas? (peso 15%)
2. tom_voz: Segue o tom "{tom_voz}", nivel tecnico "{nivel_tecnico}" e estilo "{estilo_escrita}"? (peso 15%)
3. aderencia_instrucoes: Atende as instrucoes do cliente/persona, as instrucoes do artigo e o feedback do usuario (quando houver)? (peso 15%)
4. palavras_chave: Palavras-chave foram distribuidas corretamente? (peso 10%)
5. coerencia_textual: O texto e coerente e fluido? (peso 15%)
6. seo_on_page: H1, H2/H3, meta description estao corretos? (peso 10%)
7. palavras_proibidas: Nenhuma destas palavras foi usada? {palavras_proibidas} (peso 10%)
8. palavras_recomendadas: Incluiu de forma natural quando cabivel? {palavras_recomendadas} (peso 5%)
9. contagem_palavras: Dentro da meta de {meta_palavras} palavras (+/- 10%)? (peso 5%)

Regras:
- score_qualidade = media ponderada das checagens (0-100).
- Sempre que qualquer checagem ficar abaixo de {score_min}, descreva o problema em `problemas` e de orientacao acionavel em `feedback_para_redator`.
- Se houver feedback do usuario, a checagem aderencia_instrucoes DEVE verificar se ele foi atendido; se nao foi, reprove essa checagem.

INSTRUCOES DO CLIENTE/PERSONA:
{instrucoes or "(nenhuma)"}

INSTRUCOES DESTE ARTIGO:
{instrucoes_adicionais or "(nenhuma)"}

FEEDBACK DO USUARIO (rodada de revisao, se houver):
{feedback_usuario or "(nenhum)"}

ARTIGO:
{json.dumps(artigo, ensure_ascii=False)[:3000]}

BRIEF:
{json.dumps(brief, ensure_ascii=False)[:1500]}

Preencha: score_qualidade, problemas, sugestoes, feedback_para_redator, checagens (o campo `aprovado` e ignorado, nos o derivamos do score)."""

        try:
            resultado: RevisaoArtigoSchema = await self.invoke_structured(prompt, RevisaoArtigoSchema)
            revisao_dict = resultado.model_dump()
        except Exception:
            logger.warning("Structured output falhou para revisao, usando JsonOutputParser fallback")
            from langchain_core.output_parsers import JsonOutputParser

            chain = self.llm | JsonOutputParser()
            raw = await self.invoke_raw(prompt)
            revisao_dict = chain.invoke(raw.content)

        score = revisao_dict.get("score_qualidade", 0)
        # Aprovacao derivada do score (deterministica), nao confiamos no campo
        # `aprovado` do LLM, que pode divergir do score e do threshold.
        aprovado = score >= score_min
        revisao_dict["aprovado"] = aprovado

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
