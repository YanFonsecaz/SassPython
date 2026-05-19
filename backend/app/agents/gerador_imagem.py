import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

IMAGEM_PROMPT_SYSTEM = """Voce e um especialista em criacao de prompts para geracao de imagens por IA. Crie um prompt descritivo para gerar uma imagem profissional para blog.

Regras:
1. NUNCA inclua texto legivel na imagem
2. Estilo visual adequado para blog profissional
3. Cores suaves e profissionais
4. Resolucao: 1792x1024 (landscape)
5. O prompt deve ser em ingles
6. Inclua um alt_text descritivo em portugues

Responda em formato JSON: {{"prompt": "...", "alt_text": "..."}}"""


class GeradorImagemAgent(BaseAgent):
    async def executar(self, estado: dict[str, Any], session) -> dict[str, Any]:
        artigo = estado.get("artigo", {})
        titulo = estado.get("artigo_titulo", "")
        tipo_conteudo = estado.get("tipo_conteudo", "blog")

        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", IMAGEM_PROMPT_SYSTEM),
            ("human", "Crie prompt para imagem sobre: {titulo}\nTipo: {tipo}\nConteudo resumido: {resumo}"),
        ])
        chain = prompt | self.llm | JsonOutputParser()
        resultado = await self.invoke(chain, {
            "titulo": titulo,
            "tipo": tipo_conteudo,
            "resumo": str(artigo.get("conteudo_markdown", ""))[:1000],
        })

        prompt_imagem = resultado.get("prompt", "")
        alt_text = resultado.get("alt_text", "")

        imagem_url = None
        try:
            from app.core.graceful_degradation import gerar_imagem_com_fallback

            imagem_url, _ = await gerar_imagem_com_fallback(prompt_imagem, self.usuario_id)
            from app.agents.imagem_storage import persistir_imagem

            execucao_id = estado.get("execucao_id", "")
            if imagem_url and execucao_id:
                imagem_url = await persistir_imagem(imagem_url, execucao_id)
        except Exception as e:
            logger.warning("Falha ao gerar imagem: %s", e)

        return {
            "imagem_url": imagem_url,
            "imagem_prompt": prompt_imagem,
            "imagem_alt_text": alt_text,
        }
