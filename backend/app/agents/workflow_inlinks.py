import asyncio
import logging
from typing import Any, TypedDict

import numpy as np
from langgraph.graph import END, StateGraph

from app.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj

_MIN_SEMANTIC_SCORE = 0.40


def _log_prefix(eid: str) -> str:
    return f"[eid={eid[:8]}]"


def _calcular_max_inlinks_dinamico(pilar_md: str, teto_usuario: int) -> int:
    palavras = len(pilar_md.split())
    dinamico = max(2, min(12, round(palavras / 222)))
    return min(dinamico, teto_usuario)


async def _resolver_checkpointer(ctx: dict[str, Any] | None):
    """Prefere checkpointer do ctx (worker warmup); senao usa singleton."""
    from app.agents.checkpointer import get_checkpointer, get_checkpointer_from_ctx

    cp = get_checkpointer_from_ctx(ctx)
    if cp is not None:
        return cp
    return await get_checkpointer()


class EstadoInlinks(TypedDict):
    execucao_id: str
    usuario_id: str
    cliente_id: str | None

    pilar_url: str
    pilar_markdown: str
    candidatas_urls: list[str]
    threshold_score: float
    max_inlinks: int
    rel_attr: str

    pilar_resultado: dict[str, Any]
    candidatas_resultados: list[dict[str, Any]]
    n_candidatas_validas: int
    n_candidatas_falhas: int

    pilar_embedding: list[float] | None
    candidatas_embeddings: list[dict[str, Any]]
    pilar_metadados: dict[str, Any]

    candidatos_reranked: list[dict[str, Any]]

    pilar_modificado: str
    inlinks_aplicados: list[dict[str, Any]]
    inlinks_revisados: list[dict[str, Any]]

    resultado_final: dict[str, Any]


async def node_validar_e_normalizar(estado: EstadoInlinks) -> dict[str, Any]:
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "validar_urls", "Validando e normalizando URLs...")

    urls = estado.get("candidatas_urls", [])
    validas = []
    vistas = set()

    for url in urls:
        from app.core.scraper import _normalizar_url

        n = _normalizar_url(url)
        if n and n not in vistas:
            validas.append(n)
            vistas.add(n)

    await publish_event(eid, "node_complete", "validar_urls", f"{len(validas)} URLs validas de {len(urls)} recebidas")
    return {"candidatas_urls": validas}


async def node_extrair_pilar(estado: EstadoInlinks) -> dict[str, Any]:
    from app.agents.inlinks.extrator import extrair_pilar
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "extrair_pilar", "Extraindo conteudo do pilar...")

    resultado = await extrair_pilar(
        estado.get("pilar_url") or None,
        estado.get("pilar_markdown") or None,
    )

    if resultado.falhou:
        await publish_event(eid, "node_complete", "extrair_pilar", f"Falha ao extrair pilar: {resultado.erro}")
    else:
        await publish_event(eid, "node_complete", "extrair_pilar", f"Pilar extraido: {resultado.tokens} tokens")
    return {
        "pilar_resultado": {
            "url": resultado.url,
            "url_canonica": resultado.url_canonica,
            "conteudo_md": resultado.conteudo_md,
            "titulo": resultado.titulo,
            "tokens": resultado.tokens,
            "html_hash": resultado.html_hash,
            "falhou": resultado.falhou,
            "erro": resultado.erro,
        }
    }


async def node_falha_pilar(estado: EstadoInlinks) -> dict[str, Any]:
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    pilar = estado.get("pilar_resultado", {})
    erro = pilar.get("erro") or "Não foi possível extrair o conteúdo do pilar."
    await publish_event(eid, "node_complete", "falha_pilar", f"Pilar indisponível: {erro}")
    return {"resultado_final": {
        "_pilar_falhou": True,
        "erro": erro,
        "n_candidatas_validas": 0,
        "n_aplicadas": 0,
        "inlinks": [],
    }}


def _pilar_ok(estado: EstadoInlinks) -> str:
    pilar = estado.get("pilar_resultado", {})
    if pilar.get("falhou") or not (pilar.get("conteudo_md") or "").strip():
        return "falha_pilar"
    return "extrair_candidatos"


