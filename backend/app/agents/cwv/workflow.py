import asyncio
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

SEMAFORO_PSI = asyncio.Semaphore(5)
SEMAFORO_LLM = asyncio.Semaphore(3)


ESTRATEGIAS_CWV = ("mobile", "desktop")


def _chave(url: str, estrategia: str) -> str:
    return f"{estrategia}\x00{url}"


class EstadoCWV(TypedDict):
    execucao_id: str
    usuario_id: str
    cliente_id: str
    jobs: list[tuple[str, str, str]]
    psi_resultados: dict[str, dict]
    plataformas: dict[str, str]
    problemas_por_url: dict[str, list[dict]]
    analises_persistidas: list[str]
    llm_stats_por_url: dict[str, dict]
    page_experience_por_origem: dict[str, dict]


def _log_prefix(eid: str) -> str:
    return f"[cwv eid={eid[:8]}]"


async def node_coletar_psi(estado: EstadoCWV) -> dict[str, Any]:
    import time

    from app.core.metrics import cwv_analise_duracao_seconds
    from app.core.workflow_events import publish_event
    from app.services.cwv_psi_client import PSIError, fetch_psi, parse_psi

    eid = estado["execucao_id"]
    jobs = estado["jobs"]
    total = len(jobs)
    await publish_event(eid, "node_start", "coletar_psi", f"Coletando metricas CWV para {total} URLs (mobile + desktop)...")

    async def coletar_uma(url: str, estrategia: str, idx: int, total: int) -> tuple[str, dict]:
        async with SEMAFORO_PSI:
            await publish_event(eid, "node_progress", "coletar_psi", f"Coletando PSI {idx}/{total}: {url[:60]} ({estrategia})")
            t0 = time.monotonic()
            try:
                payload = await fetch_psi(url, estrategia)
                parsed = parse_psi(payload)
                return url, {"ok": True, "payload": payload, "parsed": parsed, "estrategia": estrategia}
            except PSIError as e:
                return url, {"ok": False, "erro": str(e), "estrategia": estrategia}
            finally:
                cwv_analise_duracao_seconds.observe(time.monotonic() - t0)

    tarefas = [coletar_uma(url, estrategia, i + 1, total) for i, (_, url, estrategia) in enumerate(jobs)]
    resultados = await asyncio.gather(*tarefas)

    psi_dict: dict[str, dict] = {}
    n_ok = 0
    n_fail = 0
    for url, r in resultados:
        chave = _chave(url, r["estrategia"])
        psi_dict[chave] = r
        if r["ok"]:
            n_ok += 1
        else:
            n_fail += 1

    await publish_event(eid, "node_complete", "coletar_psi", f"PSI concluido: {n_ok} OK, {n_fail} falharam")
    return {"psi_resultados": psi_dict}


async def node_coletar_page_experience(estado: EstadoCWV) -> dict[str, Any]:
    """SPEC_CWV_Page_Experience: checagens por origem (HTTPS/SSL/redirect/headers/SB/mixed/mobile).

    DEVE rodar antes de ``node_detectar_plataformas`` (que remove o payload
    bruto do estado). Fail-open total: nenhuma exceção aqui derruba o workflow.
    """
    from app.core.workflow_events import publish_event
    from app.services.cwv_page_experience import _origem, auditar_origem

    eid = estado["execucao_id"]
    try:
        # Deriva origens únicas e agrupa payloads OK por origem.
        payloads_por_origem: dict[str, list[dict]] = {}
        for _, url, _estrategia in estado["jobs"]:
            chave = _chave(url, _estrategia)
            r = estado["psi_resultados"].get(chave, {})
            if r.get("ok") and r.get("payload"):
                origem = _origem(url)
                payloads_por_origem.setdefault(origem, []).append(r["payload"])

        origens = list(payloads_por_origem.keys())
        await publish_event(
            eid, "node_start", "coletar_page_experience",
            f"Verificando page experience de {len(origens)} origem(ns)...",
        )

        async def _auditar(o: str) -> tuple[str, dict]:
            return o, await auditar_origem(o, payloads_por_origem[o])

        try:
            resultados = await asyncio.wait_for(
                asyncio.gather(*[_auditar(o) for o in origens], return_exceptions=True),
                timeout=90,
            )
        except TimeoutError:
            logger.warning("%s page_experience excedeu budget de 90s", _log_prefix(eid))
            resultados = [(o, _vereditos_erro()) for o in origens]

        page_experience_por_origem: dict[str, dict] = {}
        n_pass = n_fail = n_erro = 0
        for res in resultados:
            if isinstance(res, Exception):
                logger.warning("%s page_experience origem falhou: %s", _log_prefix(eid), res)
                continue
            o, resultado = res
            page_experience_por_origem[o] = resultado
            for v in (resultado.get("https"), resultado.get("ssl"), resultado.get("redirect_301"),
                      resultado.get("security_headers"), resultado.get("safe_browsing"),
                      resultado.get("mixed_content"), resultado.get("mobile_friendly")):
                if v == "pass":
                    n_pass += 1
                elif v == "fail":
                    n_fail += 1
                elif v == "erro":
                    n_erro += 1

        await publish_event(
            eid, "node_complete", "coletar_page_experience",
            f"Page experience: {n_pass} pass / {n_fail} fail / {n_erro} erro",
        )
        return {"page_experience_por_origem": page_experience_por_origem}
    except Exception:
        logger.exception("%s node_coletar_page_experience falhou (fail-open)", _log_prefix(eid))
        await publish_event(eid, "node_complete", "coletar_page_experience", "Page experience: indisponível")
        return {"page_experience_por_origem": {}}


