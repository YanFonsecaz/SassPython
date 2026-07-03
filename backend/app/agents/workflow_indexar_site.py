"""SPEC_Inlinks_Descoberta_Automatica_Candidatas — workflow de indexação do site.

Pipeline linear (sem LangGraph): baixa sitemap → scrape em paralelo (semáforo do
scraper) → cleaner+enriquecedor+embeddings SÓ para hash novo → upsert em
conteudos_vetores com cliente_id + tipo_recurso='pagina_site' → atualiza
indices_site. Reindexação incremental: só reprocessa páginas cujo html_hash mudou.
"""
import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agents.inlinks.cleaner import limpar_conteudo
from app.agents.inlinks.constantes import MAX_PAGINAS_SITE
from app.agents.inlinks.enriquecedor_metadados import enriquecer_metadados
from app.core.chunker import chunk_texto
from app.core.embeddings import gerar_embeddings_batch
from app.core.scraper import scrape_url
from app.core.sitemap import coletar_urls_do_sitemap
from app.core.workflow_events import publish_event
from app.db.session import async_session_factory
from app.models.conteudo_vetor import ConteudoVetor
from app.models.indice_site import IndiceSite

logger = logging.getLogger(__name__)


def _log_prefix(eid: str) -> str:
    return f"[eid={eid[:8]}]"


async def _gravar_etapa(execucao_id: str, etapa: str) -> None:
    from app.services import ferramenta_service
    try:
        async with async_session_factory() as session:
            await ferramenta_service.atualizar_etapa(session, execucao_id, etapa)
            await session.commit()
    except Exception as e:
        logger.debug("Falha ao gravar etapa %s: %s", etapa, e)


async def _atualizar_indice(cliente_id: str, **campos: Any) -> None:
    async with async_session_factory() as session:
        indice = (
            await session.execute(
                select(IndiceSite).where(IndiceSite.cliente_id == cliente_id)
            )
        ).scalar_one_or_none()
        if indice:
            for k, v in campos.items():
                setattr(indice, k, v)
            indice.atualizado_em = datetime.now(UTC)
            await session.commit()