async def node_extrair_candidatos(estado: EstadoInlinks) -> dict[str, Any]:
    from app.agents.inlinks.extrator import extrair_candidatas
    from app.core.scraper import ScrapeResult
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    urls = estado.get("candidatas_urls", [])
    await publish_event(eid, "node_start", "extrair_candidatos", f"Extraindo {len(urls)} URLs candidatas...")

    async def _on_progress(feito: int, total: int, r: ScrapeResult) -> None:
        sufixo = "(cache)" if r.cache_hit else ("falhou" if r.falhou else "ok")
        await publish_event(
            eid,
            "node_progress",
            "extrair_candidatos",
            f"Extraindo URL {feito}/{total} {sufixo}",
        )

    lote = await extrair_candidatas(urls, on_progress=_on_progress)

    await publish_event(
        eid,
        "node_complete",
        "extrair_candidatos",
        f"Extraidas {lote.n_sucessos}/{len(urls)} candidatas ({lote.n_falhas} falhas)",
    )

    resultados = [
        {
            "url": r.url,
            "url_canonica": r.url_canonica,
            "conteudo_md": r.conteudo_md,
            "titulo": r.titulo,
            "tokens": r.tokens,
            "html_hash": r.html_hash,
            "falhou": r.falhou,
            "erro": r.erro,
        }
        for r in lote.resultados
    ]

    return {
        "candidatas_resultados": resultados,
        "n_candidatas_validas": lote.n_sucessos,
        "n_candidatas_falhas": lote.n_falhas,
    }


