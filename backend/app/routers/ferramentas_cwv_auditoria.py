"""Router da auditoria CWV (SPEC_CWV_Auditoria_Ciclo_De_Vida).

Campanha before → implementação → after com checklist colaborativo. Não toca
em billing — criação de auditoria é gratuita; execuções continuam com billing próprio.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, rate_limit_autenticado
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
from app.services.ferramenta_service import calcular_custo_cwv

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


@router.post("/core-web-vitals/auditorias/{auditoria_id}/reauditar", status_code=202)
async def reauditar_auditoria(
    auditoria_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_reanalisar", max_requests=3, window_seconds=300)),
) -> dict[str, Any]:
    """SPEC_CWV_Reauditoria_After: re-executa a análise nas mesmas URLs do before."""
    import uuid
    from datetime import UTC, datetime, timedelta

    from app.config import settings
    from app.services import credito_service

    # Ownership.
    aud_result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = aud_result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")

    # Fase deve ser aguardando_implementacao.
    if auditoria.fase != "aguardando_implementacao":
        raise HTTPException(status_code=409, detail="Auditoria precisa estar em fase 'aguardando_implementacao'")

    # Re-tentar só após falha.
    if auditoria.execucao_after_id:
        exec_check = await db.execute(
            select(ExecucaoFerramenta).where(ExecucaoFerramenta.id == auditoria.execucao_after_id)
        )
        exec_after = exec_check.scalar_one_or_none()
        if exec_after and exec_after.status not in ("falhou", "cancelada"):
            raise HTTPException(status_code=409, detail="Re-auditoria já em andamento ou concluída")

    # Reconstrói urls_por_template da execução before.
    exec_before_result = await db.execute(
        select(ExecucaoFerramenta).where(ExecucaoFerramenta.id == auditoria.execucao_before_id)
    )
    exec_before = exec_before_result.scalar_one_or_none()
    if not exec_before or not exec_before.entrada_json:
        raise HTTPException(status_code=409, detail="Execução before não encontrada ou sem entrada")

    urls_por_template = exec_before.entrada_json.get("urls_por_template")
    if not urls_por_template:
        raise HTTPException(status_code=409, detail="Execução before sem urls_por_template")

    # Conta URLs e calcula custo (mesmo cálculo do analisar_cwv).
    from app.schemas.cwv import UrlsPorTemplate

    urls_obj = UrlsPorTemplate(**urls_por_template)
    n_urls = urls_obj.total()
    custo = calcular_custo_cwv(n_urls * 2)

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), custo)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc

    # Cria execução com campos extras (auditoria_id, fase_auditoria) irmãos de urls_por_template.
    entrada_json = {
        "cliente_id": str(auditoria.cliente_id),
        "urls_por_template": urls_por_template,  # shape idêntico — _obter_reserva_estimada lê este campo
        "auditoria_id": str(auditoria.id),
        "fase_auditoria": "after",
    }
    execucao = ExecucaoFerramenta(
        usuario_id=str(usuario.id),
        cliente_id=str(auditoria.cliente_id),
        ferramenta="core_web_vitals",
        status="pendente",
        entrada_json={k: str(v) if isinstance(v, uuid.UUID) else v for k, v in entrada_json.items()},
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=settings.cwv_workflow_timeout),
    )
    db.add(execucao)
    await db.flush()

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow_cwv", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        logger.error("Falha ao enfileirar re-auditoria: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        execucao.status = "falhou"
        execucao.erro_msg = "Falha ao enfileirar workflow"
        await db.flush()

    # Atualiza auditoria: vincula execução after + avança fase.
    auditoria.execucao_after_id = execucao.id
    try:
        avancar_fase(auditoria, "after")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()

    return {
        "id": str(execucao.id),
        "status": execucao.status,
        "custo_estimado": custo,
        "auditoria_id": str(auditoria.id),
    }


@router.post("/core-web-vitals/auditorias/{auditoria_id}/consolidar", status_code=202)
async def consolidar_auditoria(
    auditoria_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    """SPEC_CWV_Consolidador_Cross_URL: enfileira a consolidação."""
    aud_result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = aud_result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")
    if not auditoria.execucao_before_id:
        raise HTTPException(status_code=409, detail="Auditoria sem execucao before")
    if auditoria.consolidacao_status == "executando":
        raise HTTPException(status_code=409, detail="Consolidação já em andamento")

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        await redis.enqueue_job("executar_consolidador_cwv", auditoria_id)
        auditoria.consolidacao_status = "executando"
        await db.commit()
    except Exception as e:
        logger.error("Falha ao enfileirar consolidação: %s", e)
        auditoria.consolidacao_status = "falhou"
        await db.commit()
        raise HTTPException(status_code=500, detail="Falha ao enfileirar consolidação") from e

    return {"status": "executando", "auditoria_id": auditoria_id}


@router.get("/core-web-vitals/auditorias/{auditoria_id}/consolidados")
async def listar_consolidados(
    auditoria_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    """SPEC_CWV_Consolidador_Cross_URL: lista consolidados da auditoria."""
    from app.models.cwv_problema_consolidado import CwvProblemaConsolidado

    aud_result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = aud_result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")

    result = await db.execute(
        select(CwvProblemaConsolidado)
        .where(CwvProblemaConsolidado.auditoria_id == auditoria_id)
        .order_by(CwvProblemaConsolidado.prioridade_ordem)
    )
    consolidados = []
    for c in result.scalars().all():
        consolidados.append({
            "id": str(c.id),
            "titulo": c.titulo,
            "causa_raiz": c.causa_raiz,
            "kb_codigo": c.kb_codigo,
            "severidade": c.severidade,
            "prioridade_ordem": c.prioridade_ordem,
            "esforco": c.esforco,
            "metricas_afetadas": c.metricas_afetadas or [],
            "escopo_json": c.escopo_json or {},
            "evidencias_json": c.evidencias_json or {},
            "recomendacao_md": c.recomendacao_md,
            "problemas_origem_ids": c.problemas_origem_ids or [],
        })
    return {"consolidados": consolidados, "status": auditoria.consolidacao_status}


@router.post("/core-web-vitals/auditorias/{auditoria_id}/relatorio", status_code=202)
async def gerar_relatorio_auditoria(
    auditoria_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    """SPEC_CWV_Relatorio_Executivo: enfileira a geração do relatório executivo."""
    aud_result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = aud_result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")
    if auditoria.consolidacao_status != "concluida":
        raise HTTPException(status_code=409, detail="Consolidação precisa estar concluída antes do relatório")

    rel = auditoria.relatorio_json or {}
    if isinstance(rel, dict) and rel.get("status") == "gerando":
        raise HTTPException(status_code=409, detail="Geração de relatório já em andamento")

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        await redis.enqueue_job("executar_relatorio_cwv", auditoria_id)
        auditoria.relatorio_json = {"status": "gerando"}
        await db.commit()
    except Exception as e:
        logger.error("Falha ao enfileirar relatório: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao enfileirar relatório") from e

    return {"status": "gerando", "auditoria_id": auditoria_id}


@router.get("/core-web-vitals/auditorias/{auditoria_id}/docx")
async def exportar_auditoria_docx(
    auditoria_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_export", max_requests=30, window_seconds=300)),
) -> StreamingResponse:
    """SPEC_CWV_Relatorio_Executivo: DOCX da auditoria completa (8 seções)."""
    import asyncio
    import io

    from app.models.cwv_page_experience import CwvPageExperience
    from app.models.cwv_problema_consolidado import CwvProblemaConsolidado
    from app.services.cwv_export import relatorio_auditoria_para_html, slugify_titulo
    from app.services.cwv_persistencia import buscar_analises_da_execucao
    from app.services.parecer_service import html_para_docx_bytes

    aud_result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = aud_result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")

    # Checklist.
    itens_result = await db.execute(
        select(CwvChecklistItem).where(CwvChecklistItem.auditoria_id == auditoria_id)
        .order_by(CwvChecklistItem.status_before != "fail", CwvChecklistItem.prioridade)
    )
    checklist = [{
        "item_codigo": i.item_codigo, "titulo": i.titulo,
        "status_before": i.status_before, "status_after": i.status_after,
        "status_implementacao": i.status_implementacao,
        "prioridade": i.prioridade, "esforco": i.esforco,
    } for i in itens_result.scalars().all()]

    # Consolidados.
    consol_result = await db.execute(
        select(CwvProblemaConsolidado).where(CwvProblemaConsolidado.auditoria_id == auditoria_id)
        .order_by(CwvProblemaConsolidado.prioridade_ordem)
    )
    consolidados = [{
        "titulo": c.titulo, "causa_raiz": c.causa_raiz, "esforco": c.esforco,
        "escopo_json": c.escopo_json or {}, "recomendacao_md": c.recomendacao_md,
    } for c in consol_result.scalars().all()]

    # Page experience.
    pe_result = await db.execute(
        select(CwvPageExperience).where(CwvPageExperience.execucao_id == auditoria.execucao_before_id)
    )
    page_exp = [{
        "origem": r.origem, "https": r.https, "ssl": r.ssl, "redirect_301": r.redirect_301,
        "security_headers": r.security_headers, "mixed_content": r.mixed_content,
        "mobile_friendly": r.mobile_friendly,
    } for r in pe_result.scalars().all()]

    # Análises (para CrUX).
    analises = []
    if auditoria.execucao_before_id:
        analises = await buscar_analises_da_execucao(db, str(auditoria.execucao_before_id))

    # Cliente.
    cliente_nome = ""
    from app.models.cliente import Cliente as ClienteModel

    if auditoria.cliente_id:
        cliente = await db.get(ClienteModel, auditoria.cliente_id)
        cliente_nome = cliente.nome if cliente else ""

    html = relatorio_auditoria_para_html(
        auditoria={
            "criado_em": auditoria.criado_em.isoformat() if auditoria.criado_em else "",
            "fase": auditoria.fase,
            "health_score_before": float(auditoria.health_score_before) if auditoria.health_score_before is not None else None,
            "health_score_after": float(auditoria.health_score_after) if auditoria.health_score_after is not None else None,
            "relatorio_json": auditoria.relatorio_json,
        },
        checklist=checklist,
        consolidados=consolidados,
        page_experience=page_exp,
        analises=analises,
        cliente_nome=cliente_nome,
    )
    docx = await asyncio.to_thread(html_para_docx_bytes, html)
    nome = f"cwv-relatorio-auditoria-{slugify_titulo(cliente_nome) if cliente_nome else auditoria_id[:8]}"
    return StreamingResponse(
        io.BytesIO(docx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'},
    )
