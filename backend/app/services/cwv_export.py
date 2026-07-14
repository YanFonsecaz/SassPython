import html
import re

import markdown

SEVERIDADE_LABELS = {5: "Critico", 4: "Critico", 3: "Alto", 2: "Medio", 1: "Baixo"}

# Thresholds (meta) por audit_id — fonte: docs Lighthouse/web.dev e cabeçalhos
# da planilha NPBR. Exibidos no cabeçalho da tabela de evidências para o cliente
# entender de imediato o quão longe cada recurso está do ideal. pt-BR direto.
THRESHOLDS_POR_AUDIT: dict[str, str] = {
    "long-tasks": "< 100 ms por tarefa",
    "mainthread-work-breakdown": "< 2 s de trabalho na main thread",
    "bootup-time": "< 2 s de execução de JS",
    "total-blocking-time": "TBT < 200 ms",
    "server-response-time": "TTFB < 600 ms",
    "render-blocking-resources": "0 recursos bloqueantes",
    "unused-javascript": "desperdício < 20 KB por arquivo",
    "unused-css-rules": "desperdício < 20 KB por arquivo",
    "uses-long-cache-ttl": "TTL de cache ≥ 30 dias",
    "total-byte-weight": "página < 1,6 MB",
    "dom-size": "< 800 nós no DOM",
    "third-party-summary": "bloqueio por terceiros < 250 ms",
    "largest-contentful-paint": "LCP < 2,5 s",
    "cumulative-layout-shift": "CLS < 0,1",
    "interaction-to-next-paint": "INP < 200 ms",
    "first-contentful-paint": "FCP < 1,8 s",
    "modern-image-formats": "imagens em WebP/AVIF",
    "uses-optimized-images": "0 KB de desperdício por compressão",
    "uses-responsive-images": "imagem ≤ tamanho exibido",
    "offscreen-images": "imagens fora da tela com lazy load",
    "unminified-javascript": "JS minificado (0 KB de desperdício)",
    "unminified-css": "CSS minificado (0 KB de desperdício)",
    "uses-text-compression": "compressão gzip/brotli ativa",
    "redirects": "0 redirecionamentos encadeados",
    "critical-request-chains": "cadeias críticas curtas (≤ 2 níveis)",
    "layout-shifts": "nenhum shift > 0,05",
    "legacy-javascript": "0 polyfills desnecessários",
    "duplicated-javascript": "0 módulos duplicados",
    "efficient-animated-content": "vídeo no lugar de GIF",
    "font-display": "font-display: swap/optional",
    "prioritize-lcp-image": "imagem LCP com fetchpriority=high",
    "lcp-lazy-loaded": "imagem LCP sem lazy load",
    "unsized-images": "width/height explícitos em todas as imagens",
}


def threshold_do_audit(audit_id: str | None) -> str | None:
    """Resolve o threshold (meta) de um audit_id.

    Aplica ``AUDIT_ALIASES`` (resolve ids ``-insight`` antes do lookup).
    Retorna ``None`` se o audit não tiver threshold mapeado.
    """
    if not audit_id:
        return None
    from app.services.cwv_kb import AUDIT_ALIASES

    resolvido = AUDIT_ALIASES.get(audit_id, audit_id)
    return THRESHOLDS_POR_AUDIT.get(resolvido)


def _severidade_label(sev: int) -> str:
    return SEVERIDADE_LABELS.get(sev, str(sev))


def _fmt_bytes(n) -> str:
    if n is None:
        return ""
    n = int(n)
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    if n >= 1_024:
        return f"{n / 1_024:.1f} KB"
    return f"{n} B"


def _fmt_ms(n) -> str:
    if n is None:
        return ""
    return f"{float(n):.0f} ms"


def _md_to_html(md_text: str) -> str:
    return markdown.markdown(
        md_text,
        extensions=["fenced_code", "tables", "sane_lists"],
    )


def _escape(text: str) -> str:
    return html.escape(text or "")


