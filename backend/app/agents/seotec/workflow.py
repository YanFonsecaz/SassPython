"""Workflow SEOTEC Onda 1+3: validar_pacote -> motor_regras -> analisar_ia ->
recomendar_ia -> health_score -> persistir.

Os nós de IA (Onda 3, SPEC_SEOTEC_Agentes_IA) rodam entre o motor de regras e
o health_score. Kill-switch: ``settings.seotec_ia_habilitada=False`` os nós
viram no-op (diagnóstico/recomendação vazios). Falha de LLM NÃO derruba a
auditoria (fail-open). Padrão do grafo: agents/cwv/workflow.py.
``persistir=False`` permite rodar o grafo puro em teste.
"""
import logging
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.config import settings
from app.services.seotec_checklist import carregar_checklist
from app.services.seotec_ingestao import validar_pacote
from app.services.seotec_motor import avaliar_pacote
from app.services.seotec_score import calcular_health_score

logger = logging.getLogger(__name__)


class EstadoSeotec(TypedDict, total=False):
    zip_bytes: bytes
    auditoria_id: str
    crawl_id: str
    usuario_id: str
    fase_destino: str
    persistir: bool
    pacote: Any            # PacoteIngestao
    faltantes: list[str]
    resultados: Any        # dict[str, ResultadoItem]
    diagnosticos: dict[str, str]
    pendentes_diagnostico: list[str]
    recomendacoes: dict[str, str]
    pendentes_recomendacao: list[str]
    sugestoes_ia: dict[str, list[dict]]
    score: Any             # ScoreResultado
    erro: str | None


def _exports_requeridos() -> set[str]:
    ck = carregar_checklist()
    return {i.regra.export for i in ck.itens() if i.fonte == "sf" and i.regra is not None}


async def node_validar_pacote(estado: EstadoSeotec) -> EstadoSeotec:
    r = validar_pacote(estado["zip_bytes"], exports_requeridos=_exports_requeridos())
    if r.pacote is None:
        return {**estado, "erro": "; ".join(r.erros) or "pacote inválido"}
    return {**estado, "pacote": r.pacote, "faltantes": r.faltantes, "erro": None}


async def node_motor_regras(estado: EstadoSeotec) -> EstadoSeotec:
    if estado.get("erro"):
        return estado
    ck = carregar_checklist()
    resultados = avaliar_pacote(ck, estado["pacote"], estado["faltantes"])
    return {**estado, "resultados": resultados}


def _derivar_site(estado: EstadoSeotec) -> dict:
    """Contexto do site para os agentes de IA (dominio + plataforma).

    Plataforma detectada via marcadores de URL do export `internal` (reusa
    `URL_SIGNATURES` do CWV). Fail-open: ``"geral"`` quando não detectável
    (a KB cai na recomendação canônica).
    """
    from app.services.seotec_plataforma import detectar_plataforma

    pacote = estado.get("pacote")
    dominio = getattr(pacote, "dominio", "") or ""
    plataforma = detectar_plataforma(pacote) if pacote is not None else "geral"
    return {"dominio": dominio, "plataforma": plataforma}


async def node_analisar_ia(estado: EstadoSeotec) -> EstadoSeotec:
    """SPEC_SEOTEC_Agentes_IA nó `analisar_ia`: diagnóstico LLM em lote."""
    if estado.get("erro"):
        return estado
    if not settings.seotec_ia_habilitada:
        return {**estado, "diagnosticos": {}, "pendentes_diagnostico": []}
    from app.agents.seotec.analisador import (
        SeotecAnalisadorAgent,
        montar_contexto_itens,
    )

    ck = carregar_checklist()
    itens_ctx = montar_contexto_itens(ck, estado["resultados"])
    if not itens_ctx:
        return {**estado, "diagnosticos": {}, "pendentes_diagnostico": []}
    site = _derivar_site(estado)
    agente = SeotecAnalisadorAgent(estado.get("usuario_id", ""))
    try:
        diagnosticos, pendentes = await agente.diagnosticar(itens_ctx, site)
    except Exception:
        logger.warning("SEOTEC analisar_ia falhou (fail-open)", exc_info=True)
        diagnosticos, pendentes = {}, [i["slug"] for i in itens_ctx]
    return {**estado, "diagnosticos": diagnosticos, "pendentes_diagnostico": pendentes}


