import logging

from app.services.cwv_kb import buscar_entrada

logger = logging.getLogger(__name__)

AUDIT_METRICAS: dict[str, list[str]] = {
    "largest-contentful-paint": ["LCP"],
    "first-contentful-paint": ["FCP"],
    "total-blocking-time": ["TBT"],
    "cumulative-layout-shift": ["CLS"],
    "interaction-to-next-paint": ["INP"],
    "experimental-interaction-to-next-paint": ["INP"],
    "interactive": ["INP", "TBT"],
    "speed-index": ["LCP", "FCP", "CLS"],
    "server-response-time": ["TTFB"],
    "render-blocking-resources": ["LCP", "FCP"],
    "uses-long-cache-ttl": ["TTFB"],
    "uses-text-compression": ["TTFB"],
    "modern-image-formats": ["LCP"],
    "dom-size": ["INP"],
    "unused-css-rules": ["FCP"],
    "unused-javascript": ["FCP"],
    "unminified-css": ["FCP"],
    "unminified-javascript": ["FCP"],
    "bootup-time": ["FCP", "INP"],
    "mainthread-work": ["INP"],
    "offscreen-images": ["LCP"],
    "uses-optimized-images": ["LCP"],
    "efficient-animated-content": ["CLS"],
    "font-display": ["FCP"],
    "viewport": ["CLS"],
    "prioritize-lcp-image": ["LCP"],
    "layout-shifts": ["CLS"],
    "long-tasks": ["INP"],
    "third-party-summary": ["FCP", "INP"],
    "duplicated-javascript": ["FCP"],
    "legacy-javascript": ["FCP", "INP"],
    "diagnostics": [],
    "metrics": [],
}


def _severidade_por_savings(savings_ms: float | None, savings_bytes: float | None) -> int:
    if savings_ms is not None:
        if savings_ms >= 1000:
            return 5
        if savings_ms >= 500:
            return 4
        if savings_ms >= 200:
            return 3
        if savings_ms >= 50:
            return 2
    if savings_bytes is not None:
        kb = savings_bytes / 1024
        if kb >= 200:
            return 5
        if kb >= 100:
            return 4
        if kb >= 50:
            return 3
        if kb >= 20:
            return 2
    return 1


def _metricas_por_audit(audit_id: str) -> list[str]:
    return list(AUDIT_METRICAS.get(audit_id, [])) or ["LCP"]


class CWVDocumentadorAgent:
    async def documentar(
        self, *, problemas: list[dict], plataforma: str
    ) -> list[dict]:
        documentados = []
        for p in problemas:
            kb_codigo = p.get("kb_codigo")
            entrada_kb = buscar_entrada(kb_codigo) if kb_codigo else None

            if entrada_kb is None:
                audit_id = p.get("audit_id") or p.get("contexto_especifico", {}).get("audit_id", "")
                titulo = p.get("contexto_especifico", {}).get("title", "") or audit_id
                doc_md = self._gerar_doc_skeleton(p, audit_id)
                severidade = _severidade_por_savings(
                    p.get("contexto_especifico", {}).get("savings_ms"),
                    p.get("contexto_especifico", {}).get("savings_bytes"),
                )
                metricas = _metricas_por_audit(audit_id) if audit_id else ["LCP"]
                documentados.append({
                    "kb_codigo": kb_codigo,
                    "audit_id": audit_id,
                    "titulo": titulo,
                    "severidade": severidade,
                    "metricas_afetadas": metricas,
                    "contexto_especifico": p.get("contexto_especifico", {}),
                    "documentacao_md": doc_md,
                })
                continue

            doc_md = self._gerar_doc(entrada_kb, plataforma, p.get("contexto_especifico", {}))
            documentados.append({
                "kb_codigo": kb_codigo,
                "audit_id": p.get("audit_id"),
                "titulo": entrada_kb["titulo"],
                "severidade": entrada_kb["severidade"],
                "metricas_afetadas": entrada_kb["metricas_afetadas"],
                "contexto_especifico": p.get("contexto_especifico", {}),
                "documentacao_md": doc_md,
            })
        return documentados

    @staticmethod
    def _gerar_doc_skeleton(problema: dict, audit_id: str) -> str:
        ctx = problema.get("contexto_especifico", {})
        titulo = ctx.get("title", audit_id)
        descricao = ctx.get("description", "Audit do Lighthouse sem entrada especifica na base de conhecimento.")

        return (
            f"## {titulo}\n\n{descricao}\n\n"
            "## Solucao\n\n"
            "Consulte a documentacao oficial do Lighthouse/Chrome para orientacoes especificas sobre este audit.\n\n"
            "Para obter recomendacoes mais detalhadas, este problema pode ser re-analisado com pesquisa em tempo real.\n"
        )

    @staticmethod
    def _gerar_doc(entrada_kb: dict, plataforma: str, contexto: dict) -> str:
        partes: list[str] = [
            f"## Problema\n\n{entrada_kb['descricao']}\n",
            "## Solucao\n\n",
        ]

        solucoes = entrada_kb.get("solucoes", {})
        if plataforma in solucoes and plataforma != "geral":
            partes.append(f"**Para sua plataforma ({plataforma.upper()}):**\n\n{solucoes[plataforma]}\n\n")

        geral = solucoes.get("geral", "")
        if geral:
            partes.append(f"**Solucao geral:**\n\n{geral}\n")

        links = entrada_kb.get("links_referencia") or []
        if links:
            partes.append("\n## Referencias\n\n")
            for link in links:
                partes.append(f"- [{link['titulo']}]({link['url']})\n")

        return "".join(partes)
