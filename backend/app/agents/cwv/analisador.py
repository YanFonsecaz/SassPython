import logging

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.services.cwv_kb import AUDITS_IGNORADOS, listar_kb_codigos_descritos, mapeamento_audit_kb_com_aliases

logger = logging.getLogger(__name__)


class ProblemaIdentificado(BaseModel):
    kb_codigo: str | None = None
    audit_id: str | None = None
    contexto_especifico: dict = Field(default_factory=dict)
    audits_origem: list[str] = Field(default_factory=list)


class ListaProblemas(BaseModel):
    problemas: list[ProblemaIdentificado] = Field(default_factory=list)


class CWVAnalisadorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings

        model = settings.cwv_analisador_llm_model if settings.llm_provider == "openai" else None
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.cwv_analisador_llm_temperature,
        )

    async def analisar(
        self, *, audits_falhos: list[dict], plataforma: str, metricas: dict
    ) -> tuple[list[dict], dict]:
        """Retorna (problemas, stats) onde stats tem chaves: llm_usado, processados, descartados."""
        diretos = mapeamento_audit_kb_com_aliases()
        identificados: list[ProblemaIdentificado] = []

        audits_falhos = [a for a in audits_falhos if a.get("id") not in AUDITS_IGNORADOS]

        for audit in audits_falhos:
            aid = audit.get("id", "")
            if aid in diretos:
                identificados.append(
                    ProblemaIdentificado(
                        kb_codigo=diretos[aid],
                        audit_id=aid,
                        contexto_especifico=_extrair_contexto(audit),
                        audits_origem=[aid],
                    )
                )

        audits_residuais = [a for a in audits_falhos if a.get("id", "") not in diretos]

        stats = {"llm_usado": False, "processados": 0, "descartados": 0}

        if audits_residuais:
            stats["llm_usado"] = True
            stats["processados"] = len(audits_residuais)
            kb_descritos = listar_kb_codigos_descritos()
            kb_codigos_validos = {c["codigo"] for c in kb_descritos}
            try:
                prompt = _montar_prompt_analise(
                    audits_residuais, kb_descritos, plataforma, metricas
                )
                logger.info(
                    "CWV analisador prompt size: %d chars, %d audits",
                    len(prompt), len(audits_residuais),
                )
                resp: ListaProblemas = await self.invoke_structured(prompt, ListaProblemas)

                validos = [p for p in resp.problemas if p.kb_codigo in kb_codigos_validos]
                descartados = len(resp.problemas) - len(validos)
                if descartados:
                    logger.warning(
                        "CWV analisador descartou %d problemas com kb_codigo inexistente",
                        descartados,
                    )
                    stats["descartados"] += descartados
                identificados.extend(validos)

                audits_cobertos_llm: set[str] = set()
                for p in validos:
                    audits_cobertos_llm.update(p.audits_origem)
                for a in audits_residuais:
                    aid = a.get("id", "")
                    if aid not in audits_cobertos_llm:
                        _emit_kb_miss(a)
                        identificados.append(
                            ProblemaIdentificado(
                                kb_codigo=None,
                                audit_id=aid,
                                contexto_especifico={
                                    **_extrair_contexto(a),
                                    "audit_id": aid,
                                },
                                audits_origem=[aid],
                            )
                        )
            except Exception as e:
                logger.warning("CWV analisador LLM fallback falhou: %s", e)
                stats["descartados"] += len(audits_residuais)
                for a in audits_residuais:
                    _emit_kb_miss(a)
                    identificados.append(
                        ProblemaIdentificado(
                            kb_codigo=None,
                            audit_id=a.get("id", ""),
                            contexto_especifico={
                                **_extrair_contexto(a),
                                "audit_id": a.get("id", ""),
                            },
                            audits_origem=[a.get("id", "")],
                        )
                    )

        return [p.model_dump() for p in identificados], stats


def _emit_kb_miss(audit: dict):
    from app.core.metrics import cwv_kb_miss_total

    aid = audit.get("id") or "unknown"
    cwv_kb_miss_total.labels(audit_id=aid).inc()
    logger.warning(
        "CWV kb_miss: audit_id=%s title=%s — sem mapeamento na KB",
        aid,
        audit.get("title"),
        extra={"event_type": "cwv.kb_miss", "audit_id": aid},
    )


