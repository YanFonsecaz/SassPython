import json
import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


_MAX_PILAR_CHARS = 30000


async def gerar_ancoras(
    pilar_texto: str,
    candidatos: list[dict[str, Any]],
    usuario_id: str,
) -> list[dict[str, Any]]:
    if not candidatos:
        return []

    agente = _AncoradorAgent(usuario_id)

    trecho_pilar = pilar_texto[:_MAX_PILAR_CHARS]

    lista = ""
    for i, c in enumerate(candidatos):
        lista += f"\n{i+1}. URL: {c['url']}\n   Titulo: {c.get('titulo', '')}\n   Resumo: {c.get('resumo', '')[:200]}"

    prompt = f"""Você é um especialista em SEO e linkagem interna.

Para cada URL candidata abaixo, escolha 5-7 frases do artigo pilar que sirvam de **âncora teaser** para o destino — ou seja, frases que, lidas isoladamente, façam o leitor querer clicar para saber mais sobre o **destino**.

ARTIGO PILAR:
{trecho_pilar}

CANDIDATAS:
{lista}

Responda APENAS com JSON:
{{"ancoras": [{{"indice": 1, "opcoes": ["trecho exato do pilar 1", "trecho exato do pilar 2"]}}, ...]}}

REGRAS DE QUALIDADE (em ordem de prioridade):
1. **Foco no destino:** a âncora deve evocar o tema do destino (use o título e o resumo da URL candidata como guia). Pergunte-se: "Se eu lesse só esta âncora, eu esperaria chegar nessa URL?"
2. **Literal do pilar:** as âncoras DEVEM ser trechos copiados EXATAMENTE do artigo pilar — preservando acentuação, capitalização e pontuação interna. Não invente, não parafraseie.
3. **Especificidade > generalidade:** prefira frases com substantivos concretos do tema do destino ("portfólio de projetos", "linguagem para iniciantes") em vez de termos abertos do pilar ("começar a aprender", "expandir conhecimento").
4. **Tamanho:** cada âncora deve ter 2-5 palavras.
5. **Cobertura do artigo:** procure âncoras ao longo de TODO o pilar (introdução, meio, conclusão), não apenas no início.
6. **Variedade:** dê 5-7 opções por candidato — combinações diferentes de termos para o injector escolher a melhor disponível.
7. **Não-cabeçalhos:** NÃO escolha trechos dentro de cabeçalhos (linhas iniciadas por `#`, `##`, etc.). Esses trechos serão descartados pelo injector.
8. **Sem genéricos:** evite "clique aqui", "saiba mais", "veja também".
9. **Vazio é aceitável:** se nenhuma frase do pilar evocar o destino com qualidade, retorne `"opcoes": []` para esse candidato — melhor descartar do que linkar mal."""

    try:
        resultado = await agente._invoke_llm(prompt)
        ancoras_map = _parse_ancoras(resultado)

        for c in candidatos:
            idx = candidatos.index(c) + 1
            if idx in ancoras_map:
                c["ancoras_opcoes"] = ancoras_map[idx]
            else:
                c["ancoras_opcoes"] = [c.get("titulo", "saiba mais")]
    except Exception as e:
        logger.warning("Ancorador LLM falhou: %s", e)
        for c in candidatos:
            c["ancoras_opcoes"] = [c.get("titulo", "saiba mais")]

    return candidatos


class _AncoradorAgent(BaseAgent):
    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage

        from app.core.llm_guard import chamada_llm_mensagem_com_retry

        response = await chamada_llm_mensagem_com_retry(
            self.llm, [HumanMessage(content=prompt)], self.usuario_id
        )
        return response.content


def _parse_ancoras(response: str) -> dict[int, list[str]]:
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            result = {}
            for item in data.get("ancoras", []):
                idx = item.get("indice", 0)
                opcoes = item.get("opcoes", [])
                if idx and opcoes:
                    result[idx] = opcoes
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return {}
