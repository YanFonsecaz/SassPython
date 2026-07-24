import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_analise_do_usuario,
    get_current_user,
    get_db,
    get_execucao_do_usuario,
    rate_limit_autenticado,
)
from app.models.cliente import Cliente
from app.models.usuario import Usuario

if TYPE_CHECKING:
    from app.models.cwv_analise import CwvAnalise
    from app.models.execucao_ferramenta import ExecucaoFerramenta
from app.schemas.cwv import (
    AnalisarRequest,
    AnaliseResposta,
    ComparacaoResposta,
    CustoCwvResponse,
    ExecucaoResposta,
    HealthScoreResposta,
    HistoricoListResponse,
    PageExperienceListResponse,
    PlataformaOverrideRequest,
)
from app.services.ferramenta_service import (
    CUSTO_POR_URL_CWV,
    calcular_custo_cwv,
)

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


@router.get("/core-web-vitals/custo", response_model=CustoCwvResponse)
async def custo_cwv_endpoint(
    n_urls: int = Query(1, ge=1, le=50),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    n_jobs = n_urls * 2
    custo = calcular_custo_cwv(n_jobs)
    return {
        "custo": custo,
        "custo_por_url": CUSTO_POR_URL_CWV,
        "n_urls": n_urls,
        "n_urls_reais": n_jobs,
    }


@router.post("/core-web-vitals/analisar", status_code=202)
async def analisar_cwv(
    body: AnalisarRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_analisar", max_requests=3, window_seconds=300)),
) -> dict[str, Any]:
    await _validar_cliente(db, str(usuario.id), str(body.cliente_id))

    n_urls = body.urls_por_template.total()
    custo = calcular_custo_cwv(n_urls * 2)

    from app.services import credito_service

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), custo)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc

    entrada = body.model_dump(mode="json")
    execucao = await _criar_execucao_cwv(db, str(usuario.id), str(body.cliente_id), entrada)

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow_cwv", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        logger.error("Falha ao enfileirar CWV: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        execucao.status = "falhou"
        execucao.erro_msg = "Falha ao enfileirar workflow"
        await db.flush()

    return {
        "id": str(execucao.id),
        "ferramenta": execucao.ferramenta,
        "status": execucao.status,
        "etapa_atual": execucao.etapa_atual,
        "creditos_cobrados": execucao.creditos_cobrados,
        "criado_em": str(execucao.criado_em),
        "n_urls": n_urls,
        "custo_estimado": custo,
    }


@router.get("/core-web-vitals/execucao/{execucao_id}", response_model=ExecucaoResposta)
async def buscar_execucao_cwv(
    execucao: "ExecucaoFerramenta" = Depends(get_execucao_do_usuario),
) -> dict[str, Any]:
    """SPEC_CWV_Contratos_JSONB_Tipados: ``response_model=ExecucaoResposta`` com
    ``resultado_json`` tipado (motivo_falha, health_score, auditoria_id, etc).
    """
    return {
        "id": str(execucao.id),
        "ferramenta": execucao.ferramenta,
        "status": execucao.status,
        "etapa_atual": execucao.etapa_atual,
        "creditos_cobrados": execucao.creditos_cobrados,
        "resultado_json": execucao.resultado_json,
        "entrada_json": execucao.entrada_json,
        "erro_msg": execucao.erro_msg,
        "criado_em": str(execucao.criado_em),
        "concluida_em": str(execucao.concluida_em) if execucao.concluida_em else None,
        "cliente_id": str(execucao.cliente_id) if execucao.cliente_id else None,
    }