def _extrair_contexto(audit: dict) -> dict:
    details = audit.get("details") or {}
    items = details.get("items") or []
    headings = details.get("headings") or []
    headings_compact = [
        {k: h.get(k) for k in ("key", "label", "valueType", "subItemsHeading") if h.get(k) is not None}
        for h in headings if isinstance(h, dict)
    ]
    return {
        "display_value": audit.get("displayValue"),
        "title": audit.get("title"),
        "description": audit.get("description"),
        "score": audit.get("score"),
        "score_display_mode": audit.get("scoreDisplayMode"),
        "numeric_value": audit.get("numericValue"),
        "numeric_unit": audit.get("numericUnit"),
        "details_type": details.get("type"),
        "savings_ms": details.get("overallSavingsMs"),
        "savings_bytes": details.get("overallSavingsBytes"),
        "metric_savings": audit.get("metricSavings"),
        "headings": headings_compact,
        "warnings": audit.get("warnings") or [],
        "items": _resumir_items(items),
    }


_ITEM_NUM_FIELDS = (
    "wastedMs", "wastedBytes", "wastedPercent",
    "totalBytes", "transferSize", "resourceBytes", "resourceSize",
    "duration", "scriptParseCompile", "scripting",
    "startTime", "endTime",
    "mainThreadTime", "total", "value", "statistic",
    "cacheLifetimeMs", "responseTime", "serverResponseTime",
    "requestCount",
)

_SUB_ITEM_STR_FIELDS = (
    "signal", "source", "location", "url",
    "label", "snippet", "node_label",
    "group_label", "value",
)