def _html_table(headers: list[str], rows: list[list]) -> str:
    # Gera <table> HTML (renderizado por html_para_docx_bytes). NAO usar markdown
    # aqui: tabelas em markdown soltas no HTML sao descartadas pelo parser (selectolax).
    out = ["<table data-causas>"]
    out.append("<tr>" + "".join(f"<td>{_escape(str(h))}</td>" for h in headers) + "</tr>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{_escape(str(c))}</td>" for c in r) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def _tabela_recursos(items: list[dict], audit_id: str | None = None) -> str:
    if not items:
        return ""
    # Ordena por desperdício decrescente (os piores primeiro). wastedMs/wastedBytes
    # são opcionais; items sem desperdício mensurável ficam ao final (peso 0).
    def peso_wasted(item: dict) -> float:
        if item.get("wastedMs") is not None:
            return float(item["wastedMs"])
        if item.get("wastedBytes") is not None:
            return float(item["wastedBytes"])
        return 0.0

    items_ordenados = sorted(items, key=peso_wasted, reverse=True)[:50]

    rows = []
    for item in items_ordenados:
        recurso = item.get("url") or item.get("label") or ""
        detalhe = (item.get("snippet") or item.get("type") or "")[:120]
        desperd = _fmt_bytes(item.get("wastedBytes")) or _fmt_ms(item.get("wastedMs")) or ""
        total = _fmt_bytes(item.get("totalBytes")) or _fmt_ms(item.get("totalMs")) or ""
        rows.append([recurso, detalhe, desperd, total])

    threshold = threshold_do_audit(audit_id)
    partes = []
    if threshold:
        partes.append(f"<p><strong>Evidências</strong> — meta: {_escape(threshold)}</p>")
    partes.append(_html_table(["Recurso", "Detalhe", "Desperdicado", "Total"], rows))
    return "\n".join(partes)


def problema_para_html(problema: dict) -> str:
    ctx = problema.get("contexto_especifico") or {}
    titulo = _escape(problema.get("titulo", ""))
    metricas = ", ".join(problema.get("metricas_afetadas", []))
    severidade = _severidade_label(problema.get("severidade", 1))

    parts = [f"<h1>{titulo}</h1>"]
    parts.append(f"<p><em>Metricas afetadas: {metricas} · Severidade: {severidade}</em></p>")

    display_value = ctx.get("display_value", "")
    savings_ms = ctx.get("savings_ms")
    savings_bytes = ctx.get("savings_bytes")
    metric_savings = ctx.get("metric_savings")
    if display_value:
        parts.append(f"<p><strong>Valor atual:</strong> {_escape(str(display_value))}</p>")
    if savings_ms is not None:
        parts.append(f"<p><strong>Economia estimada:</strong> {_fmt_ms(savings_ms)}</p>")
    elif savings_bytes is not None:
        parts.append(f"<p><strong>Economia estimada:</strong> {_fmt_bytes(savings_bytes)}</p>")
    elif metric_savings:
        for metric_name, saving_val in metric_savings.items():
            parts.append(f"<p><strong>Economia ({metric_name}):</strong> {_fmt_ms(saving_val)}</p>")

    description = ctx.get("description", "")
    if description:
        parts.append(f"<p>{_escape(description)}</p>")

    items = (ctx.get("items") or ctx.get("details", {}).get("items") or [])
    if items:
        parts.append(_tabela_recursos(items, problema.get("audit_id")))

    doc_md = problema.get("documentacao_md", "")
    if doc_md:
        parts.append("<h2>Como corrigir</h2>")
        parts.append(_md_to_html(doc_md))

    return "\n".join(parts)