async def node_enriquecer(estado: EstadoInlinks) -> dict[str, Any]:
    from sqlalchemy import select as sel
    from sqlalchemy.exc import IntegrityError

    from app.agents.inlinks.cleaner import limpar_conteudo
    from app.agents.inlinks.enriquecedor_metadados import enriquecer_metadados
    from app.core.chunker import chunk_texto
    from app.core.embeddings import gerar_embeddings_batch
    from app.core.workflow_events import publish_event
    from app.models.conteudo_vetor import ConteudoVetor

    eid = estado["execucao_id"]
    uid = estado["usuario_id"]
    cliente_id_val = estado.get("cliente_id")
    await publish_event(eid, "node_start", "enriquecer", "Consultando banco vetorial...")

    pilar = estado.get("pilar_resultado", {})
    candidatas = estado.get("candidatas_resultados", [])

    todas_urls = []
    if pilar.get("conteudo_md"):
        todas_urls.append({
            "url": pilar.get("url", ""),
            "url_canonica": pilar.get("url_canonica", pilar.get("url", "")),
            "conteudo_md": pilar.get("conteudo_md", ""),
            "titulo": pilar.get("titulo", ""),
            "html_hash": pilar.get("html_hash"),
            "is_pilar": True,
        })
    for c in candidatas:
        if c.get("falhou") or not c.get("conteudo_md"):
            continue
        todas_urls.append({
            "url": c.get("url", ""),
            "url_canonica": c.get("url_canonica", c.get("url", "")),
            "conteudo_md": c.get("conteudo_md", ""),
            "titulo": c.get("titulo", ""),
            "html_hash": c.get("html_hash"),
            "is_pilar": False,
        })

    pilar_embedding = None
    pilar_metadados: dict[str, Any] = {}
    candidatas_embeddings = []
    pilar_chunk_embeddings: list[list[float]] = []

    async with async_session_factory() as session:
        n_reused = 0
        n_cold = 0

        for item in todas_urls:
            url_c = item["url_canonica"]
            html_hash = item.get("html_hash")
            titulo = item.get("titulo", "")

            existing_rows = []
            if html_hash:
                # A busca por html_hash + url_canonica + usuario_id basta;
                # vetores não são por-cliente nesta versão. Para multi-cliente real,
                # adicionar `ConteudoVetor.cliente_id == cliente_id_val` aqui.
                stmt = (
                    sel(ConteudoVetor)
                    .where(
                        ConteudoVetor.usuario_id == uid,
                        ConteudoVetor.url_canonica == url_c,
                        ConteudoVetor.html_hash == html_hash,
                        ConteudoVetor.ativo,
                    )
                    .order_by(ConteudoVetor.chunk_index)
                )
                result = await session.execute(stmt)
                existing_rows = result.scalars().all()

            if existing_rows:
                n_reused += 1
                meta_dict = {
                    "tipo": existing_rows[0].tipo,
                    "intencao": existing_rows[0].intencao,
                    "palavras_chave": existing_rows[0].palavras_chave or [],
                    "entidades": existing_rows[0].atividades or [],
                    "resumo": existing_rows[0].resumo or "",
                    "categoria": existing_rows[0].categoria or "",
                }

                for row in existing_rows:
                    row_emb = list(row.embedding) if row.embedding is not None else None
                    emb_dict = {
                        "url": item["url"],
                        "url_canonica": url_c,
                        "titulo": titulo,
                        "ordem": row.chunk_index or 0,
                        "embedding": row_emb,
                        **meta_dict,
                    }
                    if item["is_pilar"]:
                        if row_emb:
                            pilar_chunk_embeddings.append(row_emb)
                        if not pilar_metadados:
                            pilar_metadados = meta_dict
                    else:
                        candidatas_embeddings.append(emb_dict)
            else:
                n_cold += 1
                markdown_limpo = await limpar_conteudo(item["conteudo_md"], uid)

                meta = await enriquecer_metadados(markdown_limpo, titulo, uid)
                meta_dict = {
                    "tipo": meta.tipo,
                    "intencao": meta.intencao,
                    "palavras_chave": meta.palavras_chave,
                    "entidades": meta.entidades,
                    "resumo": meta.resumo,
                    "categoria": meta.categoria,
                }

                chunks = chunk_texto(markdown_limpo)

                async def _on_batch(batch_idx: int, total_batches: int, n_proc: int, total: int) -> None:
                    await publish_event(
                        eid,
                        "node_progress",
                        "enriquecer",
                        f"Embeddings batch {batch_idx}/{total_batches} ({n_proc}/{total} chunks)",
                    )

                embeddings = await gerar_embeddings_batch(
                    [ch.texto[:8000] for ch in chunks],
                    uid,
                    on_progress=_on_batch,
                )

                for ch, emb in zip(chunks, embeddings, strict=False):
                    if emb is None:
                        continue

                    vetor = ConteudoVetor(
                        usuario_id=uid,
                        cliente_id=cliente_id_val,
                        execucao_id=eid,
                        titulo=titulo,
                        conteudo=ch.texto,
                        tipo=meta.tipo,
                        intencao=meta.intencao,
                        palavras_chave=meta.palavras_chave,
                        atividades=meta.entidades,
                        embedding=emb,
                        url_canonica=url_c,
                        chunk_index=ch.ordem,
                        tipo_recurso="pilar" if item["is_pilar"] else "candidata",
                        html_hash=html_hash,
                        tokens=ch.tokens,
                        score_base=0.0,
                        ativo=True,
                        resumo=meta.resumo,
                        categoria=meta.categoria,
                    )
                    try:
                        async with session.begin_nested():
                            session.add(vetor)
                            await session.flush()
                    except IntegrityError:
                        stmt2 = (
                            sel(ConteudoVetor)
                            .where(
                                ConteudoVetor.usuario_id == uid,
                                ConteudoVetor.url_canonica == url_c,
                                ConteudoVetor.chunk_index == ch.ordem,
                                ConteudoVetor.ativo,
                            )
                            .order_by(ConteudoVetor.chunk_index)
                        )
                        result2 = await session.execute(stmt2)
                        existing = result2.scalars().first()
                        if existing:
                            emb = existing.embedding

                    emb_dict = {
                        "url": item["url"],
                        "url_canonica": url_c,
                        "titulo": titulo,
                        "ordem": ch.ordem,
                        "embedding": emb,
                        **meta_dict,
                    }
                    if item["is_pilar"]:
                        if emb:
                            pilar_chunk_embeddings.append(emb)
                        if not pilar_metadados:
                            pilar_metadados = meta_dict
                    else:
                        candidatas_embeddings.append(emb_dict)

                await session.commit()

    from app.core.embeddings import media_embeddings
    if pilar_chunk_embeddings:
        pilar_embedding = media_embeddings(pilar_chunk_embeddings)
        logger.info("%s enriquecer: pilar_embedding=%s (%d chunks consolidados via mean pooling)",
                    _log_prefix(eid),
                    "OK" if pilar_embedding else "NONE",
                    len(pilar_chunk_embeddings),
        )
    else:
        logger.info("%s enriquecer: pilar_embedding=NONE (nenhum chunk encontrado)", _log_prefix(eid))

    for emb_dict in candidatas_embeddings:
        e = emb_dict.get("embedding")
        if e is not None and not isinstance(e, list):
            emb_dict["embedding"] = list(e)

    n_emb = len(candidatas_embeddings)
    if n_cold == 0:
        msg = f"Reuso completo: {n_reused} URLs do banco vetorial"
    elif n_reused == 0:
        msg = f"Gerando embeddings + metadados (cold) para {n_cold} URLs"
    else:
        msg = f"Reuso de {n_reused} URLs do banco vetorial, {n_cold} URLs novas"

    logger.info("%s enriquecer: candidatas_embeddings=%d (%s)", _log_prefix(eid), n_emb, msg)
    await publish_event(eid, "node_complete", "enriquecer", f"{msg} — {n_emb} chunks")

    return _sanitize({
        "pilar_embedding": pilar_embedding,
        "candidatas_embeddings": candidatas_embeddings,
        "pilar_metadados": pilar_metadados,
    })


