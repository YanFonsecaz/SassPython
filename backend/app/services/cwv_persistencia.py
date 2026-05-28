import logging
from datetime import datetime

from sqlalchemy import case, func, select

from app.models.cwv_analise import CwvAnalise
from app.models.cwv_problema import CwvProblema
from app.services.cwv_psi_client import normalizar_url

logger = logging.getLogger(__name__)


async def persistir_analise(
    session,
    *,
    execucao_id: str,
    cliente_id: str,
    usuario_id: str,
    url: str,
    template: str,
    estrategia: str,
    plataforma: str,
    psi_resultado: dict,
    problemas: list[dict],
    llm_stats: dict | None = None,
) -> str:
    url_canonica = normalizar_url(url)
    llm_stats = llm_stats or {"llm_usado": False, "processados": 0, "descartados": 0}

    if not psi_resultado.get("ok"):
        analise = CwvAnalise(
            execucao_id=execucao_id,
            cliente_id=cliente_id,
            usuario_id=usuario_id,
            url=url,
            url_canonica=url_canonica,
            template_tipo=template,
            estrategia=estrategia,
            plataforma_detectada=plataforma,
            raw_psi_json={},
            status="falhou_psi",
            erro_msg=str(psi_resultado.get("erro", ""))[:500],
        )
        session.add(analise)
        await session.flush()
        return str(analise.id)

    parsed = psi_resultado.get("parsed", {})
    analise = CwvAnalise(
        execucao_id=execucao_id,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        url=url,
        url_canonica=url_canonica,
        template_tipo=template,
        estrategia=estrategia,
        plataforma_detectada=plataforma,
        score_performance=parsed.get("score_performance"),
        lcp_ms=parsed.get("lcp_ms"),
        cls=parsed.get("cls"),
        inp_ms=parsed.get("inp_ms"),
        fcp_ms=parsed.get("fcp_ms"),
        ttfb_ms=parsed.get("ttfb_ms"),
        tbt_ms=parsed.get("tbt_ms"),
        raw_psi_json=psi_resultado.get("payload", {}),
        status="sucesso",
        audits_totais=parsed.get("audits_totais", 0),
        n_network_requests=parsed.get("n_network_requests", 0),
        main_document_size_bytes=parsed.get("main_document_size_bytes", 0),
        llm_usado=bool(llm_stats.get("llm_usado", False)),
        llm_audits_processados=int(llm_stats.get("processados", 0)),
        llm_audits_descartados=int(llm_stats.get("descartados", 0)),
    )
    session.add(analise)
    await session.flush()
    analise_id = str(analise.id)

    for p in problemas:
        problema = CwvProblema(
            analise_id=analise.id,
            kb_codigo=p.get("kb_codigo"),
            audit_id=p.get("audit_id"),
            titulo=p.get("titulo", ""),
            severidade=p.get("severidade", 1),
            prioridade_ordem=p.get("prioridade_ordem", 0),
            metricas_afetadas=p.get("metricas_afetadas", []),
            contexto_especifico=p.get("contexto_especifico"),
            documentacao_md=p.get("documentacao_md", ""),
            pesquisado=bool(p.get("pesquisado", False)),
        )
        session.add(problema)

    await session.flush()
    return analise_id


async def buscar_analise_com_problemas(session, analise_id: str) -> dict | None:
    resultado = await session.execute(
        select(CwvAnalise).where(CwvAnalise.id == analise_id)
    )
    analise = resultado.scalar_one_or_none()
    if not analise:
        return None

    probs_result = await session.execute(
        select(CwvProblema)
        .where(CwvProblema.analise_id == analise_id)
        .order_by(CwvProblema.prioridade_ordem)
    )
    problemas = probs_result.scalars().all()

    return _analise_to_dict(analise, problemas)


async def buscar_historico_url(session, cliente_id: str, url_canonica: str) -> list[dict]:
    contagens = (
        select(
            CwvProblema.analise_id.label("analise_id"),
            func.count(CwvProblema.id).label("n_total"),
            func.coalesce(
                func.sum(case((CwvProblema.severidade >= 4, 1), else_=0)),
                0,
            ).label("n_alta"),
        )
        .group_by(CwvProblema.analise_id)
        .subquery()
    )

    resultado = await session.execute(
        select(
            CwvAnalise,
            func.coalesce(contagens.c.n_total, 0).label("n_total"),
            func.coalesce(contagens.c.n_alta, 0).label("n_alta"),
        )
        .outerjoin(contagens, contagens.c.analise_id == CwvAnalise.id)
        .where(
            CwvAnalise.cliente_id == cliente_id,
            CwvAnalise.url_canonica == url_canonica,
        )
        .order_by(CwvAnalise.criado_em.desc())
        .limit(30)
    )
    return [
        _analise_resumo(a, n_problemas=int(n_total), n_alta=int(n_alta))
        for a, n_total, n_alta in resultado.all()
    ]


async def buscar_ultima_analise_url(
    session, cliente_id: str, url_canonica: str
) -> CwvAnalise | None:
    resultado = await session.execute(
        select(CwvAnalise)
        .where(
            CwvAnalise.cliente_id == cliente_id,
            CwvAnalise.url_canonica == url_canonica,
        )
        .order_by(CwvAnalise.criado_em.desc())
        .limit(1)
    )
    return resultado.scalar_one_or_none()


