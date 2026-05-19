import logging
from typing import Any

logger = logging.getLogger(__name__)


async def pesquisar_web_com_fallback(topico: str, usuario_id: str) -> tuple[list[dict[str, Any]], bool]:
    try:
        from app.agents.pesquisador import PesquisadorAgent

        agente = PesquisadorAgent(usuario_id)
        resultados = await agente._buscar_serpapi(topico)
        return resultados, False
    except Exception as e:
        logger.warning("SerpAPI falhou para usuario %s, continuando sem resultados web: %s", usuario_id, e)
        return [], True


async def buscar_tendencias_com_fallback(topico: str, usuario_id: str) -> tuple[list[dict[str, Any]], bool]:
    try:
        from app.agents.pesquisador import PesquisadorAgent

        agente = PesquisadorAgent(usuario_id)
        tendencias = await agente._buscar_google_trends(topico)
        return tendencias, False
    except Exception as e:
        logger.warning("Google Trends falhou para usuario %s, continuando sem tendencias: %s", usuario_id, e)
        return [], True


async def gerar_embedding_com_fallback(texto: str, usuario_id: str) -> tuple[list[float] | None, bool]:
    try:
        from app.config import settings

        if settings.llm_provider == "openai":
            from langchain_openai import OpenAIEmbeddings

            embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                dimensions=settings.embedding_dimensions,
                api_key=settings.openai_api_key,
            )
        else:
            from langchain_community.embeddings import ZhipuAIEmbeddings

            emb_kwargs: dict[str, Any] = {
                "model": settings.embedding_model,
                "api_key": settings.zhipuai_api_key,
            }
            if settings.embedding_dimensions:
                emb_kwargs["dimensions"] = settings.embedding_dimensions
            embeddings = ZhipuAIEmbeddings(**emb_kwargs)
        resultado = await embeddings.aembed_query(texto)
        return resultado, False
    except Exception as e:
        logger.warning("Embeddings falhou para usuario %s, usando fallback keyword: %s", usuario_id, e)
        return None, True


async def gerar_imagem_com_fallback(prompt: str, usuario_id: str) -> tuple[str | None, bool]:
    modelos = [
        ("gpt-image-1-mini", "1024x1024"),
        ("gpt-image-1.5", "1024x1536"),
        ("gpt-image-1", "1536x1024"),
    ]
    for model, size in modelos:
        try:
            import httpx

            from app.config import settings

            resposta = await httpx.AsyncClient(timeout=120).post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": model, "prompt": prompt, "size": size, "n": 1},
            )
            resposta.raise_for_status()
            data = resposta.json()
            if data.get("data") and data["data"][0].get("url"):
                return data["data"][0]["url"], False
            if data.get("data") and data["data"][0].get("b64_json"):
                return f"data:image/png;base64,{data['data'][0]['b64_json']}", False
        except Exception as e:
            logger.warning("Modelo %s falhou: %s", model, e)
            continue
    logger.warning("Todos os modelos de imagem falharam para usuario %s", usuario_id)
    return None, True


async def buscar_conteudo_vetorial_com_keyword_fallback(
    texto: str, usuario_id: str, session
) -> tuple[list[dict[str, Any]], bool]:
    try:
        embedding, fallback = await gerar_embedding_com_fallback(texto, usuario_id)
        if fallback or embedding is None:
            raise RuntimeError("Embedding nao disponivel")
        return await _buscar_por_embedding(embedding, usuario_id, session), False
    except Exception as e:
        logger.warning("Busca vetorial falhou, usando keyword fallback para usuario %s: %s", usuario_id, e)
        return await _buscar_por_keyword(texto, usuario_id, session), True


async def _buscar_por_embedding(embedding: list[float], usuario_id: str, session) -> list[dict[str, Any]]:
    from sqlalchemy import select, text

    from app.models.conteudo_vetor import ConteudoVetor

    await session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    stmt = (
        select(ConteudoVetor)
        .filter(ConteudoVetor.usuario_id == usuario_id, ConteudoVetor.ativo.is_(True))
        .order_by(ConteudoVetor.embedding.cosine_distance(embedding))
        .limit(10)
    )
    resultado = await session.execute(stmt)
    conteudos = resultado.scalars().all()
    return [{"id": str(c.id), "titulo": c.titulo, "conteudo": c.conteudo[:500], "tipo": c.tipo} for c in conteudos]


async def _buscar_por_keyword(texto: str, usuario_id: str, session) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from app.models.conteudo_vetor import ConteudoVetor

    palavras = texto.lower().split()[:10]
    conditions = [ConteudoVetor.conteudo.ilike(f"%{p}%") for p in palavras if len(p) > 3]
    if not conditions:
        return []
    stmt = (
        select(ConteudoVetor)
        .filter(ConteudoVetor.usuario_id == usuario_id, ConteudoVetor.ativo.is_(True), *conditions)
        .limit(10)
    )
    resultado = await session.execute(stmt)
    conteudos = resultado.scalars().all()
    return [{"id": str(c.id), "titulo": c.titulo, "conteudo": c.conteudo[:500], "tipo": c.tipo} for c in conteudos]