async def node_match_rerank(estado: EstadoInlinks) -> dict[str, Any]:
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "match_rerank", "Buscando e re-ranqueando candidatos...")

    pilar_embedding = estado.get("pilar_embedding")
    if pilar_embedding is None:
        logger.info("%s match_rerank: pilar_embedding is None!", _log_prefix(eid))
        await publish_event(eid, "node_complete", "match_rerank", "Sem embedding do pilar, pulando match")
        return {"candidatos_reranked": []}

    candidatas_emb = estado.get("candidatas_embeddings", [])
    logger.info("%s match_rerank: pilar_embedding len=%d candidatas_emb count=%d",
                _log_prefix(eid), len(pilar_embedding), len(candidatas_emb))

    from app.core.embeddings import cosine_seguro

    best_by_url: dict[str, dict[str, Any]] = {}
    for c in candidatas_emb:
        url = c.get("url", "")
        emb_c = c.get("embedding")
        if emb_c is None:
            continue

        cosine = cosine_seguro(pilar_embedding, emb_c)

        existing = best_by_url.get(url)
        if existing is None or cosine > existing["score_semantico"]:
            best_by_url[url] = {
                "url": url,
                "url_canonica": c.get("url_canonica", url),
                "titulo": c.get("titulo", ""),
                "resumo": c.get("resumo", ""),
                "categoria": c.get("categoria", ""),
                "palavras_chave": c.get("palavras_chave", []),
                "score_semantico": cosine,
            }

    scored = sorted(best_by_url.values(), key=lambda x: x["score_semantico"], reverse=True)
    scored = scored[:15]

    await publish_event(
        eid,
        "node_progress",
        "match_rerank",
        f"Top {len(scored)} por similaridade semantica, aplicando re-rank LLM...",
    )

    threshold = estado.get("threshold_score", 0.6)

    from app.agents.inlinks.reranker import rerank_candidatos

    pilar_resultado = estado.get("pilar_resultado", {})
    reranked = await rerank_candidatos(
        pilar_resultado.get("titulo", ""),
        pilar_resultado.get("conteudo_md", "")[:2000],
        estado.get("pilar_metadados", {}),
        scored,
        estado["usuario_id"],
    )

    filtered = [
        c for c in reranked
        if c.get("score_total", 0) >= threshold
        and c.get("score_semantico", 0) >= _MIN_SEMANTIC_SCORE
    ]

    if not filtered and reranked:
        fallback_threshold = threshold * 0.85
        filtered = [
            c for c in reranked
            if c.get("score_total", 0) >= fallback_threshold
            and c.get("score_semantico", 0) >= _MIN_SEMANTIC_SCORE
        ]
        logger.info(
            "%s match_rerank: filtro vazio com threshold %.2f, reaplicou com %.2f → %d resultados",
            _log_prefix(eid), threshold, fallback_threshold, len(filtered),
        )

    n_descartadas_piso = len(reranked) - len(filtered)
    await publish_event(
        eid,
        "node_complete",
        "match_rerank",
        f"Top {len(filtered)} candidatos acima de {threshold} (piso semântico {_MIN_SEMANTIC_SCORE}; {n_descartadas_piso} descartadas pelo piso)",
    )
    return _sanitize({"candidatos_reranked": filtered})