async def node_recomendar_ia(estado: EstadoSeotec) -> EstadoSeotec:
    """SPEC_SEOTEC_Agentes_IA nó `recomendar_ia`: KB→LLM + sugestões amostra."""
    if estado.get("erro"):
        return estado
    if not settings.seotec_ia_habilitada:
        return {**estado, "recomendacoes": {}, "pendentes_recomendacao": [], "sugestoes_ia": {}}
    from app.agents.seotec.recomendador import (
        SeotecRecomendadorAgent,
        montar_contexto_recomendacao,
    )

    ck = carregar_checklist()
    resultados = estado["resultados"]
    itens_ctx = montar_contexto_recomendacao(ck, resultados)
    if not itens_ctx:
        return {**estado, "recomendacoes": {}, "pendentes_recomendacao": [], "sugestoes_ia": {}}
    site = _derivar_site(estado)
    agente = SeotecRecomendadorAgent(estado.get("usuario_id", ""))
    try:
        recomendacoes, pendentes = await agente.recomendar(itens_ctx, site["plataforma"])
    except Exception:
        logger.warning("SEOTEC recomendar_ia falhou (fail-open)", exc_info=True)
        recomendacoes, pendentes = {}, [i["slug"] for i in itens_ctx]

    sugestoes: dict[str, list[dict]] = {}
    itens_ri = [
        i for i in itens_ctx
        if i.get("recomendada_ia") and resultados[i["slug"]].status in ("reprovado", "atencao")
    ]
    if itens_ri:
        try:
            sugestoes = await agente.sugerir_amostra(itens_ri, site["plataforma"])
        except Exception:
            logger.warning("SEOTEC sugerir_amostra falhou (fail-open)", exc_info=True)
            sugestoes = {}
    return {
        **estado,
        "recomendacoes": recomendacoes,
        "pendentes_recomendacao": pendentes,
        "sugestoes_ia": sugestoes,
    }


async def node_health_score(estado: EstadoSeotec) -> EstadoSeotec:
    if estado.get("erro"):
        return estado
    ck = carregar_checklist()
    statuses = {slug: r.status for slug, r in estado["resultados"].items()}
    return {**estado, "score": calcular_health_score(ck, statuses)}


async def node_persistir(estado: EstadoSeotec) -> EstadoSeotec:
    if estado.get("erro") or not estado.get("persistir", True):
        return estado
    from app.db.session import async_session_factory
    from app.models.seo_auditoria import SeoAuditoria
    from app.models.seo_crawl import SeoCrawl
    from app.services.seotec_persistencia import persistir_resultados

    async with async_session_factory() as db:
        auditoria = await db.get(SeoAuditoria, estado["auditoria_id"])
        crawl = await db.get(SeoCrawl, estado["crawl_id"])
        await persistir_resultados(
            db, auditoria, crawl, estado["resultados"], estado["score"], estado["faltantes"],
            diagnosticos=estado.get("diagnosticos"),
            recomendacoes=estado.get("recomendacoes"),
            sugestoes_ia=estado.get("sugestoes_ia"),
        )
        if crawl.fase_destino == "after" and auditoria.fase != "concluida":
            auditoria.fase = "after"
        await db.commit()
    return estado


def construir_workflow():
    g = StateGraph(EstadoSeotec)
    g.add_node("validar_pacote", node_validar_pacote)
    g.add_node("motor_regras", node_motor_regras)
    g.add_node("analisar_ia", node_analisar_ia)
    g.add_node("recomendar_ia", node_recomendar_ia)
    g.add_node("health_score", node_health_score)
    g.add_node("persistir", node_persistir)
    g.set_entry_point("validar_pacote")
    g.add_edge("validar_pacote", "motor_regras")
    g.add_edge("motor_regras", "analisar_ia")
    g.add_edge("analisar_ia", "recomendar_ia")
    g.add_edge("recomendar_ia", "health_score")
    g.add_edge("health_score", "persistir")
    g.add_edge("persistir", END)
    return g.compile()


