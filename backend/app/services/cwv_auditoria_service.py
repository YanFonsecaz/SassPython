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

ITENS_MANUAIS = [
    ("manual_popups", "Pop-ups intrusivos"),
    ("manual_interstitials", "Interstitials intrusivos"),
    ("manual_ads_above_fold", "Anúncios intrusivos acima da dobra"),
]

# SPEC_CWV_Navegacao_Agentica: WebMCP não é automatizável sem render headless
# (registra tools em runtime via JS) — 3 checks manuais, default 'na'.
ITENS_MANUAIS_AGENTIC = [
    ("manual_webmcp_forms", "WebMCP: detecção de formulários"),
    ("manual_webmcp_tools", "WebMCP: ferramentas registradas"),
    ("manual_webmcp_schemas", "WebMCP: schemas válidos"),
]

# Limiar de acessibilidade (score da categoria accessibility do PSI).
_ACESSIBILIDADE_MIN = 0.9

# Descrições curtas para itens sem KB (field data, page experience, manuais e
# agênticos) — usadas na ficha (detalhe) com tem_kb=False.
# SPEC_CWV_Navegacao_Agentica / Checklist_Itens_Manuais / Page_Experience.
DESCRICOES_ITENS_SEM_KB = {
    # Field data (CrUX — usuários reais, p75 dos últimos 28 dias).
    "crux_lcp": "Dados reais de usuários (CrUX) para o LCP — tempo até o maior elemento visível terminar de carregar. p75 acima de 2,5s reprova. Como corrigir: otimize a imagem/hero principal (formato moderno, preload, CDN), reduza o tempo de resposta do servidor e elimine recursos que bloqueiam a renderização.",
    "crux_inp": "Dados reais de usuários (CrUX) para o INP — demora entre uma interação (clique/toque/tecla) e a resposta visual. p75 acima de 200ms reprova. Como corrigir: quebre tarefas longas de JavaScript, adie scripts de terceiros e simplifique handlers de eventos.",
    "crux_cls": "Dados reais de usuários (CrUX) para o CLS — o quanto o layout 'pula' durante o carregamento. p75 acima de 0,1 reprova. Como corrigir: reserve espaço fixo para imagens, anúncios e embeds (width/height) e evite fontes que trocam de tamanho ao carregar.",
    # Page Experience (checks por origem).
    "pe_https": "O site deve ser servido inteiramente via HTTPS. Falha indica conexão insegura ou erro de TLS ao acessar a origem. Como corrigir: instale um certificado válido e force HTTPS em todo o site.",
    "pe_ssl": "Certificado SSL válido, com cadeia confiável e sem expirar nos próximos 14 dias. Como corrigir: renove o certificado no provedor/CDN e confirme a cadeia completa (intermediários).",
    "pe_mixed_content": "Página HTTPS carregando recursos via http:// (mixed content) — navegadores bloqueiam ou marcam como inseguro. Como corrigir: troque URLs de imagens, scripts e estilos para https:// (ou URLs relativas).",
    "pe_redirect_301": "http:// deve redirecionar para https:// em um único salto com 301 (permanente). Cadeias longas ou 302 desperdiçam crawl budget e diluem sinais de ranqueamento. Como corrigir: configure o redirect no servidor/CDN, direto para a URL final.",
    "pe_security_headers": "Headers de segurança esperados: Strict-Transport-Security (HSTS), Content-Security-Policy ou X-Frame-Options, e X-Content-Type-Options: nosniff. Como corrigir: adicione os headers no servidor, CDN ou edge (ex.: Cloudflare/Nginx).",
    "pe_safe_browsing": "Verifica se a origem aparece nas listas do Google Safe Browsing (malware, phishing, software indesejado). n/a significa que a checagem não pôde rodar (sem chave de API configurada).",
    "pe_mobile_friendly": "Audit de viewport do Lighthouse mobile — a página deve se adaptar a telas pequenas (meta viewport correta, sem zoom bloqueado). Como corrigir: inclua <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> e valide o layout responsivo.",
    # Manuais (avaliação humana — planilha NPBR).
    "manual_popups": "Verifique manualmente se há pop-ups intrusivos cobrindo o conteúdo principal logo na entrada.",
    "manual_interstitials": "Verifique interstitials (telas cheias) que bloqueiam o acesso ao conteúdo, sobretudo no mobile.",
    "manual_ads_above_fold": "Verifique anúncios acima da dobra que empurram o conteúdo ou causam layout shift.",
    # Navegação agêntica.
    "agentic_llms_txt": "Arquivo /llms.txt em Markdown com cabeçalho H1, descrevendo o site para agentes de IA (padrão emergente de navegação agêntica).",
    "agentic_acessibilidade": "Árvore de acessibilidade bem estruturada — score de acessibilidade do Lighthouse ≥ 0.9. Base para navegação por agentes e leitores de tela.",
    "manual_webmcp_forms": "WebMCP: a página expõe formulários detectáveis por agentes (navigator.modelContext). Verificação manual — o registro ocorre em runtime via JS.",
    "manual_webmcp_tools": "WebMCP: ferramentas/ações registradas para agentes (registerTool). Verificação manual — registro em runtime.",
    "manual_webmcp_schemas": "WebMCP: schemas das ferramentas válidos, descrevendo entradas/saídas de forma que um agente consiga usar.",
}