async def node_inserir(estado: EstadoInlinks) -> dict[str, Any]:
    from app.agents.inlinks.inseridor import inserir_inlinks
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "inserir", "Inserindo inlinks no texto...")

    pilar_md = estado.get("pilar_resultado", {}).get("conteudo_md", "")
    candidatos = estado.get("candidatos_reranked", [])
    teto_usuario = estado.get("max_inlinks", 8)
    max_inlinks = _calcular_max_inlinks_dinamico(pilar_md, teto_usuario)

    await publish_event(
        eid,
        "node_progress",
        "inserir",
        f"Densidade alvo: {max_inlinks} inlinks ({len(pilar_md.split())} palavras)",
    )

    pilar_modificado, inseridos = await inserir_inlinks(
        pilar_md, candidatos, estado["usuario_id"], max_inlinks=max_inlinks
    )

    inlinks_dicts = [
        {
            "url_destino": ij.url_destino,
            "anchor_text": ij.anchor_text,
            "paragrafo_idx": ij.paragrafo_idx,
            "offset_chars": ij.offset_chars,
            "score_total": float(ij.score_total),
            "score_semantico": float(ij.score_semantico),
            "score_contexto": float(ij.score_contexto),
            "status": ij.status,
            "trecho_contexto": ij.trecho_contexto,
            "titulo_destino": ij.titulo_destino,
            "motivo_contexto": ij.motivo_contexto,
            "categoria_match": ij.categoria_match,
            "motivo_sugestao": ij.motivo_sugestao,
            "motivo_rejeicao": ij.motivo_rejeicao,
            "trecho_original": ij.trecho_original,
            "conector_antes": ij.conector_antes,
            "conector_depois": ij.conector_depois,
        }
        for ij in inseridos
    ]

    await publish_event(eid, "node_complete", "inserir", f"{len(inseridos)} inlinks inseridos")
    return _sanitize({
        "pilar_modificado": pilar_modificado,
        "inlinks_aplicados": inlinks_dicts,
    })


async def node_revisar(estado: EstadoInlinks) -> dict[str, Any]:
    from app.agents.inlinks.injector import remover_links_rejeitados
    from app.agents.inlinks.revisor import revisar_inlinks
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "revisar", "Revisando inlinks aplicados...")

    inlinks = estado.get("inlinks_aplicados", [])
    pilar_original = estado.get("pilar_resultado", {}).get("conteudo_md", "")
    pilar_modificado = estado.get("pilar_modificado", "")

    revisados = await revisar_inlinks(pilar_original, pilar_modificado, inlinks, estado["usuario_id"])

    pilar_saneado = remover_links_rejeitados(pilar_modificado, revisados)

    n_aplicados = sum(1 for r in revisados if r.get("status") == "aplicado")
    n_rejeitados = len(revisados) - n_aplicados

    await publish_event(eid, "node_complete", "revisar", f"Revisao: {n_aplicados} aplicados, {n_rejeitados} rejeitados")
    return _sanitize({"inlinks_revisados": revisados, "pilar_modificado": pilar_saneado})