async def _processar_pagina(
    cliente_id_uuid,
    usuario_id: str,
    url: str,
    *,
    execucao_id: str,
) -> dict[str, Any]:
    """Scrapa uma página e faz upsert em conteudos_vetores (incremental por hash).

    Retorna {ok, nova, url, titulo, erro}.
    """
    try:
        resultado = await scrape_url(url)
    except Exception as e:
        return {"ok": False, "nova": False, "url": url, "titulo": "", "erro": str(e)[:200]}

    if resultado.falhou or not resultado.conteudo_md.strip():
        return {
            "ok": False, "nova": False, "url": url,
            "titulo": resultado.titulo, "erro": resultado.erro or "Conteúdo vazio",
        }

    url_c = resultado.url_canonica or url
    html_hash = resultado.html_hash
    titulo = resultado.titulo or url

    async with async_session_factory() as session:
        # Reuso: já existe vetor ativo para (cliente, url, hash)?
        existing = []
        if html_hash:
            existing = (
                await session.execute(
                    select(ConteudoVetor)
                    .where(
                        ConteudoVetor.cliente_id == cliente_id_uuid,
                        ConteudoVetor.url_canonica == url_c,
                        ConteudoVetor.html_hash == html_hash,
                        ConteudoVetor.tipo_recurso == "pagina_site",
                        ConteudoVetor.ativo,
                    )
                    .order_by(ConteudoVetor.chunk_index)
                )
            ).scalars().all()

        if existing:
            return {"ok": True, "nova": False, "url": url_c, "titulo": titulo, "erro": ""}

        # Cold path: limpa, enriquece, chunka, embeda, insere.
        markdown_limpo = await limpar_conteudo(resultado.conteudo_md, usuario_id)
        meta = await enriquecer_metadados(markdown_limpo, titulo, usuario_id)
        chunks = chunk_texto(markdown_limpo)
        embeddings = await gerar_embeddings_batch(
            [ch.texto[:8000] for ch in chunks], usuario_id
        )

        # Desativa vetores ativos anteriores desta URL (hash antigo ou criados
        # pelas ferramentas de inlinks) — a unique parcial (usuario_id,
        # url_canonica, chunk_index) WHERE ativo bloquearia os inserts e o
        # índice ficaria com chunks obsoletos respondendo à descoberta.
        antigos = (
            await session.execute(
                select(ConteudoVetor).where(
                    ConteudoVetor.usuario_id == usuario_id,
                    ConteudoVetor.url_canonica == url_c,
                    ConteudoVetor.ativo,
                )
            )
        ).scalars().all()
        for row in antigos:
            row.ativo = False
        if antigos:
            await session.flush()

        n_inseridos = 0
        for ch, emb in zip(chunks, embeddings, strict=False):
            if emb is None:
                continue
            vetor = ConteudoVetor(
                usuario_id=usuario_id,
                cliente_id=cliente_id_uuid,
                execucao_id=execucao_id,
                titulo=titulo,
                conteudo=ch.texto,
                tipo=meta.tipo,
                intencao=meta.intencao,
                palavras_chave=meta.palavras_chave,
                atividades=meta.entidades,
                embedding=emb,
                url_canonica=url_c,
                chunk_index=ch.ordem,
                tipo_recurso="pagina_site",
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
                n_inseridos += 1
            except IntegrityError:
                # Corrida residual: o savepoint já foi desfeito pelo begin_nested;
                # não fazer rollback da sessão (descartaria os chunks anteriores).
                logger.warning("chunk %s#%d conflitou na unique — pulado", url_c, ch.ordem)
        await session.commit()
        return {
            "ok": True, "nova": True, "url": url_c, "titulo": titulo,
            "erro": "", "n_chunks": n_inseridos,
        }


async def executar_workflow_indexar_site(execucao_id: str, ctx: dict[str, Any] | None = None) -> None:
    import uuid as _uuid

    from app.services import ferramenta_service

    cliente_id_str: str | None = None

    try:
        async with async_session_factory() as session:
            await ferramenta_service.atualizar_execucao(session, execucao_id, status="executando")
            await session.commit()
            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if not execucao:
                return
            entrada = execucao.entrada_json or {}
            cliente_id_str = str(execucao.cliente_id) if execucao.cliente_id else None
            usuario_id = str(execucao.usuario_id)
            dominio = entrada.get("dominio", "")

        if not cliente_id_str or not dominio:
            async with async_session_factory() as session:
                await ferramenta_service.finalizar_falha(
                    session, execucao_id,
                    "Indexação requer cliente_id e domínio.",
                    ferramenta="indexar_site",
                )
                await session.commit()
            return

        cliente_id_uuid = _uuid.UUID(cliente_id_str)
        await _gravar_etapa(execucao_id, "coletar_sitemap")
        await publish_event(
            execucao_id, "node_start", "coletar_sitemap",
            f"Lendo sitemap de {dominio}...",
        )

        urls = await coletar_urls_do_sitemap(dominio, teto=MAX_PAGINAS_SITE)
        if not urls:
            await _atualizar_indice(cliente_id_str, status="falhou",
                                    erro_msg="Sitemap não encontrado ou vazio. Informe URLs manualmente.")
            async with async_session_factory() as session:
                await ferramenta_service.finalizar_falha(
                    session, execucao_id,
                    f"Sitemap de {dominio} não encontrado ou vazio. "
                    "Informe as URLs candidatas manualmente.",
                    ferramenta="indexar_site",
                )
                await session.commit()
            return

        await _atualizar_indice(cliente_id_str, status="indexando", dominio=dominio, erro_msg=None)

        await publish_event(
            execucao_id, "node_progress", "coletar_sitemap",
            f"{len(urls)} URLs no sitemap. Indexando...",
        )

        # Processa em paralelo (o scraper já tem semáforo global + por host).
        semaforo = asyncio.Semaphore(5)
        total = len(urls)
        feitas = 0
        n_novas = 0
        n_falhas = 0
        urls_novas: list[str] = []

        async def _uma(u: str):
            nonlocal feitas, n_novas, n_falhas
            async with semaforo:
                try:
                    r = await _processar_pagina(
                        cliente_id_uuid, usuario_id, u, execucao_id=execucao_id,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # Uma página com erro não pode derrubar a indexação inteira.
                    logger.warning("%s página %s falhou: %s", _log_prefix(execucao_id), u, e)
                    r = {"ok": False, "nova": False, "url": u, "titulo": "", "erro": str(e)[:200]}
            feitas += 1
            if r["ok"]:
                if r["nova"]:
                    n_novas += 1
                    urls_novas.append(r["url"])
            else:
                n_falhas += 1
            if feitas % 10 == 0 or feitas == total:
                await publish_event(
                    execucao_id, "node_progress", "indexar",
                    f"Indexando {feitas}/{total} páginas ({n_novas} novas)",
                )
                await _atualizar_indice(
                    cliente_id_str, n_paginas=feitas - n_falhas, n_falhas=n_falhas,
                )

        await _gravar_etapa(execucao_id, "indexar")
        await asyncio.gather(*[_uma(u) for u in urls])

        await _atualizar_indice(
            cliente_id_str, status="pronto", n_paginas=total - n_falhas, n_falhas=n_falhas,
            erro_msg=None,
        )
        await publish_event(
            execucao_id, "node_complete", "indexar",
            f"Índice pronto: {n_novas} páginas novas de {total}.",
        )

        resultado_json = {
            "dominio": dominio,
            "n_urls_sitemap": total,
            "n_paginas_novas": n_novas,
            "n_falhas": n_falhas,
            "urls_novas": urls_novas[:200],
        }
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_sucesso_indexar_site(session, execucao_id, resultado_json)
            await session.commit()

    except asyncio.CancelledError:
        logger.info("%s Workflow indexar_site cancelado", _log_prefix(execucao_id))
        async with async_session_factory() as session:
            from app.services import credito_service
            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if execucao and execucao.status == "executando":
                reserva = ferramenta_service._obter_reserva_estimada("indexar_site", execucao)
                if reserva > 0:
                    await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
                await ferramenta_service.atualizar_execucao(
                    session, execucao_id, status="cancelada", creditos_cobrados=0,
                )
                await session.commit()
        raise

    except Exception as e:
        logger.error("%s Workflow indexar_site falhou: %s", _log_prefix(execucao_id), e)
        if cliente_id_str:
            await _atualizar_indice(cliente_id_str, status="falhou", erro_msg=str(e)[:500])
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(
                session, execucao_id, "Erro interno do workflow indexar_site",
                ferramenta="indexar_site",
            )
            await session.commit()