def _pior_veredito(valores: list[str]) -> str:
    """Pior veredito entre origens: fail > (erro|na) > pass."""
    if any(v == "fail" for v in valores):
        return "fail"
    if any(v in ("erro", "na") for v in valores):
        return "na"
    return "pass"


_KB_NAO_CATALOGADO = "outros"


def chave_problema(p) -> str:
    """Chave canônica de problema para dedup (mesma regra do comparador/S3).

    Aceita dict (serializado) ou objeto ORM (CwvProblema).
    Trata ``kb_codigo='outros'`` como ``None`` — bucket genérico não identifica
    o problema (SPEC_CWV_Chave_Problema_Outros).
    """
    kb = p.get("kb_codigo") if isinstance(p, dict) else p.kb_codigo
    audit = p.get("audit_id") if isinstance(p, dict) else p.audit_id
    titulo = p.get("titulo") if isinstance(p, dict) else p.titulo
    if kb and kb != _KB_NAO_CATALOGADO:
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
        # Título: se chave é audit:* e título é genérico, humaniza o audit_id
        # (SPEC_CWV_Chave_Problema_Outros).
        titulo_item = primeiro.titulo
        if ch.startswith("audit:") and "não catalogado" in titulo_item.lower():
            audit_id = ch.split(":", 1)[1]
            titulo_item = audit_id.replace("-", " ").replace("_", " ").capitalize()

        # Esforço = max do grupo.
        esforcos = [p.esforco for p in probs_grupo if p.esforco]
        esforco = max(esforcos, key=lambda e: _ESFORCO_ORDEM.get(e, 0)) if esforcos else None
        urls = sorted(escopo_urls_por_chave.get(ch, set()))
        metricas_grupo = sorted({m for p in probs_grupo for m in (p.metricas_afetadas or [])})
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria.id,
            origem="psi_audit",
            item_codigo=ch,
            titulo=titulo_item,
            status_before="fail",
            prioridade=prioridade,
            esforco=esforco,
            escopo_json={"urls": urls},
            metricas_afetadas=metricas_grupo,
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
        metricas_kb = entrada.get("metricas_afetadas") or [] if entrada else []
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria.id,
            origem="psi_audit",
            item_codigo=kb_codigo,
            titulo=titulo,
            status_before="pass",
            prioridade=0,
            metricas_afetadas=metricas_kb,
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
            metricas_afetadas=[codigo.split("_")[1].upper()],
        ))

    # 4. Page experience — pior veredito entre origens (tolerante à ausência).
    try:
        itens.extend(await _itens_page_experience(session, execucao_id, auditoria.id))
    except Exception:
        logger.warning("gerar_checklist: page_experience indisponível para exec %s", execucao_id, exc_info=True)

    # 5. Itens manuais — SPEC_CWV_Checklist_Itens_Manuais (avaliação humana).
    for codigo, titulo in ITENS_MANUAIS:
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria.id,
            origem="page_experience",
            item_codigo=codigo,
            titulo=titulo,
            status_before="na",
            prioridade=0,
        ))

    # 6. Navegação agêntica — SPEC_CWV_Navegacao_Agentica (llms.txt + a11y + WebMCP).
    itens.extend(await _itens_agentic(session, execucao_id, auditoria.id, analises))

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

    itens = []
    for codigo, coluna, titulo in PE_CHECKS:
        vereditos = [getattr(r, coluna) for r in rows if getattr(r, coluna)]
        if not vereditos:
            continue
        status = _pior_veredito(vereditos)
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria_id,
            origem="page_experience",
            item_codigo=codigo,
            titulo=titulo,
            status_before=status,
            prioridade=0 if status == "pass" else 999,
        ))
    return itens