def relatorio_para_html(analise: dict, problemas: list[dict]) -> str:
    url = _escape(analise.get("url_canonica", ""))
    plataforma = _escape(analise.get("plataforma_detectada", ""))
    estrategia = _escape(analise.get("estrategia", ""))
    data = _escape((analise.get("criado_em") or "")[:10])

    parts = [f"<h1>Relatorio Core Web Vitals — {url}</h1>"]
    parts.append(f"<p><em>{plataforma} · {estrategia} · {data}</em></p>")

    perf_rows = []
    for label, key in [
        ("Performance", "score_performance"),
        ("LCP", "lcp_ms"),
        ("CLS", "cls"),
        ("INP", "inp_ms"),
        ("FCP", "fcp_ms"),
    ]:
        val = analise.get(key)
        if val is None:
            continue
        if key.endswith("_ms"):
            display = _fmt_ms(val)
        elif label == "Performance":
            display = f"{float(val):.0f}"
        else:
            display = str(val)
        perf_rows.append([label, display])

    if perf_rows:
        parts.append(_html_table(["Metrica", "Valor"], perf_rows))

    if problemas:
        parts.append("<h2>Sumario</h2>")
        sum_rows = [
            [
                str(i),
                p.get("titulo", "")[:80],
                ", ".join(p.get("metricas_afetadas", [])),
                _severidade_label(p.get("severidade", 1)),
            ]
            for i, p in enumerate(problemas, start=1)
        ]
        parts.append(_html_table(["Prioridade", "Problema", "Metricas", "Severidade"], sum_rows))

    for i, p in enumerate(problemas, start=1):
        ctx = p.get("contexto_especifico") or {}
        titulo = _escape(p.get("titulo", ""))
        parts.append(f"<h2>{i}. {titulo}</h2>")

        metricas = ", ".join(p.get("metricas_afetadas", []))
        severidade = _severidade_label(p.get("severidade", 1))
        parts.append(f"<p><em>Metricas: {metricas} · Severidade: {severidade}</em></p>")

        display_value = ctx.get("display_value", "")
        savings_ms = ctx.get("savings_ms")
        savings_bytes = ctx.get("savings_bytes")
        if display_value:
            parts.append(f"<p><strong>Valor atual:</strong> {_escape(str(display_value))}</p>")
        if savings_ms is not None:
            parts.append(f"<p><strong>Economia estimada:</strong> {_fmt_ms(savings_ms)}</p>")
        elif savings_bytes is not None:
            parts.append(f"<p><strong>Economia estimada:</strong> {_fmt_bytes(savings_bytes)}</p>")

        description = ctx.get("description", "")
        if description:
            parts.append(f"<p>{_escape(description)}</p>")

        items = (ctx.get("items") or ctx.get("details", {}).get("items") or [])
        if items:
            parts.append(_tabela_recursos(items, p.get("audit_id")))

        doc_md = p.get("documentacao_md", "")
        if doc_md:
            parts.append("<h3>Como corrigir</h3>")
            parts.append(_md_to_html(doc_md))

    return "\n".join(parts)


def chave_problema(p: dict) -> str:
    """Chave canônica de problema para dedup (mesma regra do comparador).

    Prioridade: ``kb_codigo`` > ``audit:{audit_id}`` > ``titulo:{titulo}``.
    Usada por S3 (dedup mobile/desktop no consolidado) e S5 (gerar_checklist).
    """
    if p.get("kb_codigo"):
        return p["kb_codigo"]
    if p.get("audit_id"):
        return f"audit:{p['audit_id']}"
    return f"titulo:{p.get('titulo', '')}"


def _capitulo_problemas(
    problemas: list[dict],
    *,
    max_problemas: int | None = None,
    max_recursos: int | None = None,
    heading_tag: str = "h2",
) -> str:
    """Renderiza a lista de problemas de um capítulo/relatório.

    Refatorado de ``relatorio_para_html`` (S3). ``max_problemas`` trunca a
    lista e emite linha "e mais N"; ``None`` = sem limite (comportamento do
    export unitário). ``max_recursos`` aplica-se à tabela de evidências.
    """
    if not problemas:
        return ""

    limitados = problemas if max_problemas is None else problemas[:max_problemas]
    partes: list[str] = []

    for i, p in enumerate(limitados, start=1):
        ctx = p.get("contexto_especifico") or {}
        titulo = _escape(p.get("titulo", ""))
        partes.append(f"<{heading_tag}>{i}. {titulo}</{heading_tag}>")

        metricas = ", ".join(p.get("metricas_afetadas", []))
        severidade = _severidade_label(p.get("severidade", 1))
        partes.append(f"<p><em>Metricas: {metricas} · Severidade: {severidade}</em></p>")

        display_value = ctx.get("display_value", "")
        savings_ms = ctx.get("savings_ms")
        savings_bytes = ctx.get("savings_bytes")
        if display_value:
            partes.append(f"<p><strong>Valor atual:</strong> {_escape(str(display_value))}</p>")
        if savings_ms is not None:
            partes.append(f"<p><strong>Economia estimada:</strong> {_fmt_ms(savings_ms)}</p>")
        elif savings_bytes is not None:
            partes.append(f"<p><strong>Economia estimada:</strong> {_fmt_bytes(savings_bytes)}</p>")

        description = ctx.get("description", "")
        if description:
            partes.append(f"<p>{_escape(description)}</p>")

        items = (ctx.get("items") or ctx.get("details", {}).get("items") or [])
        if items:
            if max_recursos is not None:
                items = items[:max_recursos]
            partes.append(_tabela_recursos(items, p.get("audit_id")))

        doc_md = p.get("documentacao_md", "")
        if doc_md:
            partes.append(f"<{'h3' if heading_tag == 'h2' else 'h4'}>Como corrigir</{'h3' if heading_tag == 'h2' else 'h4'}>")
            partes.append(_md_to_html(doc_md))

    if max_problemas is not None and len(problemas) > max_problemas:
        restante = len(problemas) - max_problemas
        partes.append(f"<p><em>… e mais {restante} problema(s) de menor prioridade (ver análise individual).</em></p>")

    return "\n".join(partes)