def _resumir_items(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        compact = {}
        if it.get("url"):
            compact["url"] = str(it["url"])[:500]
        node = it.get("node") if isinstance(it.get("node"), dict) else None
        if node and node.get("selector"):
            compact["selector"] = str(node["selector"])[:300]
        if node and node.get("snippet"):
            compact["snippet"] = str(node["snippet"])[:300]
        if node and node.get("nodeLabel"):
            compact["node_label"] = str(node["nodeLabel"])[:200]
        elif it.get("nodeLabel"):
            compact["node_label"] = str(it["nodeLabel"])[:200]
        if node and node.get("path"):
            compact["dom_path"] = str(node["path"])[:300]
        elif it.get("path"):
            compact["dom_path"] = str(it["path"])[:300]
        if node and node.get("boundingRect"):
            br = node["boundingRect"]
            if isinstance(br, dict):
                compact["bounding_rect"] = {k: br[k] for k in ("top", "left", "width", "height") if br.get(k) is not None}
        if it.get("label"):
            compact["label"] = str(it["label"])[:200]
        if it.get("entity"):
            compact["entity"] = str(it["entity"])[:100]
        if it.get("group"):
            compact["group"] = str(it["group"])[:80]
        if it.get("groupLabel"):
            compact["group_label"] = str(it["groupLabel"])[:120]
        if it.get("mimeType"):
            compact["mime_type"] = str(it["mimeType"])[:80]
        if it.get("name"):
            compact["name"] = str(it["name"])[:200]
        if it.get("timingType"):
            compact["timing_type"] = str(it["timingType"])[:50]
        if it.get("source"):
            src = it["source"]
            if isinstance(src, dict):
                src_str = src.get("url") or src.get("location") or str(src)
            else:
                src_str = str(src)
            compact["source"] = src_str[:300]
        for k in _ITEM_NUM_FIELDS:
            if it.get(k) is not None:
                compact[k] = it[k]
        sub = it.get("subItems") or {}
        sub_items = sub.get("items") if isinstance(sub, dict) else None
        if sub_items:
            sub_compact = []
            for s in sub_items:
                row = {}
                for k in _SUB_ITEM_STR_FIELDS:
                    if s.get(k) is not None:
                        v = s[k]
                        if isinstance(v, dict):
                            v = v.get("url") or v.get("location") or v.get("signal") or str(v)
                        row[k] = v if not isinstance(v, str) else v[:300]
                for k in ("wastedBytes", "wastedMs", "wastedPercent", "totalBytes", "duration", "mainThreadTime"):
                    if s.get(k) is not None:
                        row[k] = s[k]
                if row:
                    sub_compact.append(row)
            if sub_compact:
                compact["sub_items"] = sub_compact
        if compact:
            out.append(compact)
    return out


def _formatar_audit_para_prompt(audit: dict) -> str:
    ctx = _extrair_contexto(audit)
    aid = audit.get("id", "?")
    titulo = ctx.get("title", "?")
    descricao = (ctx.get("description") or "?")[:300]
    score = ctx.get("score")
    score_mode = ctx.get("score_display_mode", "?")
    nv = ctx.get("numeric_value")
    nu = ctx.get("numeric_unit", "")
    dv = ctx.get("display_value", "?")
    dt = ctx.get("details_type", "?")
    sms = ctx.get("savings_ms")
    sby = ctx.get("savings_bytes")
    warnings = ctx.get("warnings") or []
    items = ctx.get("items") or []

    linhas = [
        f"### audit: {aid}",
        f"- Titulo: {titulo}",
        f"- Descricao: {descricao}",
        f"- Score: {score} ({score_mode})",
        f"- Valor: {nv} {nu} (display: \"{dv}\")" if nv is not None else f"- Valor: {dv}",
        f"- Tipo de detalhe: {dt}",
    ]

    if sms is not None:
        linhas.append(f"- Ganho potencial: {sms:.0f}ms")
    elif sby is not None:
        linhas.append(f"- Ganho potencial: {sby / 1024:.1f}KB")
    else:
        linhas.append("- Ganho potencial: — (audit informativo, sem savings)")

    if warnings:
        for w in warnings[:3]:
            linhas.append(f"- Aviso: {w}")

    if items:
        linhas.append("- Top elementos:")
        for item in items[:3]:
            sel = item.get("selector")
            url = item.get("url")
            label = item.get("label")
            parts = []
            if sel:
                parts.append(f"selector: \"{sel}\"")
            if url:
                parts.append(f"url: {url}")
            if label:
                parts.append(f"label: {label}")
            linhas.append(f"  - {', '.join(parts)}")

    return "\n".join(linhas)


def _montar_prompt_analise(
    audits: list[dict], kb_descritos: list[dict], plataforma: str, metricas: dict
) -> str:
    metricas_str = (
        f"LCP={metricas.get('lcp_ms')}ms, CLS={metricas.get('cls')}, "
        f"INP={metricas.get('inp_ms')}ms, FCP={metricas.get('fcp_ms')}ms, "
        f"TTFB={metricas.get('ttfb_ms')}ms, TBT={metricas.get('tbt_ms')}ms"
    )

    kb_linhas = []
    for c in kb_descritos:
        metricas_str_kb = ", ".join(c["metricas_afetadas"])
        kb_linhas.append(
            f"- {c['codigo']} — {c['titulo']} ({metricas_str_kb})"
        )

    audits_str = "\n".join(
        _formatar_audit_para_prompt(a) for a in audits
    )

    return (
        "Voce e um especialista em Core Web Vitals analisando audits do Lighthouse.\n"
        "Mapeie cada audit falho para o codigo da base de conhecimento mais especifico.\n\n"
        f"Plataforma: {plataforma}\n"
        f"Metricas atuais: {metricas_str}\n\n"
        "## Base de conhecimento (use APENAS estes codigos)\n\n"
        + "\n".join(kb_linhas) + "\n\n"
        "## Audits falhos a classificar\n\n"
        f"{audits_str}\n\n"
        "## Instrucoes\n\n"
        "- Para cada audit, escolha o kb_codigo mais especifico (preferir mais especifico a mais generico).\n"
        "- Use `savings_ms` ou `savings_bytes` para priorizar — audits com >500ms ou >100KB de ganho sao alta severidade.\n"
        "- Se NENHUM codigo se encaixa, use `kb_codigo: null` e descreva no campo `contexto_especifico.audit_id` qual era o audit.\n"
        "- NAO invente kb_codigo fora da lista acima.\n"
        "- Inclua em `contexto_especifico` os elementos/URLs especificos afetados (max 3).\n"
        "- Retorne um problema para CADA audit (1:1) — nao consolide.\n"
        "- Inclua `audits_origem` com o ID do audit correspondente.\n"
    )