def _vereditos_erro() -> dict:
    return {
        "https": "erro", "ssl": "erro", "redirect_301": "erro",
        "security_headers": "erro", "safe_browsing": "erro",
        "mixed_content": "erro", "mobile_friendly": "erro",
        "detalhes": {"erro": "timeout do nó"},
    }


async def node_detectar_plataformas(estado: EstadoCWV) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    from app.services.cwv_plataforma import detectar_plataforma

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "detectar_plataformas", "Detectando plataformas...")

    plataformas: dict[str, str] = {}
    psi_sem_payload: dict[str, dict] = {}
    for _, url, estrategia in estado["jobs"]:
        chave = _chave(url, estrategia)
        r = estado["psi_resultados"].get(chave, {})
        if r.get("ok"):
            plataformas[chave] = detectar_plataforma(r["payload"])
        else:
            plataformas[chave] = "desconhecida"
        psi_sem_payload[chave] = {k: v for k, v in r.items() if k != "payload"}

    contagem: dict[str, int] = {}
    for p in plataformas.values():
        contagem[p] = contagem.get(p, 0) + 1
    await publish_event(eid, "node_complete", "detectar_plataformas", f"Plataformas: {contagem}")
    return {"plataformas": plataformas, "psi_resultados": psi_sem_payload}


async def node_analisar_seo(estado: EstadoCWV) -> dict[str, Any]:
    from app.agents.cwv.analisador import CWVAnalisadorAgent
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    agente = CWVAnalisadorAgent(estado["usuario_id"])
    problemas_por_url: dict[str, list[dict]] = {}
    llm_stats_por_url: dict[str, dict] = {}

    jobs_to_analyze = []
    for template, url, estrategia in estado["jobs"]:
        chave = _chave(url, estrategia)
        r = estado["psi_resultados"].get(chave, {})
        if r.get("ok"):
            jobs_to_analyze.append((template, url, estrategia))

    total = len(jobs_to_analyze)
    await publish_event(eid, "node_start", "analisar_seo", f"Analisando {total} URLs com sucesso...")

    async def analisar_uma(template: str, url: str, estrategia: str, idx: int) -> tuple[str, list[dict], dict]:
        async with SEMAFORO_LLM:
            chave = _chave(url, estrategia)
            r = estado["psi_resultados"][chave]
            await publish_event(eid, "node_progress", "analisar_seo", f"Analisando {idx}/{total}: {url[:60]} ({estrategia})")
            problemas, stats = await agente.analisar(
                audits_falhos=r["parsed"]["audits_falhos"],
                plataforma=estado["plataformas"][chave],
                metricas=r["parsed"],
            )
            return chave, problemas, stats

    if jobs_to_analyze:
        resultados = await asyncio.gather(*[analisar_uma(t, u, e, i + 1) for i, (t, u, e) in enumerate(jobs_to_analyze)])
        for chave, probs, stats in resultados:
            problemas_por_url[chave] = probs
            llm_stats_por_url[chave] = stats

    total_problemas = sum(len(p) for p in problemas_por_url.values())
    await publish_event(eid, "node_complete", "analisar_seo", f"{total_problemas} problemas identificados em {total} URLs")
    return {"problemas_por_url": problemas_por_url, "llm_stats_por_url": llm_stats_por_url}


