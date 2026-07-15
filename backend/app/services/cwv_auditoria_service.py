"""Service da auditoria CWV (SPEC_CWV_Auditoria_Ciclo_De_Vida).

Gera o checklist determinístico a partir de uma execução concluída: fails
(problemas agrupados por chave), passes (audits saudáveis mapeados na KB),
field data (crux_*) e page experience (pe_*). Snapshot no momento da criação.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.cwv_analise import CwvAnalise
from app.models.cwv_auditoria import CwvAuditoria
from app.models.cwv_checklist_item import CwvChecklistItem
from app.models.cwv_problema import CwvProblema

logger = logging.getLogger(__name__)

ORDEM_FASES = ("before", "aguardando_implementacao", "after", "concluida")

# Mapeamento item_codigo page-experience → coluna veredito em CwvPageExperience.
PE_CHECKS = [
    ("pe_https", "https", "HTTPS"),
    ("pe_ssl", "ssl", "SSL"),
    ("pe_mixed_content", "mixed_content", "Mixed content"),
    ("pe_redirect_301", "redirect_301", "Redirect 301"),
    ("pe_security_headers", "security_headers", "Headers de segurança"),
    ("pe_safe_browsing", "safe_browsing", "Safe Browsing"),
    ("pe_mobile_friendly", "mobile_friendly", "Mobile-friendly"),
]

_ESFORCO_ORDEM = {"baixo": 1, "medio": 2, "alto": 3}


def chave_problema(p) -> str:
    """Chave canônica de problema para dedup (mesma regra do comparador/S3).

    Aceita dict (serializado) ou objeto ORM (CwvProblema).
    """
    kb = p.get("kb_codigo") if isinstance(p, dict) else p.kb_codigo
    audit = p.get("audit_id") if isinstance(p, dict) else p.audit_id
    titulo = p.get("titulo") if isinstance(p, dict) else p.titulo
    if kb:
        return kb
    if audit:
        return f"audit:{audit}"
    return f"titulo:{titulo}"


def avancar_fase(auditoria: CwvAuditoria, nova_fase: str) -> None:
    """Valida a ordem linear de fases. Levanta ValueError se inválida."""
    if nova_fase not in ORDEM_FASES:
        raise ValueError(f"Fase inválida: {nova_fase}")
    atual_idx = ORDEM_FASES.index(auditoria.fase)
    nova_idx = ORDEM_FASES.index(nova_fase)
    if nova_idx != atual_idx + 1:
        raise ValueError(
            f"Transição inválida: '{auditoria.fase}' → '{nova_fase}'. "
            f"Próxima fase esperada: '{ORDEM_FASES[atual_idx + 1] if atual_idx + 1 < len(ORDEM_FASES) else '—'}'."
        )
    auditoria.fase = nova_fase


async def gerar_checklist(session, auditoria: CwvAuditoria, execucao_id: str) -> list[CwvChecklistItem]:
    """Gera o checklist determinístico a partir da execução.

    1. Fails — problemas agrupados por chave (1 item por grupo, escopo = URLs).
    2. Passes — audits saudáveis (score ≥ 0.9) mapeados na KB, não-falhos.
    3. Field data — crux_lcp/inp/cls (pass=FAST, fail=AVERAGE/SLOW, na=sem).
    4. Page experience — pior veredito entre origens (omitido se tabela vazia).
    """
    from app.services.cwv_kb import buscar_entrada, mapeamento_audit_kb_com_aliases

    # Carrega análises de sucesso + problemas da execução.
    analises_result = await session.execute(
        select(CwvAnalise).where(
            CwvAnalise.execucao_id == execucao_id,
            CwvAnalise.status == "sucesso",
        )
    )
    analises = list(analises_result.scalars().all())
    if not analises:
        return []

    probs_result = await session.execute(
        select(CwvProblema).where(CwvProblema.analise_id.in_([a.id for a in analises]))
    )
    todos_problemas = list(probs_result.scalars().all())

    itens: list[CwvChecklistItem] = []

    # 1. Fails — agrupar por chave canônica.
    grupos: dict[str, list] = {}
    escopo_urls_por_chave: dict[str, set] = {}
    for p in todos_problemas:
        ch = chave_problema(p)
        grupos.setdefault(ch, []).append(p)
        # URL da análise de origem.
        analise_origem = next((a for a in analises if a.id == p.analise_id), None)
        if analise_origem:
            escopo_urls_por_chave.setdefault(ch, set()).add(analise_origem.url_canonica)

    chaves_fail = set(grupos.keys())
    grupos_ordenados = sorted(
        grupos.items(),
        key=lambda kv: min(p.prioridade_ordem for p in kv[1]),
    )

    for prioridade, (ch, probs_grupo) in enumerate(grupos_ordenados, start=1):
        primeiro = probs_grupo[0]
        # Esforço = max do grupo.
        esforcos = [p.esforco for p in probs_grupo if p.esforco]
        esforco = max(esforcos, key=lambda e: _ESFORCO_ORDEM.get(e, 0)) if esforcos else None
        urls = sorted(escopo_urls_por_chave.get(ch, set()))
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria.id,
            origem="psi_audit",
            item_codigo=ch,
            titulo=primeiro.titulo,
            status_before="fail",
            prioridade=prioridade,
            esforco=esforco,
            escopo_json={"urls": urls},
        ))

    # 2. Passes — audits saudáveis mapeados na KB, não-falhos.
    audit_para_kb = mapeamento_audit_kb_com_aliases()
    chaves_kb_fail = {ch for ch in chaves_fail if not ch.startswith("audit:") and not ch.startswith("titulo:")}
    audits_saudaveis: set[str] = set()
    for a in analises:
        resumo = a.raw_resumo_json or {}
        score_map = resumo.get("audits_score_map") or {}
        for audit_id, score in score_map.items():
            if score is not None and score >= 0.9 and audit_id in audit_para_kb:
                kb_codigo = audit_para_kb[audit_id]
                if kb_codigo not in chaves_kb_fail:
                    audits_saudaveis.add(kb_codigo)

    for kb_codigo in sorted(audits_saudaveis):
        entrada = buscar_entrada(kb_codigo)
        titulo = entrada.get("titulo", kb_codigo) if entrada else kb_codigo
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria.id,
            origem="psi_audit",
            item_codigo=kb_codigo,
            titulo=titulo,
            status_before="pass",
            prioridade=0,
        ))

    # 3. Field data — crux_lcp/inp/cls.
    for codigo, campo_categoria in [
        ("crux_lcp", "crux_lcp_categoria"),
        ("crux_inp", "crux_inp_categoria"),
        ("crux_cls", "crux_cls_categoria"),
    ]:
        categorias = [getattr(a, campo_categoria) for a in analises if getattr(a, campo_categoria)]
        if not categorias:
            status = "na"
        elif all(c == "FAST" for c in categorias):
            status = "pass"
        else:
            status = "fail"
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria.id,
            origem="field_data",
            item_codigo=codigo,
            titulo=f"Dado de campo — {codigo.split('_')[1].upper()}",
            status_before=status,
            prioridade=0 if status == "pass" else len(grupos_ordenados) + 1,
        ))

    # 4. Page experience — pior veredito entre origens (tolerante à ausência).
    try:
        itens.extend(await _itens_page_experience(session, execucao_id, auditoria.id))
    except Exception:
        logger.warning("gerar_checklist: page_experience indisponível para exec %s", execucao_id, exc_info=True)

    # Persiste todos (UNIQUE (auditoria_id, item_codigo) já garante dedup).
    for item in itens:
        session.add(item)
    await session.flush()
    return itens


async def _itens_page_experience(session, execucao_id: str, auditoria_id) -> list[CwvChecklistItem]:
    """Itens de page experience — pior veredito entre origens."""
    try:
        from app.models.cwv_page_experience import CwvPageExperience
    except ImportError:
        return []

    result = await session.execute(
        select(CwvPageExperience).where(CwvPageExperience.execucao_id == execucao_id)
    )
    rows = list(result.scalars().all())
    if not rows:
        return []

    def pior_veredito(valores: list[str]) -> str:
        # fail > (erro|na) > pass
        if any(v == "fail" for v in valores):
            return "fail"
        if any(v in ("erro", "na") for v in valores):
            return "na"
        return "pass"

    itens = []
    for codigo, coluna, titulo in PE_CHECKS:
        vereditos = [getattr(r, coluna) for r in rows if getattr(r, coluna)]
        if not vereditos:
            continue
        status = pior_veredito(vereditos)
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria_id,
            origem="page_experience",
            item_codigo=codigo,
            titulo=titulo,
            status_before=status,
            prioridade=0 if status == "pass" else 999,
        ))
    return itens


async def criar_auditoria(
    session,
    *,
    usuario_id: str,
    cliente_id: str,
    execucao_id: str,
    titulo: str | None = None,
) -> CwvAuditoria:
    """Cria a auditoria + gera o checklist na mesma transação."""
    from app.models.execucao_ferramenta import ExecucaoFerramenta

    # Copia health_score_before do resultado_json da execução.
    exec_result = await session.execute(
        select(ExecucaoFerramenta).where(ExecucaoFerramenta.id == execucao_id)
    )
    execucao = exec_result.scalar_one_or_none()
    health_before = None
    if execucao and execucao.resultado_json:
        hs = execucao.resultado_json.get("health_score")
        if isinstance(hs, dict) and hs.get("health_score") is not None:
            health_before = hs["health_score"]

    auditoria = CwvAuditoria(
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        titulo=titulo or f"Auditoria CWV — {datetime.now(UTC).strftime('%Y-%m-%d')}",
        fase="before",
        execucao_before_id=execucao_id,
        health_score_before=health_before,
    )
    session.add(auditoria)
    await session.flush()

    await gerar_checklist(session, auditoria, execucao_id)
    return auditoria


async def aplicar_resultado_after(session, auditoria_id: str, execucao_after_id: str) -> None:
    """SPEC_CWV_Reauditoria_After: aplica os resultados da execução after no checklist.

    Fail-open: se a auditoria não existe, retorna silenciosamente. Chamada pelo
    hook no final do workflow (nunca pode derrubar a execução).
    """
    aud_result = await session.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = aud_result.scalar_one_or_none()
    if not auditoria:
        return

    itens_result = await session.execute(
        select(CwvChecklistItem).where(CwvChecklistItem.auditoria_id == auditoria_id)
    )
    itens = list(itens_result.scalars().all())
    if not itens:
        return

    # Carrega problemas + análises da execução after.
    analises_after = await session.execute(
        select(CwvAnalise).where(
            CwvAnalise.execucao_id == execucao_after_id,
            CwvAnalise.status == "sucesso",
        )
    )
    analises_after = list(analises_after.scalars().all())

    problemas_after_result = await session.execute(
        select(CwvProblema).where(
            CwvProblema.analise_id.in_([a.id for a in analises_after])
        )
    )
    problemas_after = list(problemas_after_result.scalars().all())

    chaves_after = {chave_problema(p) for p in problemas_after}

    # Mapa de audits saudáveis (score >= 0.9) -> kb_codigo.
    from app.services.cwv_kb import mapeamento_audit_kb_com_aliases

    audit_para_kb = mapeamento_audit_kb_com_aliases()
    kb_saudaveis_after: set[str] = set()
    for a in analises_after:
        resumo = a.raw_resumo_json or {}
        score_map = resumo.get("audits_score_map") or {}
        for audit_id, score in score_map.items():
            if score is not None and score >= 0.9 and audit_id in audit_para_kb:
                kb_saudaveis_after.add(audit_para_kb[audit_id])

    # URLs que tiveram análise de sucesso no after.
    urls_com_sucesso_after = {a.url_canonica for a in analises_after}

    # Field data after.
    categorias_crux: dict[str, list[str]] = {"lcp": [], "inp": [], "cls": []}
    for a in analises_after:
        for chave, campo in [("lcp", "crux_lcp_categoria"), ("inp", "crux_inp_categoria"), ("cls", "crux_cls_categoria")]:
            val = getattr(a, campo)
            if val:
                categorias_crux[chave].append(val)

    # Page experience after.
    pe_vereditos_after: dict[str, list[str]] = {}
    try:
        from app.models.cwv_page_experience import CwvPageExperience

        pe_result = await session.execute(
            select(CwvPageExperience).where(CwvPageExperience.execucao_id == execucao_after_id)
        )
        for row in pe_result.scalars().all():
            for _, coluna, _ in PE_CHECKS:
                v = getattr(row, coluna)
                if v:
                    pe_vereditos_after.setdefault(coluna, []).append(v)
    except Exception:
        logger.warning("aplicar_resultado_after: page_experience indisponível", exc_info=True)

    n_pass = n_fail = 0
    for item in itens:
        escopo_urls = (item.escopo_json or {}).get("urls", [])

        if item.origem == "psi_audit":
            if item.item_codigo in chaves_after:
                item.status_after = "fail"
                n_fail += 1
            elif item.item_codigo in kb_saudaveis_after:
                item.status_after = "pass"
                n_pass += 1
            elif escopo_urls and all(u not in urls_com_sucesso_after for u in escopo_urls):
                # Todas as URLs do escopo falharam no PSI after → sem dado.
                item.status_after = "na"
            else:
                item.status_after = "pass"
                n_pass += 1

        elif item.origem == "field_data":
            # item_codigo = crux_lcp / crux_inp / crux_cls
            metrica = item.item_codigo.split("_")[1] if "_" in item.item_codigo else ""
            cats = categorias_crux.get(metrica, [])
            if not cats:
                item.status_after = "na"
            elif all(c == "FAST" for c in cats):
                item.status_after = "pass"
                n_pass += 1
            else:
                item.status_after = "fail"
                n_fail += 1

        elif item.origem == "page_experience":
            # item_codigo = pe_https, pe_ssl, etc.
            coluna = item.item_codigo.replace("pe_", "", 1)
            vereditos = pe_vereditos_after.get(coluna, [])
            if not vereditos:
                item.status_after = "na"
            elif any(v == "fail" for v in vereditos):
                item.status_after = "fail"
                n_fail += 1
            elif any(v in ("erro", "na") for v in vereditos):
                item.status_after = "na"
            else:
                item.status_after = "pass"
                n_pass += 1

    # Copia health_score_after.
    from app.models.execucao_ferramenta import ExecucaoFerramenta

    exec_result = await session.execute(
        select(ExecucaoFerramenta).where(ExecucaoFerramenta.id == execucao_after_id)
    )
    execucao_after = exec_result.scalar_one_or_none()
    if execucao_after and execucao_after.resultado_json:
        hs = execucao_after.resultado_json.get("health_score")
        if isinstance(hs, dict) and hs.get("health_score") is not None:
            auditoria.health_score_after = hs["health_score"]

    await session.flush()
    logger.info(
        "aplicar_resultado_after auditoria=%s: %d resolvidos, %d persistentes",
        auditoria_id, n_pass, n_fail,
    )

    # Evento SSE final (best-effort: falha de publish não pode impedir o commit).
    try:
        from app.core.workflow_events import publish_event

        await publish_event(
            execucao_after_id, "node_complete", "aplicar_after",
            f"Checklist atualizado: {n_pass} resolvidos, {n_fail} persistentes",
        )
    except Exception:
        logger.warning("aplicar_resultado_after: publish_event falhou", exc_info=True)