def relatorio_execucao_para_html(
    execucao: dict,
    analises: list[dict],
    cliente_nome: str = "",
) -> str:
    """SPEC_CWV_Export_Consolidado_Execucao: DOCX consolidado da execução.

    Capa + sumário comparativo + capítulos por URL (mobile+desktop agrupados)
    + apêndice de URLs não analisadas.
    """
    partes: list[str] = []

    # 1. Capa
    titulo_capa = _escape(cliente_nome) if cliente_nome else "Auditoria"
    data = _escape((execucao.get("criado_em") or "")[:10])
    n_urls = len({a.get("url_canonica") for a in analises if a.get("status") == "sucesso"})
    partes.append(f"<h1>Auditoria Core Web Vitals — {titulo_capa}</h1>")
    partes.append(f"<p><em>{data} · {n_urls} URL(s) analisada(s)</em></p>")
    resultado = execucao.get("resultado_json") or {}
    health = resultado.get("health_score") if isinstance(resultado, dict) else None
    if health and isinstance(health, dict) and health.get("health_score") is not None:
        partes.append(f"<p><strong>Health Score:</strong> {health['health_score']}%</p>")

    # 2. Sumário comparativo — uma linha por análise de sucesso
    sucessos = [a for a in analises if a.get("status") == "sucesso"]
    if sucessos:
        sucessos.sort(key=lambda a: (a.get("url_canonica", ""), a.get("estrategia", "")))
        sum_rows = []
        for a in sucessos:
            problemas = a.get("problemas", [])
            n_criticos = sum(1 for p in problemas if p.get("severidade", 0) >= 4)
            sum_rows.append([
                a.get("url_canonica", "")[:60],
                a.get("estrategia", ""),
                str(a.get("score_performance", "—")),
                _fmt_ms(a.get("lcp_ms")),
                str(a.get("cls", "—")),
                _fmt_ms(a.get("inp_ms")),
                str(len(problemas)),
                str(n_criticos),
            ])
        partes.append("<h2>Sumario comparativo</h2>")
        partes.append(_html_table(
            ["URL", "Estrategia", "Score", "LCP", "CLS", "INP", "Problemas", "Criticos"],
            sum_rows,
        ))

    # 3. Capítulos por URL (agrupar mobile+desktop)
    por_url: dict[str, list[dict]] = {}
    for a in sucessos:
        por_url.setdefault(a.get("url_canonica", ""), []).append(a)

    for url, grupo in por_url.items():
        partes.append(f"<h2>{_escape(url)}</h2>")
        primeiro = grupo[0]
        partes.append(
            f"<p><em>Template: {primeiro.get('template_tipo', '—')} · "
            f"Plataforma: {primeiro.get('plataforma_detectada', '—')}</em></p>"
        )
        # Dedup mobile/desktop: se mesma chave de problema em ambas, renderiza 1x.
        if len(grupo) == 2:
            probs_mobile = grupo[0].get("problemas", [])
            probs_desktop = grupo[1].get("problemas", [])
            chaves_mobile = {chave_problema(p) for p in probs_mobile}
            chaves_desktop = {chave_problema(p) for p in probs_desktop}
            if chaves_mobile == chaves_desktop and chaves_mobile:
                partes.append("<p><em>Observação: os problemas ocorrem de forma idêntica em Desktop e Mobile.</em></p>")
                partes.append(_capitulo_problemas(probs_mobile, max_problemas=15, max_recursos=10, heading_tag="h3"))
                continue
        # Caso geral: subseções por estratégia
        for a in grupo:
            partes.append(f"<h3>{a.get('estrategia', '').title()}</h3>")
            partes.append(_capitulo_problemas(
                a.get("problemas", []), max_problemas=15, max_recursos=10, heading_tag="h4",
            ))

    # 4. Apêndice — URLs não analisadas
    falhas = [a for a in analises if a.get("status") != "sucesso"]
    if falhas:
        partes.append("<h2>Apêndice — URLs não analisadas</h2>")
        ap_rows = [[a.get("url", "")[:60], a.get("estrategia", ""), a.get("erro_msg", "")[:120]] for a in falhas]
        partes.append(_html_table(["URL", "Estrategia", "Erro"], ap_rows))

    return "\n".join(partes)


def slugify_titulo(titulo: str, max_len: int = 60) -> str:
    s = titulo.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s).strip("-")
    return s[:max_len] or "cwv-problema"