async def node_documentar(estado: EstadoCWV) -> dict[str, Any]:
    from app.agents.cwv.documentador import CWVDocumentadorAgent
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    agente = CWVDocumentadorAgent()
    novo: dict[str, list[dict]] = {}

    urls_com_problemas = [(chave, probs) for chave, probs in estado["problemas_por_url"].items() if probs]
    total = len(urls_com_problemas)
    await publish_event(eid, "node_start", "documentar", f"Documentando problemas em {total} URLs...")

    async def doc_uma(chave: str, problemas: list[dict], idx: int) -> tuple[str, list[dict]]:
        await publish_event(eid, "node_progress", "documentar", f"Documentando {idx}/{total}: {_chave_label(chave)}")
        documentados = await agente.documentar(
            problemas=problemas,
            plataforma=estado["plataformas"].get(chave, "outros"),
        )
        return chave, documentados

    if urls_com_problemas:
        resultados = await asyncio.gather(
            *[doc_uma(chave, probs, i + 1) for i, (chave, probs) in enumerate(urls_com_problemas)]
        )
        for chave, docs in resultados:
            novo[chave] = docs

    for chave, probs in estado["problemas_por_url"].items():
        if chave not in novo:
            novo[chave] = probs

    total_docs = sum(len(d) for d in novo.values())
    await publish_event(eid, "node_complete", "documentar", f"{total_docs} problemas documentados")
    return {"problemas_por_url": novo}


def _chave_label(chave: str) -> str:
    parts = chave.split("\x00", 1)
    if len(parts) == 2:
        return f"{parts[1][:60]} ({parts[0]})"
    return chave[:80]


async def node_pesquisar_outros(estado: EstadoCWV) -> dict[str, Any]:
    from app.agents.cwv.pesquisador import CWVPesquisadorAgent
    from app.core.metrics import cwv_pesquisador_invocacoes
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    usuario_id = estado["usuario_id"]

    tarefas: list[tuple[str, dict, str]] = []
    agentes: dict[str, CWVPesquisadorAgent] = {}
    for chave, problemas in estado["problemas_por_url"].items():
        sem_kb = [p for p in problemas if p.get("kb_codigo") is None][:settings.cwv_pesquisador_max_por_analise]
        if not sem_kb:
            continue
        plataforma = estado["plataformas"].get(chave, "outros")
        if plataforma not in agentes:
            agentes[plataforma] = CWVPesquisadorAgent(usuario_id=usuario_id, plataforma=plataforma)
        for p in sem_kb:
            tarefas.append((chave, p, plataforma))

    if tarefas:
        cwv_pesquisador_invocacoes.inc(len(tarefas))
        await publish_event(eid, "node_start", "pesquisar_outros", f"Pesquisando {len(tarefas)} problemas residuais em paralelo...")

    async def _pesquisar_um(_chave: str, p: dict, plataforma: str) -> int:
        async with SEMAFORO_LLM:
            ctx = p.get("contexto_especifico", {})
            audit_dict = {
                "id": p.get("audit_id") or ctx.get("audit_id"),
                "title": ctx.get("title"),
                "description": ctx.get("description"),
                "displayValue": ctx.get("display_value"),
                "savings_ms": ctx.get("savings_ms"),
                "savings_bytes": ctx.get("savings_bytes"),
            }
            try:
                nova_doc = await agentes[plataforma].documentar(audit=audit_dict, plataforma=plataforma)
                if nova_doc:
                    p["documentacao_md"] = nova_doc
                    p["pesquisado"] = True
                    return 1
            except Exception as e:
                logger.warning("Pesquisador falhou para audit %s: %s", ctx.get("audit_id"), e)
            return 0

    if tarefas:
        resultados = await asyncio.gather(*[_pesquisar_um(c, p, pl) for c, p, pl in tarefas])
        total_pesquisas = sum(resultados)
    else:
        total_pesquisas = 0

    await publish_event(eid, "node_complete", "pesquisar_outros", f"{total_pesquisas} problemas pesquisados")
    return {"problemas_por_url": estado["problemas_por_url"]}


