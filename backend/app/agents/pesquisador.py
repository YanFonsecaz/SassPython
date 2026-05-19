import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.agents.base import BaseAgent
from app.config import settings
from app.models.pesquisa_cache import PesquisaCache

logger = logging.getLogger(__name__)


class PesquisadorAgent(BaseAgent):
    async def executar(self, estado: dict[str, Any], session) -> dict[str, Any]:
        topico = estado["topico"]
        kw_principal = estado["palavra_chave_principal"]
        usuario_id = estado["usuario_id"]

        serpapi_task = self._fetch_pesquisa(session, usuario_id, topico, "serpapi", self._buscar_serpapi)
        trends_task = self._fetch_pesquisa(session, usuario_id, f"{topico} {kw_principal}", "google_trends", self._buscar_google_trends)
        vetorial_task = self._buscar_conteudos_vetoriais(topico, usuario_id, session)

        (resultados_web, web_fallback, serpapi_cache), (tendencias, trends_fallback, trends_cache), (conteudos_vetoriais, _) = await asyncio.gather(
            serpapi_task, trends_task, vetorial_task
        )

        for cache_entry in (serpapi_cache, trends_cache):
            if cache_entry is not None:
                session.add(cache_entry)
        if serpapi_cache is not None or trends_cache is not None:
            await session.flush()

        query_para_resumo = f"Topico: {topico}\nPalavra-chave: {kw_principal}\nResultados web: {json.dumps(resultados_web[:5], ensure_ascii=False)[:1000]}\nTendencias: {json.dumps(tendencias[:5], ensure_ascii=False)[:500]}\nConteudos similares: {json.dumps(conteudos_vetoriais[:3], ensure_ascii=False)[:1000]}"

        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Voce e um pesquisador de conteudo SEO. Resuma os achados de pesquisa em insights acionaveis para criacao de conteudo. Foque em: tendencias, gaps de conteudo, oportunidades de SEO. Responda em portugues."),
            ("human", "{query}"),
        ])
        chain = prompt | self.llm
        resultado = await self.invoke(chain, {"query": query_para_resumo})
        insights = resultado.get("output", "")

        return {
            "pesquisa_resultados": {
                "resultados_web": resultados_web[:10],
                "tendencias": tendencias[:10],
                "conteudos_vetoriais": conteudos_vetoriais[:5],
                "web_fallback": web_fallback,
                "trends_fallback": trends_fallback,
                "insights": insights,
            }
        }

    async def _fetch_pesquisa(self, session, usuario_id: str, query: str, fonte: str, buscar_fn):
        query_norm = query.lower().strip()
        query_hash = hashlib.sha256(query_norm.encode()).hexdigest()

        stmt = select(PesquisaCache).where(
            PesquisaCache.usuario_id == usuario_id,
            PesquisaCache.query_hash == query_hash,
            PesquisaCache.fonte == fonte,
            PesquisaCache.expira_em > datetime.now(UTC),
        )
        resultado = await session.execute(stmt)
        cache = resultado.scalar_one_or_none()
        if cache:
            return cache.resultados_json.get("dados", []), False, None

        dados = await buscar_fn(query)

        cache_entry = PesquisaCache(
            usuario_id=usuario_id,
            query_hash=query_hash,
            query_original=query,
            resultados_json={"dados": dados},
            fonte=fonte,
            expira_em=datetime.now(UTC) + timedelta(days=settings.pesquisa_cache_ttl_days),
        )
        return dados, False, cache_entry

    async def _buscar_serpapi(self, query: str) -> list[dict[str, Any]]:
        if not settings.serpapi_key:
            return []
        from serpapi import GoogleSearch

        search = GoogleSearch({
            "q": query,
            "api_key": settings.serpapi_key,
            "num": 10,
            "hl": "pt-br",
            "gl": "br",
        })
        results = search.get_dict()
        organic = results.get("organic_results", [])
        return [
            {"titulo": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
            for r in organic
        ]

    async def _buscar_google_trends(self, query: str) -> list[dict[str, Any]]:
        if not settings.google_trends_enabled:
            return []
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="pt-BR", tz=-3, timeout=(10, 25))
        pytrends.build_payload(kw_list=[query[:50]], timeframe="today 3-m", geo="BR")
        interest = pytrends.interest_over_time()
        if interest.empty:
            return []
        related = pytrends.related_queries()
        related_data = related.get(query[:50], {}).get("rising", [])
        return [
            {"termo": row.get("query", ""), "valor": int(row.get("value", 0))}
            for _, row in related_data.head(10).iterrows()
        ] if related_data is not None and not related_data.empty else []

    async def _buscar_conteudos_vetoriais(self, texto: str, usuario_id: str, session) -> tuple[list[dict[str, Any]], bool]:
        from app.core.graceful_degradation import buscar_conteudo_vetorial_com_keyword_fallback

        return await buscar_conteudo_vetorial_com_keyword_fallback(texto, usuario_id, session)