@router.get("/core-web-vitals/execucao/{execucao_id}/health-score", response_model=HealthScoreResposta)
async def health_score_cwv(
    execucao: "ExecucaoFerramenta" = Depends(get_execucao_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Health Score % da execução (proporção de audits saudáveis).

    Se a execução já tem ``resultado_json["health_score"]``, devolve direto
    (inclui ``None`` quando a execução falhou sem análises de sucesso).
    Caso contrário (execução antiga), calcula on-the-fly a partir das análises
    persistidas — sem persistir.
    """
    from app.models.cwv_analise import CwvAnalise
    from app.services.cwv_health import calcular_health_score
    from app.services.cwv_persistencia import contar_problemas_por_analise

    # Execuções novas: o workflow já gravou o health_score (pode ser None).
    if execucao.resultado_json and "health_score" in execucao.resultado_json:
        hs = execucao.resultado_json["health_score"]
        if hs is None:
            return {"health_score": None, "n_pass": 0, "n_total": 0, "por_estrategia": {}}
        return hs

    # Execução antiga sem o campo: cálculo on-the-fly.
    res = await db.execute(
        select(CwvAnalise.id, CwvAnalise.status, CwvAnalise.estrategia, CwvAnalise.audits_totais)
        .where(CwvAnalise.execucao_id == execucao.id)
    )
    rows = res.all()
    if not rows:
        return {"health_score": None, "n_pass": 0, "n_total": 0, "por_estrategia": {}}
    contagens = await contar_problemas_por_analise(db, [str(r[0]) for r in rows])
    analises = [
        {
            "status": str(status),
            "estrategia": str(estrategia),
            "audits_totais": int(audits_totais or 0),
            "n_problemas": contagens.get(str(aid), 0),
        }
        for aid, status, estrategia, audits_totais in rows
    ]
    hs = calcular_health_score(analises)
    if hs is None:
        return {"health_score": None, "n_pass": 0, "n_total": 0, "por_estrategia": {}}
    return hs


@router.get(
    "/core-web-vitals/execucao/{execucao_id}/page-experience",
    response_model=PageExperienceListResponse,
)
async def page_experience_cwv(
    execucao: "ExecucaoFerramenta" = Depends(get_execucao_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Checagens de Page Experience por origem da execução (SPEC_CWV_Page_Experience)."""
    from app.models.cwv_page_experience import CwvPageExperience

    resultado = await db.execute(
        select(CwvPageExperience)
        .where(CwvPageExperience.execucao_id == execucao.id)
        .order_by(CwvPageExperience.origem)
    )
    origens = []
    for row in resultado.scalars().all():
        origens.append({
            "origem": row.origem,
            "https": row.https,
            "ssl": row.ssl,
            "redirect_301": row.redirect_301,
            "security_headers": row.security_headers,
            "safe_browsing": row.safe_browsing,
            "mixed_content": row.mixed_content,
            "mobile_friendly": row.mobile_friendly,
            "detalhes_json": row.detalhes_json or {},
        })
    return {"origens": origens}


@router.get("/core-web-vitals/analise/{analise_id}", response_model=AnaliseResposta)
async def buscar_analise_cwv(
    analise: "CwvAnalise" = Depends(get_analise_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.services.cwv_persistencia import buscar_analise_com_problemas

    # Re-busca com problemas (shape enriquecido que o front consome).
    return await buscar_analise_com_problemas(db, str(analise.id))


@router.get("/core-web-vitals/historico", response_model=HistoricoListResponse)
async def listar_historico_cwv(
    cliente_id: uuid.UUID,
    template: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    await _validar_cliente(db, str(usuario.id), str(cliente_id))

    from app.services.cwv_persistencia import listar_historico_cliente

    # SPEC_CWV_Paginacao_Listagens: passar limit/offset; legado passa None.
    historico, total = await listar_historico_cliente(
        db, str(cliente_id), template=template, limit=limit, offset=offset
    )
    return {"urls": historico, "total": total}


@router.get("/core-web-vitals/historico-url")
async def historico_url_cwv(
    cliente_id: uuid.UUID,
    url: str,
    estrategia: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    await _validar_cliente(db, str(usuario.id), str(cliente_id))

    from app.services.cwv_persistencia import (
        buscar_historico_url,
        buscar_ultima_analise_url,
    )

    ultima = await buscar_ultima_analise_url(db, str(cliente_id), url, estrategia=estrategia)
    analises = await buscar_historico_url(db, str(cliente_id), url, estrategia=estrategia)
    return {
        "url_canonica": url,
        "template_tipo": ultima.template_tipo if ultima else "",
        "plataforma_detectada": ultima.plataforma_detectada if ultima else "",
        "analises": analises,
    }


@router.post("/core-web-vitals/reanalisar/{analise_id}", status_code=202)
async def reanalisar_cwv(
    analise: "CwvAnalise" = Depends(get_analise_do_usuario),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_reanalisar", max_requests=3, window_seconds=300)),
) -> dict[str, Any]:
    from app.schemas.cwv import UrlsPorTemplate

    url_obj = UrlsPorTemplate(**{analise.template_tipo: [analise.url_canonica]})

    custo = calcular_custo_cwv(2)

    from app.services import credito_service

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), custo)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc

    entrada = {
        "cliente_id": str(analise.cliente_id),
        "urls_por_template": url_obj.model_dump(mode="json"),
    }
    execucao = await _criar_execucao_cwv(db, str(usuario.id), str(analise.cliente_id), entrada)

    try:
        from app.core.redis_pool import get_redis_pool

        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow_cwv", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        logger.error("Falha ao enfileirar re-analise CWV: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        execucao.status = "falhou"
        execucao.erro_msg = "Falha ao enfileirar workflow"
        await db.flush()

    return {
        "id": str(execucao.id),
        "ferramenta": execucao.ferramenta,
        "status": execucao.status,
        "etapa_atual": execucao.etapa_atual,
        "creditos_cobrados": execucao.creditos_cobrados,
        "criado_em": str(execucao.criado_em),
        "n_urls": 1,
        "custo_estimado": custo,
    }


@router.get("/core-web-vitals/comparacao/{analise_id}")
async def comparar_com_anterior(
    analise_atual: "CwvAnalise" = Depends(get_analise_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> ComparacaoResposta:

    from app.schemas.cwv import MetricaComparada, ProblemaComparado
    from app.services.cwv_persistencia import buscar_analise_anterior, buscar_problemas_analise

    analise_id = str(analise_atual.id)

    # Buscar problemas da análise atual
    problemas_atual = await buscar_problemas_analise(db, analise_id)

    # Buscar análise anterior
    analise_anterior = await buscar_analise_anterior(
        db,
        analise_atual.url_canonica,
        analise_atual.cliente_id,
        analise_atual.criado_em,
        estrategia=analise_atual.estrategia,
    )

    dias_decorridos = None
    analise_anterior_id = None
    problemas_anterior = []

    if analise_anterior:
        analise_anterior_id = str(analise_anterior.id)
        dias_decorridos = int((analise_atual.criado_em - analise_anterior.criado_em).total_seconds() / 86400)
        problemas_anterior = await buscar_problemas_analise(db, str(analise_anterior.id))

    # Calcular deltas das métricas
    metricas = {}

    # Métricas que menor valor é melhor (melhorou = True)
    menor_e_melhor = ["lcp_ms", "cls", "inp_ms", "fcp_ms", "tbt_ms", "ttfb_ms"]
    # Métrica que maior valor é melhor
    maior_e_melhor = ["score_performance"]

    for metrica in menor_e_melhor + maior_e_melhor:
        valor_atual = getattr(analise_atual, metrica)
        valor_anterior = getattr(analise_anterior, metrica) if analise_anterior else None

        if valor_atual is not None and valor_anterior is not None:
            delta = valor_atual - valor_anterior
            melhorou = None

            if metrica in menor_e_melhor:
                melhorou = delta < 0
            elif metrica == "score_performance":
                melhorou = delta > 0

            metricas[metrica] = MetricaComparada(
                antes=valor_anterior,
                depois=valor_atual,
                delta=delta,
                melhorou=melhorou
            )

    def _chave(p):
        if p.kb_codigo:
            return p.kb_codigo
        if p.audit_id:
            return f"audit:{p.audit_id}"
        return f"titulo:{p.titulo}"

    set_atual = {_chave(p) for p in problemas_atual}
    set_anterior = {_chave(p) for p in problemas_anterior}

    problemas_resolvidos = [
        ProblemaComparado(kb_codigo=p.kb_codigo, titulo=p.titulo)
        for p in problemas_anterior
        if _chave(p) not in set_atual
    ]

    problemas_novos = [
        ProblemaComparado(kb_codigo=p.kb_codigo, titulo=p.titulo)
        for p in problemas_atual
        if _chave(p) not in set_anterior
    ]

    problemas_persistentes = [
        ProblemaComparado(kb_codigo=p.kb_codigo, titulo=p.titulo)
        for p in problemas_atual
        if _chave(p) in set_anterior
    ]

    return ComparacaoResposta(
        analise_atual_id=analise_id,
        analise_anterior_id=analise_anterior_id,
        dias_decorridos=dias_decorridos,
        metricas=metricas,
        problemas_resolvidos=problemas_resolvidos,
        problemas_novos=problemas_novos,
        problemas_persistentes=problemas_persistentes
    )


@router.get("/core-web-vitals/analise/{analise_id}/irma")
async def buscar_irma_cwv(
    analise: "CwvAnalise" = Depends(get_analise_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.services.cwv_persistencia import buscar_analise_irma

    irma = await buscar_analise_irma(db, str(analise.id))
    if not irma:
        return {"existe": False, "analise": None}
    return {"existe": True, "analise": irma}


@router.patch("/core-web-vitals/analise/{analise_id}/plataforma")
async def override_plataforma_cwv(
    body: PlataformaOverrideRequest,
    analise: "CwvAnalise" = Depends(get_analise_do_usuario),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Permite usuario corrigir manualmente a plataforma detectada e regenera
    documentacao_md de todos os problemas com a nova plataforma."""
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    from app.models.cwv_problema import CwvProblema
    from app.services.cwv_kb import buscar_entrada

    nova_plataforma = body.plataforma
    analise.plataforma_detectada = nova_plataforma

    probs_result = await db.execute(
        select(CwvProblema).where(CwvProblema.analise_id == analise.id)
    )
    problemas = probs_result.scalars().all()

    agente = CWVDocumentadorAgent()
    atualizados = 0
    n_sem_kb = 0
    for p in problemas:
        entrada_kb = buscar_entrada(p.kb_codigo) if p.kb_codigo else None
        if entrada_kb is None:
            n_sem_kb += 1
            continue
        p.documentacao_md = agente._gerar_doc(
            entrada_kb, nova_plataforma, p.contexto_especifico or {}
        )
        atualizados += 1

    await db.commit()
    return {
        "plataforma": nova_plataforma,
        "n_problemas_atualizados": atualizados,
        "n_sem_kb": n_sem_kb,
    }


async def _criar_execucao_cwv(
    db: AsyncSession,
    usuario_id: str,
    cliente_id: str,
    entrada: dict[str, Any],
):
    from app.config import settings
    from app.models.execucao_ferramenta import ExecucaoFerramenta

    entrada_json = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in entrada.items()}
    execucao = ExecucaoFerramenta(
        usuario_id=usuario_id,
        cliente_id=cliente_id,
        ferramenta="core_web_vitals",
        status="pendente",
        entrada_json=entrada_json,
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=settings.cwv_workflow_timeout),
    )
    db.add(execucao)
    await db.flush()
    return execucao


@router.get("/core-web-vitals/problema/{problema_id}/docx")
async def exportar_problema_docx(
    problema_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_export", max_requests=30, window_seconds=300)),
) -> StreamingResponse:
    from app.models.cwv_analise import CwvAnalise
    from app.services import cwv_persistencia

    prob = await cwv_persistencia.buscar_problema_por_id(db, problema_id)
    if not prob:
        raise HTTPException(status_code=404, detail="Problema nao encontrado")
    analise_result = await db.execute(select(CwvAnalise).where(CwvAnalise.id == prob.analise_id))
    analise = analise_result.scalar_one_or_none()
    # Ownership via _dono_ou_404 (não vaza existência).
    from app.dependencies import _dono_ou_404
    _dono_ou_404(analise, usuario, "Problema nao encontrado")

    prob_dict = {
        "titulo": prob.titulo,
        "severidade": prob.severidade,
        "metricas_afetadas": prob.metricas_afetadas,
        "contexto_especifico": prob.contexto_especifico,
        "documentacao_md": prob.documentacao_md,
        "audit_id": prob.audit_id,
    }
    import asyncio
    import io

    from app.services.cwv_export import problema_para_html, slugify_titulo
    from app.services.parecer_service import html_para_docx_bytes
    docx = await asyncio.to_thread(html_para_docx_bytes, problema_para_html(prob_dict))
    nome = slugify_titulo(prob.titulo)
    return StreamingResponse(
        io.BytesIO(docx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'},
    )


@router.get("/core-web-vitals/analise/{analise_id}/docx")
async def exportar_relatorio_docx(
    analise: "CwvAnalise" = Depends(get_analise_do_usuario),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_autenticado("cwv_export", max_requests=30, window_seconds=300)),
) -> StreamingResponse:
    from app.services import cwv_persistencia

    analise_dict = await cwv_persistencia.buscar_analise_com_problemas(db, str(analise.id))
    if not analise_dict:
        raise HTTPException(status_code=404, detail="Analise nao encontrada")

    problemas = analise_dict.get("problemas", [])
    prob_dicts = [
        {
            "titulo": p["titulo"],
            "severidade": p["severidade"],
            "metricas_afetadas": p["metricas_afetadas"],
            "contexto_especifico": p["contexto_especifico"],
            "documentacao_md": p["documentacao_md"],
            "audit_id": p.get("audit_id"),
        }
        for p in problemas
    ]
    import asyncio
    import io

    from app.services.cwv_export import relatorio_para_html
    from app.services.parecer_service import html_para_docx_bytes
    docx = await asyncio.to_thread(html_para_docx_bytes, relatorio_para_html(analise_dict, prob_dicts))
    url_slug = analise_dict.get("url_canonica", "cwv").replace("https://", "").replace("http://", "")[:50].replace("/", "-").replace(".", "-")
    nome = f"cwv-relatorio-{url_slug}"
    return StreamingResponse(
        io.BytesIO(docx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'},
    )


@router.get("/core-web-vitals/execucao/{execucao_id}/docx")
async def exportar_execucao_docx(
    execucao: "ExecucaoFerramenta" = Depends(get_execucao_do_usuario),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_autenticado("cwv_export", max_requests=30, window_seconds=300)),
) -> StreamingResponse:
    """SPEC_CWV_Export_Consolidado_Execucao: DOCX consolidado da execução."""
    import asyncio
    import io

    from app.models.cliente import Cliente as ClienteModel
    from app.services import cwv_persistencia
    from app.services.cwv_export import relatorio_execucao_para_html, slugify_titulo
    from app.services.parecer_service import html_para_docx_bytes

    analises = await cwv_persistencia.buscar_analises_da_execucao(db, str(execucao.id))

    cliente_nome = ""
    if execucao.cliente_id:
        cliente = await db.get(ClienteModel, execucao.cliente_id)
        cliente_nome = cliente.nome if cliente else ""

    html = relatorio_execucao_para_html(
        execucao={
            "id": str(execucao.id),
            "criado_em": str(execucao.criado_em),
            "resultado_json": execucao.resultado_json,
        },
        analises=analises,
        cliente_nome=cliente_nome,
    )
    docx = await asyncio.to_thread(html_para_docx_bytes, html)
    nome = f"cwv-auditoria-{slugify_titulo(cliente_nome) if cliente_nome else str(execucao.criado_em)[:10]}"
    return StreamingResponse(
        io.BytesIO(docx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'},
    )