async def listar_historico_cliente(session, cliente_id: str, template: str | None = None) -> list[dict]:
    base = select(
        CwvAnalise.url_canonica,
        CwvAnalise.template_tipo,
        CwvAnalise.plataforma_detectada,
        CwvAnalise.id,
        CwvAnalise.score_performance,
        CwvAnalise.lcp_ms,
        CwvAnalise.cls,
        CwvAnalise.inp_ms,
        CwvAnalise.criado_em,
    ).where(CwvAnalise.cliente_id == cliente_id)

    if template:
        base = base.where(CwvAnalise.template_tipo == template)

    subq = (
        base.order_by(CwvAnalise.criado_em.desc()).subquery()
    )

    resultados = await session.execute(
        select(
            subq.c.url_canonica,
            subq.c.template_tipo,
            subq.c.plataforma_detectada,
        ).distinct(subq.c.url_canonica)
    )

    urls = resultados.all()
    historico = []
    for url_row in urls:
        url_canonica = url_row[0]
        analises = await buscar_historico_url(session, cliente_id, url_canonica)
        if analises:
            historico.append({
                "url_canonica": url_canonica,
                "template_tipo": url_row[1],
                "plataforma_detectada": url_row[2],
                "analises": analises,
            })

    return historico


async def buscar_analise_por_id(session, analise_id: str) -> CwvAnalise | None:
    resultado = await session.execute(
        select(CwvAnalise).where(CwvAnalise.id == analise_id)
    )
    return resultado.scalar_one_or_none()


def _analise_to_dict(analise: CwvAnalise, problemas: list[CwvProblema]) -> dict:
    return {
        "id": str(analise.id),
        "cliente_id": str(analise.cliente_id),
        "usuario_id": str(analise.usuario_id),
        "url": analise.url,
        "url_canonica": analise.url_canonica,
        "template_tipo": analise.template_tipo,
        "plataforma_detectada": analise.plataforma_detectada,
        "estrategia": analise.estrategia,
        "score_performance": int(analise.score_performance) if analise.score_performance is not None else None,
        "lcp_ms": float(analise.lcp_ms) if analise.lcp_ms is not None else None,
        "cls": float(analise.cls) if analise.cls is not None else None,
        "inp_ms": float(analise.inp_ms) if analise.inp_ms is not None else None,
        "fcp_ms": float(analise.fcp_ms) if analise.fcp_ms is not None else None,
        "ttfb_ms": float(analise.ttfb_ms) if analise.ttfb_ms is not None else None,
        "tbt_ms": float(analise.tbt_ms) if analise.tbt_ms is not None else None,
        "status": analise.status,
        "erro_msg": analise.erro_msg,
        "criado_em": analise.criado_em.isoformat() if analise.criado_em else "",
        "audits_totais": analise.audits_totais,
        "n_network_requests": analise.n_network_requests,
        "main_document_size_bytes": analise.main_document_size_bytes,
        "llm_usado": analise.llm_usado,
        "llm_audits_processados": analise.llm_audits_processados,
        "llm_audits_descartados": analise.llm_audits_descartados,
        "problemas": [
            {
                "id": str(p.id),
                "kb_codigo": p.kb_codigo,
                "audit_id": p.audit_id,
                "titulo": p.titulo,
                "severidade": p.severidade,
                "prioridade_ordem": p.prioridade_ordem,
                "metricas_afetadas": p.metricas_afetadas,
                "contexto_especifico": p.contexto_especifico,
                "documentacao_md": p.documentacao_md,
                "pesquisado": p.pesquisado,
            }
            for p in problemas
        ],
    }


def _analise_resumo(a: CwvAnalise, *, n_problemas: int = 0, n_alta: int = 0) -> dict:
    return {
        "id": str(a.id),
        "url_canonica": a.url_canonica,
        "template_tipo": a.template_tipo,
        "score_performance": int(a.score_performance) if a.score_performance is not None else None,
        "lcp_ms": float(a.lcp_ms) if a.lcp_ms is not None else None,
        "cls": float(a.cls) if a.cls is not None else None,
        "inp_ms": float(a.inp_ms) if a.inp_ms is not None else None,
        "n_problemas": n_problemas,
        "n_problemas_alta_severidade": n_alta,
        "criado_em": a.criado_em.isoformat() if a.criado_em else "",
    }


async def buscar_problemas_analise(session, analise_id: str) -> list[CwvProblema]:
    resultado = await session.execute(
        select(CwvProblema)
        .where(CwvProblema.analise_id == analise_id)
        .order_by(CwvProblema.prioridade_ordem)
    )
    return list(resultado.scalars().all())


async def buscar_analise_anterior(
    session, url_canonica: str, cliente_id: str, antes_de: datetime
) -> CwvAnalise | None:
    """Retorna a análise imediatamente anterior à data dada para mesma URL+cliente."""
    from sqlalchemy import select
    
    resultado = await session.execute(
        select(CwvAnalise)
        .where(
            CwvAnalise.cliente_id == cliente_id,
            CwvAnalise.url_canonica == url_canonica,
            CwvAnalise.criado_em < antes_de,
            CwvAnalise.status == "sucesso",
        )
        .order_by(CwvAnalise.criado_em.desc())
        .limit(1)
    )
    return resultado.scalar_one_or_none()
