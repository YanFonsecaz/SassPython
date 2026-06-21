import logging
from typing import Any, Literal

from langsmith import traceable
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class RevisaoItemSchema(BaseModel):
    indice: int = Field(description="Indice do inlink na lista (1-based)")
    status: Literal["aplicado", "rejeitado_revisor"] = Field(description="aplicado ou rejeitado_revisor")
    motivo: str = Field(default="", description="Motivo da rejeicao (vazio se aplicado)")


class RevisaoSchema(BaseModel):
    revisao: list[RevisaoItemSchema] = Field(description="Lista de revisoes")


def _extrair_paragrafos_relevantes(texto: str, inlinks: list[dict[str, Any]], max_chars: int = 6000) -> str:
    if not inlinks:
        return texto[:max_chars]
    paragrafos = texto.split("\n\n")
    indices = sorted(set(
        il.get("paragrafo_idx", 0) for il in inlinks
        if isinstance(il.get("paragrafo_idx"), int) and 0 <= il["paragrafo_idx"] < len(paragrafos)
    ))
    selecionados = []
    total_chars = 0
    for idx in indices:
        p = paragrafos[idx]
        if total_chars + len(p) > max_chars:
            break
        selecionados.append(f"[P{idx}] {p}")
        total_chars += len(p)
    return "\n\n".join(selecionados) if selecionados else texto[:max_chars]


@traceable(name="revisor_inlinks", tags=["inlinks"])
async def revisar_inlinks(
    pilar_original: str,
    pilar_modificado: str,
    inlinks: list[dict[str, Any]],
    usuario_id: str,
) -> list[dict[str, Any]]:
    if not inlinks:
        return inlinks

    inlinks_revisaveis = [
        il for il in inlinks if il.get("status") != "sugestao_manual"
    ]

    if not inlinks_revisaveis:
        return inlinks

    agente = _RevisorAgent(usuario_id)

    lista = ""
    for i, il in enumerate(inlinks_revisaveis):
        lista += (
            f"\n{i+1}. URL: {il['url_destino']}\n"
            f"   Âncora: {il['anchor_text']}\n"
            f"   Parágrafo: {il['paragrafo_idx']}\n"
            f"   Score: {il.get('score_total', 0):.2f}"
        )

    prompt = f"""Você é um revisor de SEO. Verifique se os inlinks abaixo foram aplicados corretamente no texto.

REGRAS DE REJEIÇÃO — rejeite SOMENTE se:
- A âncora foi inserida em contexto que quebra a gramática ou o sentido da frase
- A âncora é claramente desconectada do tema do parágrafo
- Há texto duplicado, truncado ou corrompido ao redor do link
- Distância entre inlinks é menor que 100 palavras
- A âncora não tem relação clara de tema com a página de destino

NÃO rejeite por:
- Score baixo — o score já foi usado para ranquear, não para filtrar aqui
- Âncoras que são trechos literais do texto original — essas são SEMPRE naturais
- Diferença de tema parcial — links de tema complementar agregam valor ao leitor

INLINKS APLICADOS:
{lista}

TRECHO DO TEXTO MODIFICADO (parágrafos relevantes):
{_extrair_paragrafos_relevantes(pilar_modificado, inlinks_revisaveis, 6000)}

EXEMPLO de rejeição correta:
- Âncora: "o código adequado" → Destino: "Contratação PJ: guia completo"
  Status: rejeitado_revisor
  Motivo: A âncora fala de código CNAE; o destino fala de contratação PJ. Temas tangenciais.

EXEMPLO de aprovação correta:
- Âncora: "escolher o CNAE certo" → Destino: "CNAE prestação de serviço: escolha o ideal"
  Status: aplicado
  Motivo: ""

Revise cada inlink informando indice, status ("aplicado" ou "rejeitado_revisor") e motivo da rejeicao."""

    try:
        resultado: RevisaoSchema = await agente.invoke_structured(prompt, RevisaoSchema)
        for i, il in enumerate(inlinks_revisaveis):
            idx = i + 1
            match = next((r for r in resultado.revisao if r.indice == idx), None)
            if match:
                il["status"] = match.status
                il["motivo_rejeicao"] = match.motivo or None
            else:
                il["status"] = "aplicado"
                il["motivo_rejeicao"] = None
    except Exception as e:
        logger.warning("Revisor LLM falhou; rebaixando inlinks para sugestao manual: %s", e)
        for il in inlinks_revisaveis:
            il["status"] = "sugestao_manual"
            il["motivo_rejeicao"] = "Revisão automática indisponível — confira manualmente."

    return inlinks


class _RevisorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings

        model = settings.revisor_llm_model if settings.llm_provider == "openai" else None
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.inlinks_revisor_temperature,
        )