async def node_formatar(estado: EstadoInlinks) -> dict[str, Any]:
    from app.agents.inlinks.formatador import formatar_pilar
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "formatar", "Formatando texto final...")

    pilar_mod = estado.get("pilar_modificado", "")
    pilar_formatado = await formatar_pilar(pilar_mod, estado["usuario_id"])

    n_antes = len([p for p in pilar_mod.split("\n\n") if p.strip()])
    n_depois = len([p for p in pilar_formatado.split("\n\n") if p.strip()])
    await publish_event(
        eid, "node_complete", "formatar",
        f"Formatação aplicada: {n_antes} → {n_depois} parágrafos",
    )
    return _sanitize({"pilar_modificado": pilar_formatado})


async def node_persistir(estado: EstadoInlinks) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    from app.models.inlink_sugerido import InlinkSugerido
    from app.services import ferramenta_service

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "persistir", "Persistindo resultados...")

    inlinks = estado.get("inlinks_revisados", [])
    pilar_modificado = estado.get("pilar_modificado", "")
    pilar_original = estado.get("pilar_resultado", {}).get("conteudo_md", "")
    n_validas = estado.get("n_candidatas_validas", 0)

    n_aplicados = sum(1 for il in inlinks if il.get("status") == "aplicado")
    n_rejeitados = len(inlinks) - n_aplicados

    inlinks_para_resultado = []

    async with async_session_factory() as session:
        versao_n = 1
        from sqlalchemy import select as sel

        from app.models.versao_artigo import VersaoArtigo

        existing = await session.execute(
            sel(VersaoArtigo).where(VersaoArtigo.execucao_id == eid).order_by(VersaoArtigo.versao.desc())
        )
        ultima = existing.scalar_one_or_none()
        if ultima:
            versao_n = ultima.versao + 1

        await ferramenta_service.salvar_versao(
            session,
            execucao_id=eid,
            versao=versao_n,
            origem=f"inlinks_v{versao_n}",
            titulo=estado.get("pilar_resultado", {}).get("titulo", "Inlinks"),
            conteudo_markdown=pilar_modificado,
            contagem_palavras=len(pilar_modificado.split()),
        )

        url_origem = estado.get("pilar_resultado", {}).get("url_canonica", "")
        rel_attr = estado.get("rel_attr", "noopener")
        bulk_objs = []
        for il in inlinks:
            motivo_final = il.get("motivo_rejeicao") or (
                il.get("motivo_sugestao") if il.get("status") == "sugestao_manual" else None
            )
            bulk_objs.append(InlinkSugerido(
                execucao_id=eid,
                url_origem=url_origem,
                url_destino=il["url_destino"],
                anchor_text=il["anchor_text"],
                paragrafo_idx=il["paragrafo_idx"],
                offset_chars=il["offset_chars"],
                score_total=il["score_total"],
                score_semantico=il["score_semantico"],
                score_contexto=il["score_contexto"],
                status=il.get("status", "aplicado"),
                motivo_rejeicao=motivo_final,
                rel_attr=rel_attr,
                trecho_contexto=il.get("trecho_contexto"),
                titulo_destino=il.get("titulo_destino"),
                motivo_contexto=il.get("motivo_contexto"),
                categoria_match=il.get("categoria_match"),
                trecho_original=il.get("trecho_original"),
                conector_antes=il.get("conector_antes"),
                conector_depois=il.get("conector_depois"),
            ))

        if bulk_objs:
            session.add_all(bulk_objs)
            await session.flush()

        for il, obj in zip(inlinks, bulk_objs, strict=True):
            inlinks_para_resultado.append({
                **il,
                "id": str(obj.id),
            })

        await session.commit()

    top_scores = sorted([float(il.get("score_total", 0)) for il in inlinks], reverse=True)

    resultado_final = {
        "n_candidatas_validas": n_validas,
        "n_aplicadas": n_aplicados,
        "n_rejeitadas": n_rejeitados,
        "top_scores": top_scores,
        "artigo_titulo": estado.get("pilar_resultado", {}).get("titulo", ""),
        "artigo": pilar_modificado,
        "conteudo_markdown": pilar_modificado,
        "pilar_original": pilar_original,
        "imagem_url": None,
        "inlinks": inlinks_para_resultado,
    }

    await publish_event(eid, "node_complete", "persistir", "Resultados persistidos")
    return _sanitize({"resultado_final": resultado_final})