async def node_priorizar(estado: EstadoCWV) -> dict[str, Any]:
    from app.agents.cwv.priorizador import priorizar_problemas
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "priorizar", "Priorizando problemas...")

    novo: dict[str, list[dict]] = {}
    for chave, problemas in estado["problemas_por_url"].items():
        parsed = estado["psi_resultados"].get(chave, {}).get("parsed")
        novo[chave] = priorizar_problemas(problemas, metricas=parsed)

    total = sum(len(p) for p in novo.values())
    await publish_event(eid, "node_complete", "priorizar", f"{total} problemas priorizados")
    return {"problemas_por_url": novo}


async def node_persistir(estado: EstadoCWV) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    from app.services.cwv_persistencia import persistir_analise

    eid = estado["execucao_id"]
    total = len(estado["jobs"])
    await publish_event(eid, "node_start", "persistir", f"Salvando analises ({total} URLs × 2 estrategias)...")

    from app.core.metrics import cwv_problemas_por_analise

    analises_ids: list[str] = []
    llm_stats = estado.get("llm_stats_por_url", {})
    async with async_session_factory() as session:
        for template, url, estrategia in estado["jobs"]:
            chave = _chave(url, estrategia)
            r = estado["psi_resultados"].get(chave, {"ok": False, "erro": "nao coletado"})
            problemas_url = estado["problemas_por_url"].get(chave, [])
            analise_id = await persistir_analise(
                session,
                execucao_id=eid,
                cliente_id=estado["cliente_id"],
                usuario_id=estado["usuario_id"],
                url=url,
                template=template,
                estrategia=estrategia,
                plataforma=estado["plataformas"].get(chave, "desconhecida"),
                psi_resultado=r,
                problemas=problemas_url,
                llm_stats=llm_stats.get(chave),
            )
            analises_ids.append(analise_id)
            if r.get("ok"):
                cwv_problemas_por_analise.observe(len(problemas_url))

        # SPEC_CWV_Page_Experience: grava checagens por origem (mesma sessão/commit).
        from app.services.cwv_persistencia import persistir_page_experience
        for origem, resultado in estado.get("page_experience_por_origem", {}).items():
            try:
                await persistir_page_experience(
                    session, execucao_id=eid, origem=origem, resultado=resultado,
                )
            except Exception:
                logger.warning("%s persistir_page_experience falhou para %s", _log_prefix(eid), origem, exc_info=True)

        await session.commit()

    await publish_event(eid, "node_complete", "persistir", f"{len(analises_ids)} analises persistidas")
    return {"analises_persistidas": analises_ids}


def construir_workflow():
    g = StateGraph(EstadoCWV)
    g.add_node("coletar_psi", node_coletar_psi)
    g.add_node("coletar_page_experience", node_coletar_page_experience)
    g.add_node("detectar_plataformas", node_detectar_plataformas)
    g.add_node("analisar_seo", node_analisar_seo)
    g.add_node("documentar", node_documentar)
    g.add_node("pesquisar_outros", node_pesquisar_outros)
    g.add_node("priorizar", node_priorizar)
    g.add_node("persistir", node_persistir)
    g.set_entry_point("coletar_psi")
    g.add_edge("coletar_psi", "coletar_page_experience")
    g.add_edge("coletar_page_experience", "detectar_plataformas")
    g.add_edge("detectar_plataformas", "analisar_seo")
    g.add_edge("analisar_seo", "documentar")
    g.add_edge("documentar", "pesquisar_outros")
    g.add_edge("pesquisar_outros", "priorizar")
    g.add_edge("priorizar", "persistir")
    g.add_edge("persistir", END)
    return g.compile()


