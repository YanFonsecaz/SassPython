import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ArtigoRedigidoSchema(BaseModel):
    titulo: str = Field(default="", description="Titulo (H1) do artigo")
    conteudo_markdown: str = Field(default="", description="Corpo do artigo em markdown")
    meta_description: str = Field(default="", description="Meta description SEO")
    palavras_chave_usadas: list[str] = Field(default_factory=list, description="Palavras-chave utilizadas")
    contagem_palavras: int = Field(default=0, description="Numero de palavras do artigo")
    secoes_geradas: int = Field(default=0, description="Numero de secoes (H2/H3) geradas")

REDATOR_SYSTEM_PROMPT = """Voce e um redator profissional de conteudo SEO Senior. Redija o artigo completo seguindo o brief fornecido.

Regras obrigatórias:
1. Siga o outline do brief rigorosamente
2. Respeite o tom de voz, nivel tecnico e estilo de escrita da persona
3. Siga as `instrucoes_cliente` (instrucoes gerais do cliente/persona e objetivo) com prioridade — elas refletem o que o cliente quer
4. Siga as `instrucoes_adicionais` — sao pedidos especificos para ESTE artigo e tem prioridade alta
5. Quando houver `exemplos_textos`, use-os como referencia de estilo/voz (NAO copie o conteudo, apenas imite o jeito de escrever)
6. NUNCA use palavras proibidas
7. Inclua palavras recomendadas quando natural
8. Se houver `feedback` do usuario, ele tem PRIORIDADE MAXIMA: incorpore TODAS as mudancas pedidas nesta nova versao
9. SEO on-page: H1 unico, H2/H3 hierarquicos, meta description
10. Respeite a meta de palavras (+/- 10%)
11. Use markdown para formatacao
12. Responda em formato JSON com: titulo, conteudo_markdown, meta_description, palavras_chave_usadas, contagem_palavras, secoes_geradas"""


def _montar_instrucoes(persona: dict[str, Any], persona_global: dict[str, Any]) -> str:
    """Junta as instrucoes que o cliente preencheu (global + persona + objetivo).

    Esses campos vinham sendo descartados: o usuario preenchia "Instrucoes gerais"
    e "Objetivo" na UI mas nada chegava ao redator/brief.
    """
    partes = [
        persona_global.get("instrucoes_gerais", ""),
        persona.get("instrucoes_gerais", ""),
    ]
    objetivo = persona.get("objetivo", "")
    if objetivo:
        partes.append(f"Objetivo desta persona: {objetivo}")
    return "\n".join(p.strip() for p in partes if p and p.strip())


class RedatorAgent(BaseAgent):
    async def executar(self, estado: dict[str, Any], session) -> dict[str, Any]:
        brief = estado.get("brief", {})
        conteudos = estado.get("conteudos_selecionados", [])
        persona = estado.get("persona_selecionada", {})
        config_json = estado.get("cliente_config", {})
        persona_global = config_json.get("persona_global", {})
        feedback = estado.get("feedback_usuario", "")

        contexto = {
            "brief": json.dumps(brief, ensure_ascii=False),
            "conteudos_referencia": json.dumps(conteudos[:3], ensure_ascii=False)[:1500],
            "tom_voz": persona.get("tom_voz", persona_global.get("tom_voz", "profissional")),
            "nivel_tecnico": persona.get("nivel_tecnico", persona_global.get("nivel_tecnico", "intermediario")),
            "estilo_escrita": persona.get("estilo_escrita", persona_global.get("estilo_escrita", "didatico")),
            "instrucoes_cliente": _montar_instrucoes(persona, persona_global),
            "instrucoes_adicionais": estado.get("instrucoes_adicionais", ""),
            "exemplos_textos": persona_global.get("exemplos_textos", [])[:3],
            "palavras_proibidas": persona.get("palavras_proibidas", []),
            "palavras_recomendadas": persona.get("palavras_recomendadas", []),
            "meta_palavras": estado.get("meta_palavras", 2000),
            "tipo_conteudo": estado.get("tipo_conteudo", "blog"),
            "feedback": feedback,
        }

        prompt = f"{REDATOR_SYSTEM_PROMPT}\n\nContexto (JSON):\n{json.dumps(contexto, ensure_ascii=False)}"

        try:
            estruturado: ArtigoRedigidoSchema = await self.invoke_structured(prompt, ArtigoRedigidoSchema)
            resultado = estruturado.model_dump()
        except Exception:
            # Fallback tolerante: o LLM as vezes embrulha o JSON em cerca ```json,
            # o que faz o JsonOutputParser estrito falhar (OUTPUT_PARSING_FAILURE).
            logger.warning("Structured output falhou para redacao, usando JsonOutputParser fallback")
            from langchain_core.output_parsers import JsonOutputParser

            raw = await self.invoke_raw(prompt)
            resultado = JsonOutputParser().invoke(raw.content)

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
        }