def criar_workflow_inlinks(checkpointer=None):
    workflow = StateGraph(EstadoInlinks)

    workflow.add_node("validar_urls", node_validar_e_normalizar)
    workflow.add_node("extrair_pilar", node_extrair_pilar)
    workflow.add_node("falha_pilar", node_falha_pilar)
    workflow.add_node("extrair_candidatos", node_extrair_candidatos)
    workflow.add_node("enriquecer", node_enriquecer)
    workflow.add_node("match_rerank", node_match_rerank)
    workflow.add_node("inserir", node_inserir)
    workflow.add_node("revisar", node_revisar)
    workflow.add_node("formatar", node_formatar)
    workflow.add_node("persistir", node_persistir)

    workflow.set_entry_point("validar_urls")
    workflow.add_edge("validar_urls", "extrair_pilar")
    workflow.add_conditional_edges(
        "extrair_pilar", _pilar_ok,
        {"falha_pilar": "falha_pilar", "extrair_candidatos": "extrair_candidatos"},
    )
    workflow.add_edge("falha_pilar", END)
    workflow.add_edge("extrair_candidatos", "enriquecer")
    workflow.add_edge("enriquecer", "match_rerank")
    workflow.add_edge("match_rerank", "inserir")
    workflow.add_edge("inserir", "revisar")
    workflow.add_edge("revisar", "formatar")
    workflow.add_edge("formatar", "persistir")
    workflow.add_edge("persistir", END)

    return workflow.compile(checkpointer=checkpointer)