async def executar_auditoria_seotec(execucao_id: str, crawl_id: str) -> None:
    """Entrada do worker: carrega zip, roda grafo, billing + status da execução.

    Identificadores verificados contra o código real (divergem do brief em
    alguns pontos):
    - `ExecucaoFerramenta.status` usa os valores existentes no restante do
      código (`executando`, `concluida`, `falhou`) — não `concluido`.
    - `credito_service.liberar_reserva(db, usuario_id, quantidade)` e
      `confirmar_debito(db, usuario_id, reservado, quantidade, descricao,
      ferramenta=None, execucao_id=None)` batem exatamente com o brief.
    """
    from app.config import settings
    from app.db.session import async_session_factory
    from app.models.execucao_ferramenta import ExecucaoFerramenta
    from app.models.seo_crawl import SeoCrawl
    from app.services import credito_service
    from app.services.ferramenta_service import calcular_custo_seo_tecnico

    caminho = Path(settings.seotec_upload_dir) / f"{crawl_id}.zip"

    async with async_session_factory() as db:
        crawl = await db.get(SeoCrawl, crawl_id)
        execucao = await db.get(ExecucaoFerramenta, execucao_id)
        if crawl is None or execucao is None:
            logger.error(
                "SEOTEC: crawl ou execução inexistente execucao=%s crawl=%s",
                execucao_id, crawl_id,
            )
            erro_msg = "crawl ou execução inexistente"
            if execucao is not None:
                if crawl is not None:
                    fase_destino_orfa = crawl.fase_destino
                else:
                    fase_destino_orfa = (execucao.entrada_json or {}).get(
                        "fase_destino", "before"
                    )
                custo_orfa = calcular_custo_seo_tecnico(fase_destino_orfa)
                await credito_service.liberar_reserva(
                    db, str(execucao.usuario_id), custo_orfa
                )
                execucao.status = "falhou"
                execucao.erro_msg = erro_msg
            if crawl is not None:
                crawl.status = "erro"
                crawl.erro_msg = erro_msg
            await db.commit()
            caminho.unlink(missing_ok=True)
            return
        crawl.status = "processando"
        execucao.status = "executando"
        await db.commit()
        usuario_id = str(execucao.usuario_id)
        fase_destino = crawl.fase_destino
        auditoria_id = str(crawl.auditoria_id)

    custo = calcular_custo_seo_tecnico(fase_destino)
    try:
        zip_bytes = caminho.read_bytes()
        grafo = construir_workflow()
        estado = await grafo.ainvoke({
            "zip_bytes": zip_bytes,
            "auditoria_id": auditoria_id,
            "crawl_id": crawl_id,
            "usuario_id": usuario_id,
            "fase_destino": fase_destino,
            "persistir": True,
        })
        if estado.get("erro"):
            raise ValueError(estado["erro"])
    except Exception as exc:
        logger.exception("SEOTEC falhou execucao=%s crawl=%s", execucao_id, crawl_id)
        async with async_session_factory() as db:
            crawl = await db.get(SeoCrawl, crawl_id)
            execucao = await db.get(ExecucaoFerramenta, execucao_id)
            crawl.status = "erro"
            crawl.erro_msg = str(exc)[:500]
            execucao.status = "falhou"
            execucao.erro_msg = str(exc)[:500]
            await credito_service.liberar_reserva(db, usuario_id, custo)
            await db.commit()
        return
    finally:
        caminho.unlink(missing_ok=True)

    async with async_session_factory() as db:
        execucao = await db.get(ExecucaoFerramenta, execucao_id)
        execucao.status = "concluida"
        await credito_service.confirmar_debito(
            db, usuario_id, reservado=custo, quantidade=custo,
            descricao=f"Auditoria SEO Técnico ({fase_destino})",
            ferramenta="auditoria_seo_tecnico", execucao_id=execucao_id,
        )
        await db.commit()
