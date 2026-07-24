"""Router da auditoria CWV (SPEC_CWV_Auditoria_Ciclo_De_Vida).

Campanha before → implementação → after com checklist colaborativo. Não toca
em billing — criação de auditoria é gratuita; execuções continuam com billing próprio.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

from app.dependencies import (
    get_auditoria_do_usuario,
    get_current_user,
    get_db,
    rate_limit_autenticado,
)
from app.models.cliente import Cliente
from app.models.cwv_auditoria import CwvAuditoria
from app.models.cwv_checklist_item import CwvChecklistItem
from app.models.execucao_ferramenta import ExecucaoFerramenta
from app.models.usuario import Usuario
from app.schemas.cwv_auditoria import (
    ArtefatoAgenticoResposta,
    AuditoriaCriarRequest,
    AuditoriaListResponse,
    AuditoriaPatch,
    AuditoriaResposta,
    ChecklistItemPatch,
    ChecklistItemResposta,
    ComparativoResposta,
    ConsolidadosResposta,
    ItemDetalheResposta,
)
from app.services.cwv_auditoria_service import (
    avancar_fase,
    chave_problema,
    criar_auditoria,
    montar_comparativo,
    montar_detalhe_item,
    montar_evidencias,
)
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
        "metricas_afetadas": item.metricas_afetadas or [],
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
        "relatorio_json": auditoria.relatorio_json or None,
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
    cliente_id: UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    """Lista auditorias — de um cliente, ou todas do usuário (sem ``cliente_id``).

    SPEC_CWV_Paginacao_Listagens: ``limit``/``offset`` aditivos. Default 20
    mantém compat com clientes antigos (campos extras são ignorados).
    """
    from sqlalchemy import func

    if cliente_id is not None:
        await _validar_cliente(db, str(usuario.id), str(cliente_id))

    n_itens_sq = (
        select(
            CwvChecklistItem.auditoria_id.label("auditoria_id"),
            func.count(CwvChecklistItem.id).label("n_itens"),
        )
        .group_by(CwvChecklistItem.auditoria_id)
        .subquery()
    )
    base = (
        select(CwvAuditoria, Cliente.nome, func.coalesce(n_itens_sq.c.n_itens, 0))
        .join(Cliente, Cliente.id == CwvAuditoria.cliente_id)
        .outerjoin(n_itens_sq, n_itens_sq.c.auditoria_id == CwvAuditoria.id)
        .where(CwvAuditoria.usuario_id == usuario.id)
        .order_by(CwvAuditoria.criado_em.desc())
    )
    if cliente_id is not None:
        base = base.where(CwvAuditoria.cliente_id == cliente_id)

    # Contagem total na mesma query filtrada (sem carregar linhas).
    count_base = select(CwvAuditoria.id).where(CwvAuditoria.usuario_id == usuario.id)
    if cliente_id is not None:
        count_base = count_base.where(CwvAuditoria.cliente_id == cliente_id)
    total = (await db.execute(select(func.count()).select_from(count_base.subquery()))).scalar_one()

    result = await db.execute(base.limit(limit).offset(offset))
    out = []
    for a, cliente_nome, n_itens in result.all():
        out.append({
            "id": str(a.id),
            "titulo": a.titulo,
            "fase": a.fase,
            "cliente_id": str(a.cliente_id),
            "cliente_nome": cliente_nome,
            "health_score_before": float(a.health_score_before) if a.health_score_before is not None else None,
            "health_score_after": float(a.health_score_after) if a.health_score_after is not None else None,
            "n_itens": int(n_itens),
            "criado_em": a.criado_em.isoformat() if a.criado_em else "",
        })
    return {"auditorias": out, "total": int(total)}


@router.get("/core-web-vitals/auditorias/{auditoria_id}", response_model=AuditoriaResposta)
async def buscar_auditoria(
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _auditoria_to_dict(db, auditoria)


@router.get(
    "/core-web-vitals/auditorias/{auditoria_id}/comparativo",
    response_model=ComparativoResposta,
)
async def comparativo_auditoria(
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.services.cwv_persistencia import buscar_analises_da_execucao

    analises_before = await buscar_analises_da_execucao(db, str(auditoria.execucao_before_id))
    analises_after = None
    if auditoria.execucao_after_id:
        analises_after = await buscar_analises_da_execucao(db, str(auditoria.execucao_after_id))

    return {"fase": auditoria.fase, "pares": montar_comparativo(analises_before, analises_after)}


@router.patch("/core-web-vitals/auditorias/{auditoria_id}", response_model=AuditoriaResposta)
async def atualizar_auditoria(
    corpo: AuditoriaPatch,
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # Transições manuais permitidas; 'after' só é atingida pela re-auditoria
    # (que vincula a execução after) — nunca por PATCH direto.
    transicoes_manuais = {("before", "aguardando_implementacao"), ("after", "concluida")}
    if corpo.fase is not None:
        if (auditoria.fase, corpo.fase) not in transicoes_manuais:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Transição manual '{auditoria.fase}' → '{corpo.fase}' não permitida. "
                    "Use a re-auditoria para chegar à fase 'after'."
                ),
            )
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
    item_id: str,
    corpo: ChecklistItemPatch,
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(CwvChecklistItem).where(
            CwvChecklistItem.id == item_id,
            CwvChecklistItem.auditoria_id == auditoria.id,
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
    if corpo.prioridade is not None:
        item.prioridade = corpo.prioridade
    # SPEC_CWV_Checklist_Itens_Manuais: status automático editável só em itens manuais.
    if corpo.status_before is not None or corpo.status_after is not None:
        if not item.item_codigo.startswith("manual_"):
            raise HTTPException(
                status_code=422,
                detail="Status automático (before/after) só é editável em itens manuais",
            )
        if corpo.status_before is not None:
            item.status_before = corpo.status_before
        if corpo.status_after is not None:
            item.status_after = corpo.status_after

    await db.commit()
    await db.refresh(item)
    return _item_to_dict(item)


@router.get(
    "/core-web-vitals/auditorias/{auditoria_id}/itens/{item_id}/detalhe",
    response_model=ItemDetalheResposta,
)
async def detalhe_item_checklist(
    item_id: str,
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """SPEC_CWV_Auditoria_UI_V2: ficha do problema (o que é + como corrigir, KB).

    Carregada sob demanda ao expandir a linha do checklist — mantém a lista leve.
    """
    result = await db.execute(
        select(CwvChecklistItem).where(
            CwvChecklistItem.id == item_id,
            CwvChecklistItem.auditoria_id == auditoria.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item nao encontrado")

    # Plataforma para escolher a solução específica: detectada na execução before.
    from app.models.cwv_analise import CwvAnalise
    from app.models.cwv_problema import CwvProblema

    plataforma = None
    if auditoria.execucao_before_id:
        plat_result = await db.execute(
            select(CwvAnalise.plataforma_detectada)
            .where(CwvAnalise.execucao_id == auditoria.execucao_before_id)
            .limit(1)
        )
        plataforma = plat_result.scalar_one_or_none()

    # Evidências (elementos com falha por URL×estratégia) — só para fails de PSI.
    # SPEC_CWV_Detalhe_Evidencias_Elementos.
    evidencias: list[dict] = []
    if item.origem == "psi_audit" and item.status_before == "fail" and auditoria.execucao_before_id:
        probs_result = await db.execute(
            select(CwvProblema, CwvAnalise.url_canonica, CwvAnalise.estrategia)
            .join(CwvAnalise, CwvAnalise.id == CwvProblema.analise_id)
            .where(CwvAnalise.execucao_id == auditoria.execucao_before_id)
        )
        rows_grupo = [
            (p, url, estrategia)
            for p, url, estrategia in probs_result.all()
            if chave_problema(p) == item.item_codigo
        ]
        evidencias = montar_evidencias(rows_grupo)

    urls_escopo = (item.escopo_json or {}).get("urls") or []
    return montar_detalhe_item(
        item_codigo=item.item_codigo,
        titulo=item.titulo,
        esforco=item.esforco,
        urls_escopo=urls_escopo,
        plataforma=plataforma,
        evidencias=evidencias,
    )


@router.post("/core-web-vitals/auditorias/{auditoria_id}/reauditar", status_code=202)
async def reauditar_auditoria(
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_reanalisar", max_requests=3, window_seconds=300)),
) -> dict[str, Any]:
    """SPEC_CWV_Reauditoria_After: re-executa a análise nas mesmas URLs do before."""
    import uuid
    from datetime import UTC, datetime, timedelta

    from app.config import settings
    from app.services import credito_service

    # Fase: primeira re-auditoria parte de aguardando_implementacao; fase 'after'
    # é aceita apenas para re-tentar após falha (guard abaixo).
    if auditoria.fase not in ("aguardando_implementacao", "after"):
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

    enqueue_ok = True
    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow_cwv", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        enqueue_ok = False
        logger.error("Falha ao enfileirar re-auditoria: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        execucao.status = "falhou"
        execucao.erro_msg = "Falha ao enfileirar workflow"
        await db.flush()

    # Vincula execução after + avança fase SOMENTE com enqueue ok — em falha a
    # auditoria fica intocada em aguardando_implementacao e o retry é possível.
    if enqueue_ok:
        auditoria.execucao_after_id = execucao.id
        if auditoria.fase == "aguardando_implementacao":
            avancar_fase(auditoria, "after")
    await db.commit()

    return {
        "id": str(execucao.id),
        "status": execucao.status,
        "custo_estimado": custo,
        "auditoria_id": str(auditoria.id),
    }


@router.post("/core-web-vitals/auditorias/{auditoria_id}/consolidar", status_code=202)
async def consolidar_auditoria(
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """SPEC_CWV_Consolidador_Cross_URL: enfileira a consolidação."""
    if not auditoria.execucao_before_id:
        raise HTTPException(status_code=409, detail="Auditoria sem execucao before")
    if auditoria.consolidacao_status == "executando":
        raise HTTPException(status_code=409, detail="Consolidação já em andamento")

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        await redis.enqueue_job("executar_consolidador_cwv", str(auditoria.id))
        auditoria.consolidacao_status = "executando"
        await db.commit()
    except Exception as e:
        logger.error("Falha ao enfileirar consolidação: %s", e)
        auditoria.consolidacao_status = "falhou"
        await db.commit()
        raise HTTPException(status_code=500, detail="Falha ao enfileirar consolidação") from e

    return {"status": "executando", "auditoria_id": str(auditoria.id)}


@router.get(
    "/core-web-vitals/auditorias/{auditoria_id}/consolidados",
    response_model=ConsolidadosResposta,
)
async def listar_consolidados(
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """SPEC_CWV_Consolidador_Cross_URL: lista consolidados da auditoria.

    SPEC_CWV_Contratos_JSONB_Tipados: response_model = ``ConsolidadosResposta``
    (espelha ``ProblemaConsolidadoResposta`` TS). Campos fora do schema são
    descartados — diff verificado antes de ativar.
    """
    from app.models.cwv_problema_consolidado import CwvProblemaConsolidado

    result = await db.execute(
        select(CwvProblemaConsolidado)
        .where(CwvProblemaConsolidado.auditoria_id == auditoria.id)
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


# --- SPEC_CWV_Navegacao_Agentica_Geracao_IA: geração de artefatos por IA ------


def _artefato_to_dict(row) -> dict[str, Any]:
    return {
        "tipo": row.tipo,
        "diagnostico": row.diagnostico,
        "conteudo_md": row.conteudo_md,
        "explicacao_md": row.explicacao_md,
        "meta_json": row.meta_json or {},
        "modelo": row.modelo,
        "gerado_em": row.gerado_em.isoformat() if row.gerado_em else "",
    }


async def _urls_e_plataforma_da_auditoria(db: AsyncSession, auditoria: CwvAuditoria) -> tuple[list[str], str]:
    """URLs canônicas (anti-SSRF: SÓ do cliente dono) + plataforma detectada.

    Origem: análises de sucesso da execução ``before`` da auditoria. Nenhuma URL
    vem do request.
    """
    from app.models.cwv_analise import CwvAnalise

    if not auditoria.execucao_before_id:
        return [], "geral"
    res = await db.execute(
        select(CwvAnalise.url_canonica, CwvAnalise.plataforma_detectada).where(
            CwvAnalise.execucao_id == auditoria.execucao_before_id,
            CwvAnalise.status == "sucesso",
        )
    )
    rows = res.all()
    urls: list[str] = []
    for url, _ in rows:
        if url and url not in urls:
            urls.append(url)
    plataforma = next((p for _, p in rows if p), "geral")
    return urls, plataforma


@router.post(
    "/core-web-vitals/auditorias/{auditoria_id}/artefatos/{tipo}",
    response_model=ArtefatoAgenticoResposta,
)
async def gerar_artefato_agentico(
    tipo: Literal["llms_txt", "webmcp"],
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_autenticado("cwv_artefato", max_requests=10, window_seconds=300)),
) -> dict[str, Any]:
    """SPEC_CWV_Navegacao_Agentica_Geracao_IA: gera llms.txt ideal ou scaffold
    WebMCP. Kill-switch (409), fail-open (nunca 500), anti-SSRF (URLs do cliente)."""
    if not settings.cwv_agentico_llm_habilitado:
        raise HTTPException(status_code=409, detail="Geração por IA desabilitada")

    from app.agents.cwv.agentico import WEBMCP_SPEC_VERSION, CWVAgenticoAgent
    from app.models.cwv_artefato_agentico import CwvArtefatoAgentico
    from app.services.cwv_site_fetch import coletar_conteudo_site

    urls, plataforma = await _urls_e_plataforma_da_auditoria(db, auditoria)

    agora = datetime.now(UTC)
    try:
        site = await coletar_conteudo_site(urls)
        agente = CWVAgenticoAgent(usuario_id=str(auditoria.usuario_id))
        if tipo == "llms_txt":
            out = await agente.gerar_llms_txt(site, site.get("llms_txt_atual"))
            artefato = {
                "tipo": "llms_txt",
                "diagnostico": out.diagnostico,
                "conteudo_md": out.conteudo_llms_txt,
                "explicacao_md": None,
                "meta_json": {"justificativa": out.justificativa},
                "modelo": settings.cwv_agentico_llm_model,
            }
        else:
            out = await agente.gerar_webmcp(site, plataforma, site.get("webmcp") or {})
            artefato = {
                "tipo": "webmcp",
                "diagnostico": None,
                "conteudo_md": out.codigo,
                "explicacao_md": out.explicacao_md,
                "meta_json": {
                    "detectado": out.detectado,
                    "ferramentas_sugeridas": out.ferramentas_sugeridas,
                    "linguagem": out.linguagem,
                    "como_aplicar_md": out.como_aplicar_md,
                    "versao_spec": WEBMCP_SPEC_VERSION,
                    "plataforma": plataforma,
                },
                "modelo": settings.cwv_agentico_llm_model,
            }
    except Exception:
        logger.warning(
            "gerar_artefato_agentico falhou (fail-open) auditoria=%s tipo=%s",
            auditoria.id, tipo, exc_info=True,
        )
        return {
            "tipo": tipo,
            "diagnostico": None,
            "conteudo_md": "Não foi possível gerar o artefato agora. Tente novamente em instantes.",
            "explicacao_md": None,
            "meta_json": {"erro": True},
            "modelo": None,
            "gerado_em": agora.isoformat(),
        }

    # Upsert: 1 vigente por (auditoria, tipo). Regenerar substitui.
    existente_res = await db.execute(
        select(CwvArtefatoAgentico).where(
            CwvArtefatoAgentico.auditoria_id == auditoria.id,
            CwvArtefatoAgentico.tipo == tipo,
        )
    )
    row = existente_res.scalar_one_or_none()
    if row:
        row.diagnostico = artefato["diagnostico"]
        row.conteudo_md = artefato["conteudo_md"]
        row.explicacao_md = artefato["explicacao_md"]
        row.meta_json = artefato["meta_json"]
        row.modelo = artefato["modelo"]
        row.gerado_em = agora
    else:
        db.add(CwvArtefatoAgentico(auditoria_id=auditoria.id, gerado_em=agora, **artefato))
    await db.commit()
    # Resposta construída dos valores (evita lazy-load pós-commit).
    return {**artefato, "gerado_em": agora.isoformat()}


@router.get(
    "/core-web-vitals/auditorias/{auditoria_id}/artefatos/{tipo}",
    response_model=ArtefatoAgenticoResposta,
)
async def buscar_artefato_agentico(
    tipo: Literal["llms_txt", "webmcp"],
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna o artefato vigente do tipo (404 se nunca gerado)."""
    from app.models.cwv_artefato_agentico import CwvArtefatoAgentico

    res = await db.execute(
        select(CwvArtefatoAgentico).where(
            CwvArtefatoAgentico.auditoria_id == auditoria.id,
            CwvArtefatoAgentico.tipo == tipo,
        )
    )
    row = res.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Artefato ainda não gerado")
    return _artefato_to_dict(row)


