import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.cliente import Cliente
from app.models.usuario import Usuario
from app.schemas.cwv import (
    AnalisarRequest,
    AnaliseResposta,
    ComparacaoResposta,
    CustoCwvResponse,
    HistoricoListResponse,
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


@router.get("/core-web-vitals/execucao/{execucao_id}")
async def buscar_execucao_cwv(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from app.models.execucao_ferramenta import ExecucaoFerramenta

    resultado = await db.execute(
        select(ExecucaoFerramenta).where(
            ExecucaoFerramenta.id == execucao_id,
            ExecucaoFerramenta.usuario_id == usuario.id,
        )
    )
    execucao = resultado.scalar_one_or_none()
    if not execucao:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")

    return {
        "id": str(execucao.id),
        "ferramenta": execucao.ferramenta,
        "status": execucao.status,
        "etapa_atual": execucao.etapa_atual,
        "creditos_cobrados": execucao.creditos_cobrados,
        "resultado_json": execucao.resultado_json,
        "erro_msg": execucao.erro_msg,
        "criado_em": str(execucao.criado_em),
        "concluida_em": str(execucao.concluida_em) if execucao.concluida_em else None,
    }


@router.get("/core-web-vitals/analise/{analise_id}", response_model=AnaliseResposta)
async def buscar_analise_cwv(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.cwv_persistencia import buscar_analise_com_problemas

    analise = await buscar_analise_com_problemas(db, analise_id)
    if not analise or analise["usuario_id"] != str(usuario.id):
        raise HTTPException(status_code=404, detail="Analise nao encontrada")
    return analise


@router.get("/core-web-vitals/historico", response_model=HistoricoListResponse)
async def listar_historico_cwv(
    cliente_id: uuid.UUID,
    template: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    await _validar_cliente(db, str(usuario.id), str(cliente_id))

    from app.services.cwv_persistencia import listar_historico_cliente

    historico = await listar_historico_cliente(db, str(cliente_id), template=template)
    return {"urls": historico}


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
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_reanalisar", max_requests=3, window_seconds=300)),
) -> dict[str, Any]:
    from app.services.cwv_persistencia import buscar_analise_por_id

    analise = await buscar_analise_por_id(db, analise_id)
    if not analise or str(analise.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Analise nao encontrada")

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
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> ComparacaoResposta:

    from app.schemas.cwv import MetricaComparada, ProblemaComparado
    from app.services.cwv_persistencia import buscar_analise_anterior, buscar_analise_por_id

    # Buscar análise atual
    analise_atual = await buscar_analise_por_id(db, analise_id)
    if not analise_atual or str(analise_atual.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Analise nao encontrada")

    # Buscar problemas da análise atual
    from app.services.cwv_persistencia import buscar_problemas_analise
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
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.cwv_persistencia import buscar_analise_irma, buscar_analise_por_id

    analise = await buscar_analise_por_id(db, analise_id)
    if not analise or str(analise.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Analise nao encontrada")

    irma = await buscar_analise_irma(db, analise_id)
    if not irma:
        return {"existe": False, "analise": None}
    return {"existe": True, "analise": irma}


@router.patch("/core-web-vitals/analise/{analise_id}/plataforma")
async def override_plataforma_cwv(
    analise_id: str,
    body: PlataformaOverrideRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    """Permite usuario corrigir manualmente a plataforma detectada e regenera
    documentacao_md de todos os problemas com a nova plataforma."""
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    from app.models.cwv_problema import CwvProblema
    from app.services.cwv_kb import buscar_entrada
    from app.services.cwv_persistencia import buscar_analise_por_id

    analise = await buscar_analise_por_id(db, analise_id)
    if not analise or str(analise.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Analise nao encontrada")

    nova_plataforma = body.plataforma
    analise.plataforma_detectada = nova_plataforma

    probs_result = await db.execute(
        select(CwvProblema).where(CwvProblema.analise_id == analise_id)
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
    if not analise or str(analise.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Problema nao encontrado")

    prob_dict = {
        "titulo": prob.titulo,
        "severidade": prob.severidade,
        "metricas_afetadas": prob.metricas_afetadas,
        "contexto_especifico": prob.contexto_especifico,
        "documentacao_md": prob.documentacao_md,
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
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_export", max_requests=30, window_seconds=300)),
) -> StreamingResponse:
    from app.services import cwv_persistencia

    analise_dict = await cwv_persistencia.buscar_analise_com_problemas(db, analise_id)
    if not analise_dict or str(analise_dict.get("usuario_id")) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Analise nao encontrada")

    problemas = analise_dict.get("problemas", [])
    prob_dicts = [
        {
            "titulo": p["titulo"],
            "severidade": p["severidade"],
            "metricas_afetadas": p["metricas_afetadas"],
            "contexto_especifico": p["contexto_especifico"],
            "documentacao_md": p["documentacao_md"],
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