async def executar_workflow_cwv(execucao_id: str, ctx: dict[str, Any] | None = None):
    from datetime import UTC, datetime

    from app.services import credito_service, ferramenta_service

    logger.info("%s Iniciando workflow CWV", _log_prefix(execucao_id))

    try:
        async with async_session_factory() as session:
            await ferramenta_service.atualizar_execucao(session, execucao_id, status="executando")
            await session.commit()

            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if not execucao:
                logger.error("%s Execucao nao encontrada", _log_prefix(execucao_id))
                return

            # SPEC 10: validar que cliente ainda existe (pode ter sido removido entre POST e worker)
            if execucao.cliente_id:
                from app.models.cliente import Cliente
                cliente = await session.get(Cliente, execucao.cliente_id)
                if cliente is None:
                    logger.error("%s Cliente %s removido durante execucao", _log_prefix(execucao_id), execucao.cliente_id)
                    reserva_cliente = ferramenta_service._obter_reserva_estimada("core_web_vitals", execucao)
                    await credito_service.liberar_reserva(
                        session, str(execucao.usuario_id), reserva_cliente
                    )
                    execucao.status = "falhou"
                    execucao.erro_msg = "Cliente foi removido apos o inicio da analise"
                    execucao.resultado_json = {"motivo_falha": "cliente_removido"}
                    execucao.concluida_em = datetime.now(UTC)
                    await session.commit()
                    return

            entrada = execucao.entrada_json

        from app.schemas.cwv import UrlsPorTemplate

        urls_por_template_raw = entrada.get("urls_por_template", {})
        try:
            urls_obj = UrlsPorTemplate(**urls_por_template_raw)
        except Exception as e:
            logger.error("%s Entrada invalida: %s", _log_prefix(execucao_id), e)
            async with async_session_factory() as session:
                await ferramenta_service.finalizar_falha(session, execucao_id, f"Entrada invalida: {e}", ferramenta="core_web_vitals")
                exec_ref = await ferramenta_service.buscar_execucao(session, execucao_id)
                if exec_ref:
                    exec_ref.resultado_json = {**(exec_ref.resultado_json or {}), "motivo_falha": "erro_interno"}
                await session.commit()
            return

        urls_flat = urls_obj.itens()
        jobs = []
        for template, url in urls_flat:
            for estrategia in ESTRATEGIAS_CWV:
                jobs.append((template, url, estrategia))

        estado_inicial: EstadoCWV = {
            "execucao_id": execucao_id,
            "usuario_id": str(execucao.usuario_id),
            "cliente_id": str(execucao.cliente_id) if execucao.cliente_id else "",
            "jobs": jobs,
            "psi_resultados": {},
            "plataformas": {},
            "problemas_por_url": {},
            "analises_persistidas": [],
            "llm_stats_por_url": {},
            "page_experience_por_origem": {},
        }

        workflow = construir_workflow()

        await asyncio.wait_for(
            _run_workflow_cwv(workflow, estado_inicial, None, execucao_id),
            timeout=settings.cwv_workflow_timeout,
        )

    except asyncio.CancelledError:
        logger.info("%s Workflow CWV cancelado", _log_prefix(execucao_id))
        async with async_session_factory() as session:
            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if execucao and execucao.status in ("executando", "enfileirado", "pendente"):
                reserva = ferramenta_service._obter_reserva_estimada("core_web_vitals", execucao)
                if reserva > 0:
                    await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
                await ferramenta_service.atualizar_execucao(
                    session, execucao_id, status="cancelada", creditos_cobrados=0,
                )
                exec_ref = await ferramenta_service.buscar_execucao(session, execucao_id)
                if exec_ref:
                    exec_ref.resultado_json = {**(exec_ref.resultado_json or {}), "motivo_falha": "cancelada"}
                await session.commit()
        raise

    except TimeoutError:
        logger.error("%s Workflow CWV excedeu timeout", _log_prefix(execucao_id))
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Workflow excedeu o tempo limite", ferramenta="core_web_vitals")
            exec_ref = await ferramenta_service.buscar_execucao(session, execucao_id)
            if exec_ref:
                exec_ref.resultado_json = {**(exec_ref.resultado_json or {}), "motivo_falha": "timeout"}
            await session.commit()

    except Exception:
        logger.exception("%s Workflow CWV falhou", _log_prefix(execucao_id))
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Erro interno do workflow CWV", ferramenta="core_web_vitals")
            exec_ref = await ferramenta_service.buscar_execucao(session, execucao_id)
            if exec_ref:
                exec_ref.resultado_json = {**(exec_ref.resultado_json or {}), "motivo_falha": "erro_interno"}
            await session.commit()


