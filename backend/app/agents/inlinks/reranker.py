import logging
from typing import Any

from langsmith import traceable
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class RankingItemSchema(BaseModel):
    indice: int = Field(description="Indice do candidato na lista (1-based)")
    score_contexto: float = Field(ge=0, le=10, description="Score de relevancia contextual (0-10)")
    motivo: str = Field(default="", description="Breve justificativa do score")


class RankingsSchema(BaseModel):
    rankings: list[RankingItemSchema] = Field(description="Lista de rankings")


@traceable(name="reranker", tags=["inlinks"])
async def rerank_candidatos(
    pilar_titulo: str,
    pilar_resumo: str,
    pilar_metadados: dict[str, Any],
    candidatos: list[dict[str, Any]],
    usuario_id: str,
) -> list[dict[str, Any]]:
    if not candidatos:
        return []

    agente = _RerankerAgent(usuario_id)

    lista_candidatos = ""
    for i, c in enumerate(candidatos):
        pk = ", ".join(c.get("palavras_chave", [])) if isinstance(c.get("palavras_chave"), list) else str(c.get("palavras_chave", ""))
        lista_candidatos += (
            f"\n{i+1}. URL: {c['url']}\n"
            f"   Titulo: {c.get('titulo', '')}\n"
            f"   Categoria: {c.get('categoria', '')}\n"
            f"   Palavras-chave: {pk}\n"
            f"   Resumo: {c.get('resumo', '')[:300]}\n"
            f"   Score semantico: {c.get('score_semantico', 0):.3f}"
        )

    pilar_pk = ", ".join(pilar_metadados.get("palavras_chave", [])) if isinstance(pilar_metadados.get("palavras_chave"), list) else str(pilar_metadados.get("palavras_chave", ""))
    pilar_resumo_meta = pilar_metadados.get("resumo", "")[:500]

    prompt = f"""Você é um especialista em SEO e linkagem interna.
Para o artigo pilar abaixo, classifique cada URL candidata de 0 a 10 quanto à relevância contextual para linkagem interna.

TEMA DO PILAR:
- Título: {pilar_titulo}
- Categoria: {pilar_metadados.get("categoria", "")}
- Palavras-chave: {pilar_pk}
- Resumo: {pilar_resumo_meta}
- Conteúdo (trecho): {pilar_resumo[:1000]}

CANDIDATAS (cada uma é uma URL que pode receber link a partir do pilar):
{lista_candidatos}

Classifique cada candidato com indice, score_contexto (0-10) e motivo.
Considere: relevância temática, complementariedade, intenção de busca, diversidade."""

    try:
        resultado: RankingsSchema = await agente.invoke_structured(prompt, RankingsSchema)
        for c in candidatos:
            idx = candidatos.index(c) + 1
            match = next((r for r in resultado.rankings if r.indice == idx), None)
            if match:
                c["score_contexto"] = float(match.score_contexto) / 10.0
                c["motivo_contexto"] = match.motivo
            else:
                c["score_contexto"] = 0.5
                c["motivo_contexto"] = ""
    except Exception as e:
        logger.warning("Reranker LLM falhou, usando so semantico: %s", e)
        for c in candidatos:
            c["score_contexto"] = 0.5
            c["motivo_contexto"] = ""

    for c in candidatos:
        c["score_total"] = float(
            0.5 * float(c.get("score_semantico", 0))
            + 0.5 * float(c.get("score_contexto", 0))
        )

    candidatos.sort(key=lambda x: x.get("score_total", 0), reverse=True)
    return candidatos


class _RerankerAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings

        model = settings.reranker_llm_model if settings.llm_provider == "openai" else None
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.inlinks_reranker_temperature,
        )