async def _itens_agentic(
    session, execucao_id: str, auditoria_id, analises: list
) -> list[CwvChecklistItem]:
    """Grupo 'Navegação agêntica' (SPEC_CWV_Navegacao_Agentica):

    - ``agentic_llms_txt``: pior veredito da coluna ``llms_txt`` entre origens
      (mesmo padrão dos ``pe_*``; omitido se não houver page_experience);
    - ``agentic_acessibilidade``: ``pass`` se ``accessibility_score >= 0.9`` em
      todas as análises de sucesso, ``fail`` se alguma < 0.9, ``na`` sem dado;
    - ``manual_webmcp_*``: 3 checks manuais (default ``na``).
    """
    itens: list[CwvChecklistItem] = []

    # llms.txt — pior veredito entre origens.
    try:
        from app.models.cwv_page_experience import CwvPageExperience

        result = await session.execute(
            select(CwvPageExperience).where(CwvPageExperience.execucao_id == execucao_id)
        )
        rows = list(result.scalars().all())
        vereditos = [r.llms_txt for r in rows if getattr(r, "llms_txt", None)]
        if vereditos:
            status = _pior_veredito(vereditos)
            itens.append(CwvChecklistItem(
                auditoria_id=auditoria_id,
                origem="agentic",
                item_codigo="agentic_llms_txt",
                titulo="Arquivo llms.txt válido",
                status_before=status,
                prioridade=0 if status == "pass" else 999,
            ))
    except Exception:
        logger.warning("_itens_agentic: llms_txt indisponível para exec %s", execucao_id, exc_info=True)

    # Acessibilidade — score da categoria accessibility do PSI (raw_resumo_json).
    scores: list[float] = []
    for a in analises:
        s = (a.raw_resumo_json or {}).get("accessibility_score")
        if s is not None:
            scores.append(float(s))
    if not scores:
        status_acc = "na"
    elif all(s >= _ACESSIBILIDADE_MIN for s in scores):
        status_acc = "pass"
    else:
        status_acc = "fail"
    itens.append(CwvChecklistItem(
        auditoria_id=auditoria_id,
        origem="agentic",
        item_codigo="agentic_acessibilidade",
        titulo="Árvore de acessibilidade bem estruturada",
        status_before=status_acc,
        prioridade=0 if status_acc == "pass" else 999,
    ))

    # WebMCP — 3 checks manuais (não automatizável sem render headless).
    for codigo, titulo in ITENS_MANUAIS_AGENTIC:
        itens.append(CwvChecklistItem(
            auditoria_id=auditoria_id,
            origem="agentic",
            item_codigo=codigo,
            titulo=titulo,
            status_before="na",
            prioridade=0,
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


async def _criar_auditoria_automatica(
    session,
    *,
    execucao,
    cliente_id: str,
    usuario_id: str,
) -> tuple[str | None, str | None]:
    """Cria auditoria automática após execução CWV. Fail-open.

    Returns (auditoria_id_criada, auditoria_existente_id).

    SPEC_CWV_Auditoria_Automatica_Pos_Execucao:
    - re-auditoria (``entrada_json.auditoria_id``): aponta para a auditoria dona;
    - cliente com auditoria ABERTA (``before``/``aguardando_implementacao``/
      ``after``): aponta para ela e NÃO cria outra (evita pilha paralela);
    - caso contrário: cria uma nova.
    """
    auditoria_existente = (execucao.entrada_json or {}).get("auditoria_id")
    if auditoria_existente:
        return (None, str(auditoria_existente))

    # Cliente já tem auditoria aberta? Aponta em vez de empilhar (crit. #2).
    aberta_res = await session.execute(
        select(CwvAuditoria.id)
        .where(
            CwvAuditoria.cliente_id == cliente_id,
            CwvAuditoria.fase.in_(("before", "aguardando_implementacao", "after")),
        )
        .limit(1)
    )
    aberta_id = aberta_res.scalar_one_or_none()
    if aberta_id:
        return (None, str(aberta_id))

    try:
        auditoria = await criar_auditoria(
            session,
            usuario_id=usuario_id,
            cliente_id=cliente_id,
            execucao_id=str(execucao.id),
        )
        return (str(auditoria.id), None)
    except Exception:
        logger.warning(
            "criar_auditoria_automatica falhou para execucao %s",
            execucao.id,
            exc_info=True,
        )
        return (None, None)


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

    # Page experience after (inclui llms_txt do grupo agêntico).
    pe_vereditos_after: dict[str, list[str]] = {}
    llms_txt_after: list[str] = []
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
            llms_v = getattr(row, "llms_txt", None)
            if llms_v:
                llms_txt_after.append(llms_v)
    except Exception:
        logger.warning("aplicar_resultado_after: page_experience indisponível", exc_info=True)

    # SPEC_CWV_Navegacao_Agentica: accessibility_score das análises after.
    acc_scores_after: list[float] = []
    for a in analises_after:
        s = (a.raw_resumo_json or {}).get("accessibility_score")
        if s is not None:
            acc_scores_after.append(float(s))

    n_pass = n_fail = 0
    for item in itens:
        # SPEC_CWV_Checklist_Itens_Manuais: preservar avaliação humana.
        if item.item_codigo.startswith("manual_"):
            continue

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

        elif item.origem == "agentic":
            # manual_webmcp_* já foram preservados no guard startswith("manual_").
            if item.item_codigo == "agentic_llms_txt":
                if not llms_txt_after:
                    item.status_after = "na"
                else:
                    st = _pior_veredito(llms_txt_after)
                    item.status_after = st
                    if st == "pass":
                        n_pass += 1
                    elif st == "fail":
                        n_fail += 1
            elif item.item_codigo == "agentic_acessibilidade":
                if not acc_scores_after:
                    item.status_after = "na"
                elif all(s >= _ACESSIBILIDADE_MIN for s in acc_scores_after):
                    item.status_after = "pass"
                    n_pass += 1
                else:
                    item.status_after = "fail"
                    n_fail += 1

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


_CAP_TITULOS = 20


def _metricas_analise(a: dict) -> dict:
    return {
        "analise_id": str(a.get("id", "")),
        "score_performance": a.get("score_performance"),
        "lcp_ms": a.get("lcp_ms"),
        "cls": a.get("cls"),
        "inp_ms": a.get("inp_ms"),
        "tbt_ms": a.get("tbt_ms"),
        "n_problemas": len(a.get("problemas") or []),
    }


def montar_comparativo(
    analises_before: list[dict], analises_after: list[dict] | None
) -> list[dict]:
    """SPEC_CWV_Auditoria_Comparativo_API: pares URL×estratégia before/after.

    Função pura — recebe dicts de ``buscar_analises_da_execucao``. Diff de
    problemas pela mesma ``chave_problema`` do checklist/S5.
    """
    ok_before = [a for a in analises_before if a.get("status") == "sucesso"]
    ok_after = [a for a in (analises_after or []) if a.get("status") == "sucesso"]
    idx_after = {(a["url_canonica"], a["estrategia"]): a for a in ok_after}

    pares: list[dict] = []
    for a in ok_before:
        b = idx_after.get((a["url_canonica"], a["estrategia"]))
        problemas = None
        if b is not None:
            chaves_b = {chave_problema(p): p for p in (a.get("problemas") or [])}
            chaves_a = {chave_problema(p): p for p in (b.get("problemas") or [])}
            resolvidas = sorted(set(chaves_b) - set(chaves_a))
            novas = sorted(set(chaves_a) - set(chaves_b))
            persistentes = set(chaves_b) & set(chaves_a)
            problemas = {
                "resolvidos": len(resolvidas),
                "persistentes": len(persistentes),
                "novos": len(novas),
                "titulos_resolvidos": [chaves_b[c].get("titulo") or c for c in resolvidas[:_CAP_TITULOS]],
                "titulos_novos": [chaves_a[c].get("titulo") or c for c in novas[:_CAP_TITULOS]],
            }
        pares.append({
            "url_canonica": a["url_canonica"],
            "estrategia": a["estrategia"],
            "template_tipo": a.get("template_tipo", ""),
            "before": _metricas_analise(a),
            "after": _metricas_analise(b) if b is not None else None,
            "problemas": problemas,
        })

    pares.sort(key=lambda p: (p["template_tipo"], p["url_canonica"], p["estrategia"]))
    return pares


def montar_detalhe_item(
    *,
    item_codigo: str,
    titulo: str,
    esforco: str | None,
    urls_escopo: list[str],
    plataforma: str | None,
    evidencias: list[dict] | None = None,
) -> dict:
    """SPEC_CWV_Auditoria_UI_V2: ficha explicativa de um item do checklist.

    Enriquece o item com a KB (``item_codigo`` == código KB para itens mapeados):
    o que é o problema (``descricao``), como corrigir (``solucoes`` — geral +
    plataforma) e referências. Itens sem KB (``audit:*``, ``titulo:*``, field
    data, page experience) retornam ``tem_kb=False`` com o restante nulo — a UI
    mostra só título/esforço/URLs nesses casos.
    """
    from app.services.cwv_kb import buscar_entrada

    entrada = buscar_entrada(item_codigo)
    if entrada is None:
        return {
            "item_codigo": item_codigo,
            "titulo": titulo,
            "tem_kb": False,
            "descricao": DESCRICOES_ITENS_SEM_KB.get(item_codigo),
            "severidade": None,
            "metricas_afetadas": [],
            "solucao_geral": None,
            "solucao_plataforma": None,
            "plataforma": plataforma,
            "links_referencia": [],
            "esforco": esforco,
            "urls_escopo": urls_escopo,
            "evidencias": evidencias or [],
        }

    solucoes = entrada.get("solucoes") or {}
    solucao_plataforma = None
    if plataforma and plataforma != "geral":
        solucao_plataforma = solucoes.get(plataforma)
    return {
        "item_codigo": item_codigo,
        "titulo": entrada.get("titulo") or titulo,
        "tem_kb": True,
        "descricao": entrada.get("descricao"),
        "severidade": entrada.get("severidade"),
        "metricas_afetadas": entrada.get("metricas_afetadas") or [],
        "solucao_geral": solucoes.get("geral"),
        "solucao_plataforma": solucao_plataforma,
        "plataforma": plataforma,
        "links_referencia": entrada.get("links_referencia") or [],
        "esforco": esforco,
        "urls_escopo": urls_escopo,
        "evidencias": evidencias or [],
    }


def _elemento_legivel(item: dict) -> str | None:
    """Extrai uma string legível de um item de contexto_especifico."""
    if not isinstance(item, dict):
        return None
    for chave in ("node_label", "label", "selector", "url", "snippet"):
        val = item.get(chave)
        if val and isinstance(val, str) and val.strip():
            return val.strip()[:200]
    return None


_CAP_EVIDENCIAS = 40


def montar_evidencias(rows: list[tuple]) -> list[dict]:
    """SPEC_CWV_Detalhe_Evidencias_Elementos: agrupa elementos com falha por URL×estratégia.

    ``rows`` = [(problema, url_canonica, estrategia), ...]. Um item de checklist pode
    agregar vários audits (mesma chave) na mesma URL×estratégia — funde todos,
    deduplica preservando ordem e retorna a contagem total (``total``) além dos
    ``elementos`` exibíveis (cap de ``_CAP_EVIDENCIAS``).
    """
    grupos: dict[tuple, list[str]] = {}
    for p, url, estrategia in rows:
        ctx = (p.contexto_especifico if hasattr(p, "contexto_especifico") else p.get("contexto_especifico")) or {}
        items = ctx.get("items") or []
        for it in items:
            if not isinstance(it, dict):
                continue
            el = _elemento_legivel(it)
            if el:
                grupos.setdefault((url, estrategia), []).append(el)

    out: list[dict] = []
    for (url, estrategia), els in sorted(grupos.items()):
        vistos: set[str] = set()
        unicos = [e for e in els if not (e in vistos or vistos.add(e))]
        if unicos:
            out.append({
                "url_canonica": url,
                "estrategia": estrategia,
                "elementos": unicos[:_CAP_EVIDENCIAS],
                "total": len(unicos),
            })
    return out