async def _run_workflow_cwv(workflow, estado_inicial, config, execucao_id: str):
    from datetime import UTC, datetime

    from app.services import credito_service, ferramenta_service

    estado_final = await workflow.ainvoke(estado_inicial, config=config)

    async with async_session_factory() as session:
        execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
        if not execucao or execucao.status != "executando":
            return

        reserva = ferramenta_service._obter_reserva_estimada("core_web_vitals", execucao)

        analises_ids = []
        if estado_final:
            analises_ids = estado_final.get("analises_persistidas", [])

        n_sucesso = 0
        n_total_jobs = len(estado_final.get("jobs", [])) if estado_final else 0
        if estado_final:
            for _chave_j, r in estado_final.get("psi_resultados", {}).items():
                if r.get("ok"):
                    n_sucesso += 1

        custo_base = ferramenta_service.CUSTO_BASE_CWV

        # SPEC 10 Cenário #6: PSI falhou em TODAS as URLs → não cobra base, libera reserva
        if n_sucesso == 0 and n_total_jobs > 0:
            await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
            execucao.status = "falhou"
            execucao.creditos_cobrados = 0
            execucao.erro_msg = "Nenhuma URL pode ser analisada (PSI indisponivel ou todas as URLs invalidas)"
            execucao.resultado_json = {
                "n_urls_analisadas": 0,
                "n_urls_falharam": n_total_jobs,
                "analise_ids": analises_ids,
                "health_score": None,
                "motivo_falha": "psi_total",
            }
            execucao.concluida_em = datetime.now(UTC)
            await session.commit()
            logger.warning("%s CWV falhou: 0 URLs ok (de %d) — creditos liberados", _log_prefix(execucao_id), n_total_jobs)
            return

        custo = ferramenta_service.calcular_custo_cwv(n_sucesso)

        # SPEC_CWV_Health_Score: agrega proporção de audits saudáveis.
        # Roda dentro da mesma sessão/fluxo de billing existente — sem commits
        # extras nem alteração na ordem reserva→débito (aviso #2 da spec).
        health_score = await _computar_health_score(session, analises_ids)

        try:
            await credito_service.confirmar_debito(
                session,
                str(execucao.usuario_id),
                reservado=reserva,
                quantidade=custo,
                descricao=f"Core Web Vitals: {custo} creditos (base={custo_base}, urls={n_sucesso})",
                ferramenta="core_web_vitals",
                execucao_id=execucao_id,
            )
        except ValueError:
            await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
            execucao.status = "falhou"
            execucao.erro_msg = "Saldo insuficiente"
            execucao.resultado_json = {"motivo_falha": "saldo_insuficiente"}
            execucao.concluida_em = datetime.now(UTC)
            await session.commit()
            return

        resultado_json = {
            "n_urls_analisadas": n_sucesso,
            "n_urls_falharam": n_total_jobs - n_sucesso,
            "analise_ids": analises_ids,
            "health_score": health_score,
        }

        execucao.status = "concluida"
        execucao.creditos_cobrados = custo
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.now(UTC)
        await session.commit()
        logger.info("%s CWV concluida: %d URLs, custo=%d creditos", _log_prefix(execucao_id), n_sucesso, custo)


async def _computar_health_score(session, analise_ids: list[str]) -> dict | None:
    """Busca análises persistidas + contagens de problemas e calcula o health.

    Espelha ``cwv_health.calcular_health_score`` sobre dados do banco. Retorna
    ``None`` se não houver análises de sucesso com audits.
    """
    if not analise_ids:
        return None
    from sqlalchemy import select

    from app.models.cwv_analise import CwvAnalise
    from app.services.cwv_health import calcular_health_score
    from app.services.cwv_persistencia import contar_problemas_por_analise

    resultado = await session.execute(
        select(CwvAnalise.id, CwvAnalise.status, CwvAnalise.estrategia, CwvAnalise.audits_totais)
        .where(CwvAnalise.id.in_(analise_ids))
    )
    contagens = await contar_problemas_por_analise(session, analise_ids)
    analises = [
        {
            "status": str(status),
            "estrategia": str(estrategia),
            "audits_totais": int(audits_totais or 0),
            "n_problemas": contagens.get(str(aid), 0),
        }
        for aid, status, estrategia, audits_totais in resultado.all()
    ]
    return calcular_health_score(analises)
