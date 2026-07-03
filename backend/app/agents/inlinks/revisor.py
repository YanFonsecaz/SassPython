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

    # Lint final de coesão: só revisa o que foi de fato APLICADO no texto.
    # O julgamento semântico (tema âncora↔destino) já foi feito pelo juiz único
    # no inseridor — revisar semântica 2x produzia rejeições ruidosas.
    inlinks_revisaveis = [
        il for il in inlinks if il.get("status") == "aplicado"
    ]

    if not inlinks_revisaveis:
        return inlinks

    agente = _RevisorAgent(usuario_id)

    lista = ""
    for i, il in enumerate(inlinks_revisaveis):
        lista += (
            f"\n{i+1}. Âncora: {il['anchor_text']}\n"
            f"   Destino: {il.get('titulo_destino') or il['url_destino']}\n"
            f"   Parágrafo: {il['paragrafo_idx']}"
        )

    prompt = f"""Você é um revisor de texto. Os links abaixo já passaram por julgamento semântico —
NÃO reavalie tema ou relevância. Verifique APENAS defeitos objetivos de aplicação no texto.

REJEITE SOMENTE se:
- A frase ficou gramaticalmente quebrada ou sem sentido no ponto do link
- Há texto duplicado, truncado ou corrompido ao redor do link
- A mesma âncora exata foi usada em dois links diferentes

NÃO rejeite por:
- Tema, relevância ou "âncora genérica" — isso já foi julgado antes
- Score — não é critério aqui
- Âncoras que são trechos literais do texto original — essas são SEMPRE naturais

LINKS APLICADOS:
{lista}

TRECHO DO TEXTO MODIFICADO (parágrafos relevantes):
{_extrair_paragrafos_relevantes(pilar_modificado, inlinks_revisaveis, 6000)}

Revise cada link informando indice, status ("aplicado" ou "rejeitado_revisor") e motivo da rejeicao
(1 frase objetiva apontando o defeito de texto; vazio se aplicado)."""

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
        # Fail-open: juiz + validações determinísticas já garantiram o link;
        # o lint é cosmético — indisponível, mantém os aplicados.
        logger.warning("Revisor LLM indisponível; mantendo inlinks aplicados sem lint: %s", e)

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
