"""Router da Auditoria de SEO Técnico (SPEC_Ferramenta_Auditoria_SEO_Tecnico §3.2).

Onda 1: CRUD de auditoria + upload manual do pacote (fallback B) + edição manual
de itens. Conector/pareamento (Onda 2), IA (Onda 3) e SSE (Onda 4) ficam fora.

Nota sobre registro de rotas: o router é criado sem prefixo próprio (como
`ferramentas_cwv_auditoria`) — o prefixo de API (`/api/ferramentas`) é aplicado
no `include_router` em `app/main.py`, e cada rota aqui já embute o segmento
`/auditoria-seo-tecnico`, resultando em `/api/ferramentas/auditoria-seo-tecnico/...`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.cliente import Cliente
from app.models.seo_auditoria import SeoAuditoria
from app.models.seo_crawl import SeoCrawl
from app.models.seo_item_resultado import SeoItemResultado
from app.models.usuario import Usuario
from app.schemas.seotec import (
    AuditoriaCriar,
    AuditoriaDetalhe,
    AuditoriaResumo,
    CrawlResumo,
    ItemPatch,
    ItemResposta,
)
from app.services.ferramenta_service import calcular_custo_seo_tecnico, criar_execucao
from app.services.seotec_checklist import carregar_checklist

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
TAMANHO_CHUNK_UPLOAD = 1024 * 1024  # 1 MiB


async def _ler_upload_limitado(arquivo: UploadFile) -> bytes:
    """Lê o UploadFile em chunks, abortando com 413 assim que o acumulado
    ultrapassar MAX_UPLOAD_BYTES — evita materializar um corpo gigante na
    memória antes de checar o tamanho."""
    partes: list[bytes] = []
    total = 0
    while True:
        chunk = await arquivo.read(TAMANHO_CHUNK_UPLOAD)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Pacote acima de 50MB")
        partes.append(chunk)
    return b"".join(partes)


async def _auditoria_do_usuario(db: AsyncSession, auditoria_id: UUID, usuario: Usuario) -> SeoAuditoria:
    auditoria = await db.get(SeoAuditoria, auditoria_id)
    if auditoria is None or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria não encontrada")
    return auditoria


@router.post("/auditoria-seo-tecnico/auditorias", status_code=201, response_model=AuditoriaResumo)
async def criar_auditoria(
    body: AuditoriaCriar,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Any:
    cliente = await db.get(Cliente, body.cliente_id)
    if cliente is None or str(cliente.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    auditoria = SeoAuditoria(
        usuario_id=usuario.id, cliente_id=body.cliente_id, dominio=str(body.dominio),
    )
    db.add(auditoria)
    await db.flush()
    await db.refresh(auditoria)
    return auditoria


@router.get("/auditoria-seo-tecnico/auditorias", response_model=list[AuditoriaResumo])
async def listar_auditorias(
    cliente_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Any:
    q = select(SeoAuditoria).where(SeoAuditoria.usuario_id == usuario.id)
    if cliente_id:
        q = q.where(SeoAuditoria.cliente_id == cliente_id)
    q = q.order_by(SeoAuditoria.criado_em.desc()).limit(100)
    return list((await db.execute(q)).scalars())


@router.get("/auditoria-seo-tecnico/auditorias/{auditoria_id}", response_model=AuditoriaDetalhe)
async def detalhe_auditoria(
    auditoria_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Any:
    auditoria = await _auditoria_do_usuario(db, auditoria_id, usuario)
    crawl = (await db.execute(
        select(SeoCrawl).where(SeoCrawl.auditoria_id == auditoria.id)
        .order_by(SeoCrawl.criado_em.desc()).limit(1)
    )).scalar_one_or_none()
    linhas = {
        r.item_slug: r
        for r in (await db.execute(
            select(SeoItemResultado).where(SeoItemResultado.auditoria_id == auditoria.id)
        )).scalars()
    }
    ck = carregar_checklist()
    itens = []
    for item in ck.itens():
        linha = linhas.get(item.slug)
        itens.append(ItemResposta(
            item_slug=item.slug, nome=item.nome, categoria=item.categoria,
            peso=item.peso, prioridade=item.prioridade, fonte=item.fonte,
            modo=linha.modo if linha else ("auto" if item.fonte == "sf" else "manual"),
            status_antes=linha.status_antes if linha else None,
            status_depois=linha.status_depois if linha else None,
            evidencias_json=linha.evidencias_json if linha else {},
            status_cliente=linha.status_cliente if linha else None,
            validacao_seo=linha.validacao_seo if linha else None,
            observacao_cliente=linha.observacao_cliente if linha else None,
            observacao_seo=linha.observacao_seo if linha else None,
        ))
    return AuditoriaDetalhe(
        **AuditoriaResumo.model_validate(auditoria).model_dump(),
        ultimo_crawl=CrawlResumo.model_validate(crawl) if crawl else None,
        itens=itens,
    )


@router.patch(
    "/auditoria-seo-tecnico/auditorias/{auditoria_id}/itens/{item_slug}",
    response_model=ItemResposta,
)
async def editar_item(
    auditoria_id: UUID,
    item_slug: str,
    body: ItemPatch,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> Any:
    auditoria = await _auditoria_do_usuario(db, auditoria_id, usuario)
    ck = carregar_checklist()
    item_def = ck.itens_por_slug().get(item_slug)
    if item_def is None:
        raise HTTPException(status_code=404, detail="Item não existe no checklist")
    linha = (await db.execute(
        select(SeoItemResultado).where(
            SeoItemResultado.auditoria_id == auditoria.id,
            SeoItemResultado.item_slug == item_slug,
        )
    )).scalar_one_or_none()
    if linha is None:
        linha = SeoItemResultado(
            auditoria_id=auditoria.id, item_slug=item_slug,
            modo="auto" if item_def.fonte == "sf" else "manual",
        )
        db.add(linha)
    for campo, valor in body.model_dump(exclude_unset=True).items():
        setattr(linha, campo, valor)
    await db.flush()
    return ItemResposta(
        item_slug=item_def.slug, nome=item_def.nome, categoria=item_def.categoria,
        peso=item_def.peso, prioridade=item_def.prioridade, fonte=item_def.fonte,
        modo=linha.modo, status_antes=linha.status_antes, status_depois=linha.status_depois,
        evidencias_json=linha.evidencias_json or {}, status_cliente=linha.status_cliente,
        validacao_seo=linha.validacao_seo, observacao_cliente=linha.observacao_cliente,
        observacao_seo=linha.observacao_seo,
    )


@router.post("/auditoria-seo-tecnico/auditorias/{auditoria_id}/upload", status_code=202)
async def upload_pacote(
    auditoria_id: UUID,
    arquivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("seotec_upload", max_requests=5, window_seconds=300)),
) -> dict[str, Any]:
    auditoria = await _auditoria_do_usuario(db, auditoria_id, usuario)
    if auditoria.fase == "concluida":
        raise HTTPException(status_code=409, detail="Auditoria já concluída")
    fase_destino = "before" if auditoria.fase == "before" else "after"

    conteudo = await _ler_upload_limitado(arquivo)

    custo = calcular_custo_seo_tecnico(fase_destino)
    from app.services import credito_service

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), custo)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Créditos insuficientes") from exc

    execucao = await criar_execucao(
        db,
        usuario_id=str(usuario.id),
        cliente_id=str(auditoria.cliente_id),
        entrada={"auditoria_id": auditoria.id, "fase_destino": fase_destino},
        ferramenta="auditoria_seo_tecnico",
    )
    crawl = SeoCrawl(
        auditoria_id=auditoria.id, execucao_id=execucao.id,
        fase_destino=fase_destino, origem="upload", schema_version=1,
    )
    db.add(crawl)
    await db.flush()

    destino = Path(settings.seotec_upload_dir)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{crawl.id}.zip").write_bytes(conteudo)

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow_seotec", str(execucao.id), str(crawl.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as exc:
        logger.exception("Falha ao enfileirar SEOTEC")
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        execucao.status = "falhou"
        crawl.status = "erro"
        crawl.erro_msg = "Falha ao enfileirar workflow"
        # Deletar zip órfão antes de committar
        (Path(settings.seotec_upload_dir) / f"{crawl.id}.zip").unlink(missing_ok=True)
        # commit antes do raise: get_db faz rollback em exceção e descartaria os writes compensatórios
        await db.commit()
        raise HTTPException(status_code=503, detail="Fila indisponível, tente novamente") from exc

    return {"crawl_id": str(crawl.id), "execucao_id": str(execucao.id), "custo": custo,
            "fase_destino": fase_destino, "status": crawl.status}