@router.post("/core-web-vitals/auditorias/{auditoria_id}/relatorio", status_code=202)
async def gerar_relatorio_auditoria(
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """SPEC_CWV_Relatorio_Executivo: enfileira a geração do relatório executivo."""
    if auditoria.consolidacao_status != "concluida":
        raise HTTPException(status_code=409, detail="Consolidação precisa estar concluída antes do relatório")

    rel = auditoria.relatorio_json or {}
    if isinstance(rel, dict) and rel.get("status") == "gerando":
        raise HTTPException(status_code=409, detail="Geração de relatório já em andamento")

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        await redis.enqueue_job("executar_relatorio_cwv", str(auditoria.id))
        auditoria.relatorio_json = {"status": "gerando"}
        await db.commit()
    except Exception as e:
        logger.error("Falha ao enfileirar relatório: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao enfileirar relatório") from e

    return {"status": "gerando", "auditoria_id": str(auditoria.id)}


@router.get("/core-web-vitals/auditorias/{auditoria_id}/docx")
async def exportar_auditoria_docx(
    auditoria: CwvAuditoria = Depends(get_auditoria_do_usuario),
    db: AsyncSession = Depends(get_db),
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

    # Checklist.
    itens_result = await db.execute(
        select(CwvChecklistItem).where(CwvChecklistItem.auditoria_id == auditoria.id)
        .order_by(CwvChecklistItem.status_before != "fail", CwvChecklistItem.prioridade)
    )
    checklist = [{
        "item_codigo": i.item_codigo, "titulo": i.titulo,
        "status_before": i.status_before, "status_after": i.status_after,
        "status_implementacao": i.status_implementacao,
        "prioridade": i.prioridade, "esforco": i.esforco,
    } for i in itens_result.scalars().all()]

    # Consolidados (+ documentacao_md do problema representativo — o primeiro
    # de problemas_origem_ids — para a seção "Como corrigir" do DOCX).
    from app.models.cwv_problema import CwvProblema

    consol_result = await db.execute(
        select(CwvProblemaConsolidado).where(CwvProblemaConsolidado.auditoria_id == auditoria.id)
        .order_by(CwvProblemaConsolidado.prioridade_ordem)
    )
    consolidados_orm = list(consol_result.scalars().all())
    ids_representativos = [
        (c.problemas_origem_ids or [None])[0] for c in consolidados_orm
    ]
    docs_por_problema: dict[str, str] = {}
    ids_validos = [i for i in ids_representativos if i]
    if ids_validos:
        docs_result = await db.execute(
            select(CwvProblema.id, CwvProblema.documentacao_md).where(CwvProblema.id.in_(ids_validos))
        )
        docs_por_problema = {str(pid): doc or "" for pid, doc in docs_result.all()}
    consolidados = [{
        "titulo": c.titulo, "causa_raiz": c.causa_raiz, "esforco": c.esforco,
        "escopo_json": c.escopo_json or {}, "recomendacao_md": c.recomendacao_md,
        "documentacao_md": docs_por_problema.get(str((c.problemas_origem_ids or [None])[0] or ""), ""),
    } for c in consolidados_orm]

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
    nome = f"cwv-relatorio-auditoria-{slugify_titulo(cliente_nome) if cliente_nome else str(auditoria.id)[:8]}"
    return StreamingResponse(
        io.BytesIO(docx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'},
    )