async def executar_workflow_inlinks(execucao_id: str, ctx: dict[str, Any] | None = None) -> None:
    from app.services import ferramenta_service

    try:
        async with async_session_factory() as session:
            await ferramenta_service.atualizar_execucao(session, execucao_id, status="executando")
            await session.commit()

            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if not execucao:
                return

            entrada = execucao.entrada_json

        estado_inicial: EstadoInlinks = {
            "execucao_id": execucao_id,
            "usuario_id": str(execucao.usuario_id),
            "cliente_id": str(execucao.cliente_id) if execucao.cliente_id else None,
            "pilar_url": entrada.get("pilar_url", ""),
            "pilar_markdown": entrada.get("pilar_markdown", ""),
            "candidatas_urls": entrada.get("candidatas_urls", []),
            "threshold_score": entrada.get("threshold_score", 0.6),
            "max_inlinks": entrada.get("max_inlinks", 8),
            "rel_attr": entrada.get("rel_attr", "noopener"),
        }

        checkpointer = await _resolver_checkpointer(ctx)
        workflow = criar_workflow_inlinks(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": f"inlinks_{execucao_id}"}}
        await asyncio.wait_for(
            _run_workflow_inlinks(workflow, estado_inicial, config, execucao_id),
            timeout=settings.workflow_timeout_segundos,
        )

    except asyncio.CancelledError:
        logger.info("%s Workflow inlinks cancelado", _log_prefix(execucao_id))
        async with async_session_factory() as session:
            from app.services import credito_service

            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if execucao and execucao.status == "executando":
                reserva = ferramenta_service._obter_reserva_estimada("inlinks_automaticos", execucao)
                if reserva > 0:
                    await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
                await ferramenta_service.atualizar_execucao(
                    session, execucao_id, status="cancelada", creditos_cobrados=0,
                )
                await session.commit()
        raise

    except TimeoutError:
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Workflow excedeu o tempo limite", ferramenta="inlinks")
            await session.commit()
    except Exception as e:
        logger.error("%s Workflow inlinks falhou para execucao %s: %s", _log_prefix(execucao_id), execucao_id, e)
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Erro interno do workflow", ferramenta="inlinks")
            await session.commit()


async def _run_workflow_inlinks(workflow, estado_inicial, config, execucao_id: str) -> None:
    from app.services import ferramenta_service

    async for _event in workflow.astream(estado_inicial, config=config, version="v2"):
        pass

    snapshot = await workflow.aget_state(config)
    estado_final = snapshot.values if snapshot else None

    async with async_session_factory() as session:
        execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
        if execucao and execucao.status == "executando":
            resultado = _extrair_resultado_inlinks(estado_final)
            await _finalizar_sucesso_inlinks(session, execucao_id, resultado)
            await session.commit()


async def _finalizar_sucesso_inlinks(db, execucao_id: str, resultado_json: dict[str, Any]) -> None:
    from datetime import UTC, datetime

    from app.services import credito_service, ferramenta_service

    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(f"Execucao {execucao_id} nao encontrada")

    reserva = ferramenta_service._obter_reserva_estimada("inlinks_automaticos", execucao)

    if resultado_json.get("_pilar_falhou"):
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)
        execucao.status = "falhou"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = (
            "Não foi possível extrair o conteúdo do pilar (URL inacessível, "
            "bloqueio por robots.txt, ou conteúdo vazio). Verifique a URL/markdown do pilar."
        )
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        logger.info("%s inlinks status=falhou (pilar nao extraido), reserva liberada", _log_prefix(execucao_id))
        return

    n_processadas = resultado_json.get("n_candidatas_validas", 0)

    if n_processadas == 0:
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)
        execucao.status = "concluida"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = (
            "Nenhuma URL candidata pode ser processada. "
            "Possiveis causas: dominio inexistente (DNS), robots.txt bloqueando, "
            "ou IP privado. Verifique as URLs informadas."
        )
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        logger.info("%s inlinks status=concluida sem creditos (0 candidatas validas)", _log_prefix(execucao_id))
        return

    custo = ferramenta_service.calcular_custo_inlinks(n_processadas)

    n_aplicados = resultado_json.get("n_aplicadas", 0)
    if n_aplicados == 0:
        custo = max(0, custo - ferramenta_service.CUSTO_BASE_INLINKS)
        execucao.erro_msg = (
            "Nenhum link orgânico cabe neste pilar — os destinos avaliados não "
            "compartilham termos específicos com o texto. Reveja as sugestões "
            "manuais ou reescreva o pilar para citar nichos com mais detalhes."
        )
        logger.info(
            "%s inlinks: 0 aplicados de %d validas, cobrando so URLs (custo=%d, sem base)",
            _log_prefix(execucao_id), n_processadas, custo,
        )

    try:
        await credito_service.confirmar_debito(
            db,
            str(execucao.usuario_id),
            reservado=reserva,
            quantidade=custo,
            descricao=(
                f"Inlinks automaticos: {custo} creditos "
                f"(base={'0' if n_aplicados == 0 else ferramenta_service.CUSTO_BASE_INLINKS}, "
                f"urls={n_processadas})"
            ),
            ferramenta="inlinks_automaticos",
            execucao_id=execucao_id,
        )
    except ValueError:
        await credito_service.liberar_reserva(db, str(execucao.usuario_id), reserva)
        execucao.status = "falhou"
        execucao.erro_msg = "Saldo insuficiente"
        execucao.concluida_em = datetime.now(UTC)
        await db.flush()
        return

    execucao.status = "concluida"
    execucao.creditos_cobrados = custo
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.now(UTC)
    await db.flush()
    logger.info("%s inlinks status=concluida creditos=%d", _log_prefix(execucao_id), custo)


def _extrair_resultado_inlinks(estado: dict[str, Any] | None) -> dict[str, Any]:
    if not estado:
        return {"artigo_titulo": "", "artigo": "", "inlinks": []}

    resultado = estado.get("resultado_final", {})
    if resultado:
        return resultado

    pilar_mod = estado.get("pilar_modificado", "")
    return {
        "artigo_titulo": estado.get("pilar_resultado", {}).get("titulo", ""),
        "artigo": pilar_mod,
        "conteudo_markdown": pilar_mod,
        "pilar_original": estado.get("pilar_resultado", {}).get("conteudo_md", ""),
        "imagem_url": None,
        "n_candidatas_validas": estado.get("n_candidatas_validas", 0),
        "n_aplicadas": len([il for il in estado.get("inlinks_revisados", []) if il.get("status") == "aplicado"]),
        "n_rejeitadas": len([il for il in estado.get("inlinks_revisados", []) if il.get("status") != "aplicado"]),
        "inlinks": estado.get("inlinks_revisados", []),
    }
