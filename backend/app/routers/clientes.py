import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.indice_site import IndiceSite
from app.models.usuario import Usuario
from app.schemas.cliente import (
    ClienteCreateRequest,
    ClienteListResponse,
    ClienteResponse,
    ClienteUpdateRequest,
    MensagemResponse,
)
from app.services import cliente_service, ferramenta_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=ClienteListResponse)
async def listar_clientes(
    busca: str = Query(default=""),
    limite: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    clientes, total = await cliente_service.listar_clientes(db, str(usuario.id), busca=busca, limite=limite, offset=offset)
    return {"clientes": clientes, "total": total}


@router.post("", response_model=ClienteResponse, status_code=201)
async def criar_cliente(
    body: ClienteCreateRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    limite_ok = await cliente_service.verificar_limite_clientes(db, str(usuario.id))
    if not limite_ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Limite de clientes atingido para seu plano")

    cliente = await cliente_service.criar_cliente(
        db,
        usuario_id=str(usuario.id),
        nome=body.nome,
        site_url=body.site_url,
        config_json=body.config_json.model_dump(),
    )
    return cliente


@router.get("/{cliente_id}", response_model=ClienteResponse)
async def buscar_cliente(
    cliente_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    cliente = await cliente_service.buscar_cliente(db, cliente_id, str(usuario.id))
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return cliente


@router.put("/{cliente_id}", response_model=ClienteResponse)
async def atualizar_cliente(
    cliente_id: str,
    body: ClienteUpdateRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    update_data = body.model_dump(exclude_none=True)

    cliente = await cliente_service.atualizar_cliente(db, cliente_id, str(usuario.id), **update_data)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return cliente


@router.delete("/{cliente_id}", response_model=MensagemResponse)
async def remover_cliente(
    cliente_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from fastapi import HTTPException

    removido = await cliente_service.remover_cliente(db, cliente_id, str(usuario.id))
    if not removido:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return {"mensagem": "Cliente removido com sucesso"}


# ──────────────────────────────────────────────────────────────────────────────
# SPEC_Inlinks_Descoberta_Automatica_Candidatas: índice do site por cliente.
# ──────────────────────────────────────────────────────────────────────────────


def _extrair_dominio(site_url: str | None) -> str | None:
    if not site_url:
        return None
    parsed = urlparse(site_url if "://" in site_url else f"https://{site_url}")
    host = parsed.hostname
    return host.lower() if host else None


async def _validar_cliente_do_usuario(db: AsyncSession, cliente_id: str, usuario_id: str):
    cliente = await cliente_service.buscar_cliente(db, cliente_id, usuario_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return cliente


@router.get("/{cliente_id}/indice-site")
async def obter_indice_site(
    cliente_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    """Status do índice do site do cliente (card 'Índice do site' no frontend)."""
    await _validar_cliente_do_usuario(db, cliente_id, str(usuario.id))
    indice = (
        await db.execute(
            select(IndiceSite).where(IndiceSite.cliente_id == cliente_id)
        )
    ).scalar_one_or_none()
    if not indice:
        return {"status": "nao_indexado", "n_paginas": 0, "n_falhas": 0,
                "dominio": None, "atualizado_em": None}
    return {
        "status": indice.status,
        "n_paginas": indice.n_paginas,
        "n_falhas": indice.n_falhas,
        "dominio": indice.dominio,
        "atualizado_em": indice.atualizado_em,
        "erro_msg": indice.erro_msg,
    }


@router.post("/{cliente_id}/indexar-site", status_code=202)
async def indexar_site(
    cliente_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("indexar_site", max_requests=2, window_seconds=60)),
) -> dict[str, Any]:
    """Enfileira a indexação do site do cliente (sitemap → pgvector)."""
    from app.core.redis_pool import get_redis_pool

    cliente = await _validar_cliente_do_usuario(db, cliente_id, str(usuario.id))
    site_url = cliente.get("site_url") if isinstance(cliente, dict) else getattr(cliente, "site_url", None)
    dominio = _extrair_dominio(site_url)
    if not dominio:
        raise HTTPException(status_code=422, detail="Cliente sem site_url configurado.")

    # Estima custo pelo teto de páginas (reserva alta; confirma pelo real).
    from app.agents.inlinks.constantes import MAX_PAGINAS_SITE
    from app.services import credito_service

    reserva = ferramenta_service.calcular_custo_indexar_site(MAX_PAGINAS_SITE)
    try:
        await credito_service.reservar_creditos(db, str(usuario.id), reserva)
    except ValueError as exc:
        raise HTTPException(
            status_code=402,
            detail=f"Créditos insuficientes (necessário reservar até {reserva} para o teto de {MAX_PAGINAS_SITE} páginas)",
        ) from exc

    from app.models.execucao_ferramenta import ExecucaoFerramenta

    execucao = ExecucaoFerramenta(
        usuario_id=str(usuario.id),
        cliente_id=cliente_id,
        ferramenta="indexar_site",
        status="pendente",
        entrada_json={"dominio": dominio},
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=settings.indexar_workflow_timeout),
    )
    db.add(execucao)

    # Cria/atualiza o registro do índice como 'indexando'.
    indice_existente = (
        await db.execute(select(IndiceSite).where(IndiceSite.cliente_id == cliente_id))
    ).scalar_one_or_none()
    if indice_existente:
        indice_existente.status = "indexando"
        indice_existente.dominio = dominio
        indice_existente.erro_msg = None
    else:
        db.add(IndiceSite(cliente_id=cliente_id, dominio=dominio, status="indexando"))

    await db.flush()

    try:
        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_indexar_site", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        logger.error("Falha ao enfileirar indexar_site: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), reserva)
        execucao.status = "falhou"
        execucao.erro_msg = "Falha ao enfileirar workflow"
        await db.flush()

    return {
        "id": execucao.id,
        "ferramenta": "indexar_site",
        "status": execucao.status,
        "dominio": dominio,
        "custo_maximo_estimado": reserva,
    }


@router.get("/{cliente_id}/candidatas")
async def descobrir_candidatas(
    cliente_id: str,
    modo: str = Query("receber", pattern="^(receber|distribuir)$"),
    url: str | None = Query(default=None, description="URL de consulta (modo=receber)"),
    texto: str | None = Query(default=None, description="Texto de consulta"),
    k: int = Query(default=30, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    """Descoberta síncrona e GRÁTIS: top-K candidatas do índice do cliente.

    Sem LLM — cosine = pré-ranking barato (o juiz roda na execução das ferramentas).
    """
    await _validar_cliente_do_usuario(db, cliente_id, str(usuario.id))
    if not url and not texto:
        raise HTTPException(status_code=422, detail="Forneça 'url' ou 'texto' para a consulta.")

    indice = (
        await db.execute(select(IndiceSite).where(IndiceSite.cliente_id == cliente_id))
    ).scalar_one_or_none()
    if not indice or indice.status != "pronto":
        raise HTTPException(
            status_code=409,
            detail="Índice do site não está pronto. Indexe o site do cliente primeiro.",
        )

    from app.core.embeddings import gerar_embedding_single
    from app.core.scraper import scrape_url
    from app.models.conteudo_vetor import ConteudoVetor

    consulta_url_normalizada = None
    if url:
        resultado = await scrape_url(url)
        if resultado.falhou or not resultado.conteudo_md:
            raise HTTPException(status_code=422, detail=f"Não foi possível ler a URL de consulta: {resultado.erro}")
        consulta_url_normalizada = resultado.url_canonica or url
        emb_consulta = await gerar_embedding_single(resultado.conteudo_md[:8000], str(usuario.id))
    else:
        emb_consulta = await gerar_embedding_single(texto[:8000], str(usuario.id))

    if emb_consulta is None:
        raise HTTPException(status_code=500, detail="Falha ao gerar embedding da consulta.")

    # Busca paginas_site do cliente, melhor chunk por URL.
    linhas = (
        await db.execute(
            select(
                ConteudoVetor.url_canonica,
                ConteudoVetor.titulo,
                ConteudoVetor.resumo,
                ConteudoVetor.embedding.cosine_distance(emb_consulta).label("distancia"),
            )
            .where(
                ConteudoVetor.cliente_id == cliente_id,
                ConteudoVetor.tipo_recurso == "pagina_site",
                ConteudoVetor.ativo,
            )
            .order_by("distancia")
            .limit(k * 4)  # sobre-amostra; agrupamos por URL depois
        )
    ).all()

    melhores_por_url: dict[str, dict[str, Any]] = {}
    for url_c, titulo, resumo, distancia in linhas:
        # exclui a própria URL consultada (modo receber: não sugerir linkar pra si).
        if consulta_url_normalizada and url_c == consulta_url_normalizada:
            continue
        score = 1.0 - float(distancia)  # cosine_distance → similaridade
        atual = melhores_por_url.get(url_c)
        if atual is None or score > atual["score"]:
            melhores_por_url[url_c] = {
                "url": url_c, "titulo": titulo or "", "resumo": (resumo or "")[:200],
                "score": round(score, 3),
            }

    candidatas = sorted(melhores_por_url.values(), key=lambda x: x["score"], reverse=True)[:k]
    return {"candidatas": candidatas, "modo": modo, "total": len(candidatas)}
