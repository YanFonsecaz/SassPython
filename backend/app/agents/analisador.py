import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AnalisadorAgent(BaseAgent):
    def _calcular_score(
        self,
        similaridade: float,
        relevancia_contextual: float,
        atualizacao: float,
        penalidade: float,
    ) -> float:
        return (
            similaridade * 0.35
            + relevancia_contextual * 0.30
            + atualizacao * 0.20
            + penalidade * 0.15
        )

    async def executar(self, estado: dict[str, Any], session) -> dict[str, Any]:
        pesquisa = estado.get("pesquisa_resultados", {})
        conteudos = pesquisa.get("conteudos_vetoriais", [])
        topico = estado["topico"]
        kw_principal = estado["palavra_chave_principal"]

        scored = []
        for c in conteudos:
            sim = c.get("score", 0.7)
            ctx_rel = self._avaliar_relevancia(c, topico, kw_principal)
            recency = self._avaliar_atualizacao(c)
            penalty = self._avaliar_repeticao(c, conteudos)
            score = self._calcular_score(sim, ctx_rel, recency, penalty)
            if score > 0.3:
                scored.append({**c, "score_final": round(score, 3)})

        scored.sort(key=lambda x: x["score_final"], reverse=True)
        selecionados = scored[:5]

        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "Voce e um analista de conteudo SEO. Analise os conteudos ja selecionados e produza "
             "um resumo estrategico para orientar a redacao.\n"
             "Regras:\n"
             "- Responda em portugues (pt-BR).\n"
             "- Saida em 3-6 bullets curtos, sem introducao.\n"
             "- Aponte: temas recorrentes a cobrir, gaps/angulos ausentes e oportunidades de "
             "diferenciacao. Baseie-se APENAS nos conteudos fornecidos; nao invente.\n"
             "- Maximo ~150 palavras."),
            ("human", "Topico: {topico}\nPalavra-chave: {kw}\nConteudos:\n{conteudos}"),
        ])
        chain = prompt | self.llm
        resultado = await self.invoke(chain, {
            "topico": topico,
            "kw": kw_principal,
            "conteudos": str(selecionados[:5])[:2000],
        })

        return {
            "conteudos_selecionados": selecionados,
            "resumo_analise": resultado.get("output", ""),
        }

    def _avaliar_relevancia(self, conteudo: dict[str, Any], topico: str, kw: str) -> float:
        texto = f"{conteudo.get('titulo', '')} {conteudo.get('conteudo', '')}".lower()
        score = 0.0
        if kw.lower() in texto:
            score += 0.5
        palavras_topico = topico.lower().split()
        matches = sum(1 for p in palavras_topico if p in texto and len(p) > 3)
        score += min(matches * 0.1, 0.5)
        return min(score, 1.0)

    def _avaliar_atualizacao(self, conteudo: dict[str, Any]) -> float:
        return conteudo.get("atualizacao_score", 0.5)

    def _avaliar_repeticao(self, conteudo: dict[str, Any], todos: list[dict[str, Any]]) -> float:
        titulo = conteudo.get("titulo", "").lower()
        similares = sum(1 for c in todos if titulo in c.get("titulo", "").lower() and c.get("id") != conteudo.get("id"))
        return max(-0.3, -similares * 0.1)
