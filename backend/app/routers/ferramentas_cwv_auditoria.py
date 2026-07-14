"""Router da auditoria CWV (SPEC_CWV_Auditoria_Ciclo_De_Vida).

Campanha before → implementação → after com checklist colaborativo. Não toca
em billing — criação de auditoria é gratuita; execuções continuam com billing próprio.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.cliente import Cliente
from app.models.cwv_auditoria import CwvAuditoria
from app.models.cwv_checklist_item import CwvChecklistItem
from app.models.execucao_ferramenta import ExecucaoFerramenta
from app.models.usuario import Usuario
from app.schemas.cwv_auditoria import (
    AuditoriaCriarRequest,
    AuditoriaListResponse,
    AuditoriaPatch,
    AuditoriaResposta,
    ChecklistItemPatch,
    ChecklistItemResposta,
)
from app.services.cwv_auditoria_service import avancar_fase, criar_auditoria

logger = logging.getLogger(__name__)
router = APIRouter()


async def _validar_cliente(db: AsyncSession, usuario_id: str, cliente_id: str) -> Cliente:
    resultado = await db.execute(
        select(Cliente).where(Cliente.id == cliente_id, Cliente.usuario_id == usuario_id)
    )
    cliente = resultado.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return cliente


def _item_to_dict(item: CwvChecklistItem) -> dict:
    return {
        "id": str(item.id),
        "origem": item.origem,
        "item_codigo": item.item_codigo,
        "titulo": item.titulo,
        "status_before": item.status_before,
        "status_after": item.status_after,
        "status_implementacao": item.status_implementacao,
        "nota_cliente": item.nota_cliente,
        "nota_seo": item.nota_seo,
        "prioridade": item.prioridade,
        "esforco": item.esforco,
        "escopo_json": item.escopo_json or {},
    }


async def _auditoria_to_dict(db: AsyncSession, auditoria: CwvAuditoria) -> dict[str, Any]:
    itens_result = await db.execute(
        select(CwvChecklistItem)
        .where(CwvChecklistItem.auditoria_id == auditoria.id)
        .order_by(
            # Fails primeiro (prioridade > 0), depois por prioridade.
            CwvChecklistItem.status_before != "fail",
            CwvChecklistItem.prioridade,
        )
    )
    itens = list(itens_result.scalars().all())
    checklist = [_item_to_dict(i) for i in itens]
    return {
        "id": str(auditoria.id),
        "cliente_id": str(auditoria.cliente_id),
        "titulo": auditoria.titulo,
        "fase": auditoria.fase,
        "execucao_before_id": str(auditoria.execucao_before_id) if auditoria.execucao_before_id else None,
        "execucao_after_id": str(auditoria.execucao_after_id) if auditoria.execucao_after_id else None,
        "health_score_before": float(auditoria.health_score_before) if auditoria.health_score_before is not None else None,
        "health_score_after": float(auditoria.health_score_after) if auditoria.health_score_after is not None else None,
        "consolidacao_status": auditoria.consolidacao_status,
        "checklist": checklist,
        "n_pass_before": sum(1 for i in itens if i.status_before == "pass"),
        "n_fail_before": sum(1 for i in itens if i.status_before == "fail"),
        "n_implementados": sum(1 for i in itens if i.status_implementacao == "implementado"),
        "criado_em": auditoria.criado_em.isoformat() if auditoria.criado_em else "",
        "atualizado_em": auditoria.atualizado_em.isoformat() if auditoria.atualizado_em else "",
    }


@router.post("/core-web-vitals/auditorias", response_model=AuditoriaResposta, status_code=201)
async def criar_auditoria_endpoint(
    corpo: AuditoriaCriarRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    await _validar_cliente(db, str(usuario.id), str(corpo.cliente_id))

    # Valida que a execução é do usuário, é CWV e está concluída.
    exec_result = await db.execute(
        select(ExecucaoFerramenta).where(
            ExecucaoFerramenta.id == corpo.execucao_id,
            ExecucaoFerramenta.usuario_id == usuario.id,
        )
    )
    execucao = exec_result.scalar_one_or_none()
    if not execucao:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")
    if execucao.ferramenta != "core_web_vitals":
        raise HTTPException(status_code=409, detail="Execucao nao e do Core Web Vitals")
    if execucao.status != "concluida":
        raise HTTPException(status_code=409, detail="Execucao precisa estar concluida para criar auditoria")

    auditoria = await criar_auditoria(
        db,
        usuario_id=str(usuario.id),
        cliente_id=str(corpo.cliente_id),
        execucao_id=str(corpo.execucao_id),
        titulo=corpo.titulo,
    )
    await db.commit()
    await db.refresh(auditoria)
    return await _auditoria_to_dict(db, auditoria)


@router.get("/core-web-vitals/auditorias", response_model=AuditoriaListResponse)
async def listar_auditorias(
    cliente_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    await _validar_cliente(db, str(usuario.id), str(cliente_id))
    result = await db.execute(
        select(CwvAuditoria)
        .where(CwvAuditoria.cliente_id == cliente_id)
        .order_by(CwvAuditoria.criado_em.desc())
    )
    auditorias = list(result.scalars().all())
    out = []
    for a in auditorias:
        itens_count = await db.execute(
            select(CwvChecklistItem).where(CwvChecklistItem.auditoria_id == a.id)
        )
        n_itens = len(list(itens_count.scalars().all()))
        out.append({
            "id": str(a.id),
            "titulo": a.titulo,
            "fase": a.fase,
            "health_score_before": float(a.health_score_before) if a.health_score_before is not None else None,
            "health_score_after": float(a.health_score_after) if a.health_score_after is not None else None,
            "n_itens": n_itens,
            "criado_em": a.criado_em.isoformat() if a.criado_em else "",
        })
    return {"auditorias": out}


@router.get("/core-web-vitals/auditorias/{auditoria_id}", response_model=AuditoriaResposta)
async def buscar_auditoria(
    auditoria_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")
    return await _auditoria_to_dict(db, auditoria)


@router.patch("/core-web-vitals/auditorias/{auditoria_id}", response_model=AuditoriaResposta)
async def atualizar_auditoria(
    auditoria_id: str,
    corpo: AuditoriaPatch,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")

    if corpo.fase is not None:
        try:
            avancar_fase(auditoria, corpo.fase)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    if corpo.titulo is not None:
        auditoria.titulo = corpo.titulo

    await db.commit()
    await db.refresh(auditoria)
    return await _auditoria_to_dict(db, auditoria)


@router.patch(
    "/core-web-vitals/auditorias/{auditoria_id}/itens/{item_id}",
    response_model=ChecklistItemResposta,
)
async def atualizar_item_checklist(
    auditoria_id: str,
    item_id: str,
    corpo: ChecklistItemPatch,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    # Ownership via auditoria.
    aud_result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = aud_result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")

    result = await db.execute(
        select(CwvChecklistItem).where(
            CwvChecklistItem.id == item_id,
            CwvChecklistItem.auditoria_id == auditoria_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item nao encontrado")

    if corpo.status_implementacao is not None:
        item.status_implementacao = corpo.status_implementacao
    if corpo.nota_cliente is not None:
        item.nota_cliente = corpo.nota_cliente
    if corpo.nota_seo is not None:
        item.nota_seo = corpo.nota_seo

    await db.commit()
    await db.refresh(item)
    return _item_to_dict(item)
