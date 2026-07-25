"""Geração de HTML para export DOCX da Auditoria SEOTec.

Espelha o padrão do CWV (`cwv_export.relatorio_auditoria_para_html`): gera HTML
estruturado que `parecer_service.html_para_docx_bytes` converte para Word.
"""
from __future__ import annotations

from html import escape

_STATUS_LABELS = {
    "aprovado": "Aprovado",
    "atencao": "Atenção",
    "reprovado": "Reprovado",
    "na": "N/A",
    "sem_dados": "Sem dados",
}

_PRIORIDADE_CORES = {
    "alta": "#dc2626",
    "media": "#ca8a04",
    "baixa": "#6b7280",
}


def auditoria_para_html(
    dominio: str,
    fase: str,
    score_antes: float | None,
    score_depois: float | None,
    cliente_nome: str,
    criado_em: str,
    itens: list[dict],
) -> str:
    """Gera HTML da auditoria SEOTec para conversão em DOCX."""
    partes: list[str] = []

    # 1. Capa
    partes.append(f"<h1>Auditoria SEO Técnico — {escape(dominio)}</h1>")
    if cliente_nome:
        partes.append(f"<p><strong>Cliente:</strong> {escape(cliente_nome)}</p>")
    partes.append(f"<p><strong>Data:</strong> {escape(criado_em[:10] if criado_em else '—')}</p>")
    fase_label = {"before": "Before", "implementacao": "Implementação", "after": "After", "concluida": "Concluída"}.get(fase, fase)
    partes.append(f"<p><strong>Fase:</strong> {escape(fase_label)}</p>")

    # 2. Health Score
    partes.append("<h2>Health Score</h2>")
    partes.append("<table border='1' cellpadding='6' style='border-collapse:collapse;'>")
    partes.append("<tr><th>Score Before</th><th>Score After</th><th>Delta</th></tr>")
    s_antes = f"{score_antes:.0f}%" if score_antes is not None else "—"
    s_depois = f"{score_depois:.0f}%" if score_depois is not None else "—"
    if score_antes is not None and score_depois is not None:
        delta = score_depois - score_antes
        delta_str = f"{delta:+.1f} p.p."
    else:
        delta_str = "—"
    partes.append(f"<tr><td style='text-align:center;'>{s_antes}</td><td style='text-align:center;'>{s_depois}</td><td style='text-align:center;'>{delta_str}</td></tr>")
    partes.append("</table>")

    # 3. Resumo por categoria
    por_categoria: dict[str, list[dict]] = {}
    for item in itens:
        cat = item.get("categoria", "Outros")
        (por_categoria.setdefault(cat, [])).append(item)

    n_aprovado = sum(1 for i in itens if i.get("status_antes") == "aprovado")
    n_reprovado = sum(1 for i in itens if i.get("status_antes") == "reprovado")
    n_atencao = sum(1 for i in itens if i.get("status_antes") == "atencao")
    n_total = len(itens)

    partes.append("<h2>Resumo do Checklist</h2>")
    partes.append(f"<p>Total de itens: <strong>{n_total}</strong> · Aprovados: <strong>{n_aprovado}</strong> · Atenção: <strong>{n_atencao}</strong> · Reprovados: <strong>{n_reprovado}</strong></p>")

    # 4. Checklist detalhado por categoria
    partes.append("<h2>Checklist Detalhado</h2>")
    for categoria in sorted(por_categoria.keys()):
        itens_cat = por_categoria[categoria]
        n_cat_aprovado = sum(1 for i in itens_cat if i.get("status_antes") == "aprovado")
        n_cat_total = len(itens_cat)
        partes.append(f"<h3>{escape(categoria)} ({n_cat_aprovado}/{n_cat_total} aprovados)</h3>")
        partes.append("<table border='1' cellpadding='6' style='border-collapse:collapse; width:100%;'>")
        partes.append("<tr style='background:#f3f4f6;'><th style='text-align:left;'>Item</th><th>Status</th><th>Prioridade</th><th>Peso</th></tr>")
        for item in itens_cat:
            status = item.get("status_antes")
            status_label = _STATUS_LABELS.get(status, "—")
            prioridade = item.get("prioridade", "—")
            partes.append(
                f"<tr>"
                f"<td style='text-align:left;'>{escape(item.get('nome', item.get('slug', '—')))}</td>"
                f"<td style='text-align:center;'>{escape(status_label)}</td>"
                f"<td style='text-align:center;'>{escape(prioridade)}</td>"
                f"<td style='text-align:center;'>{item.get('peso', '—')}</td>"
                f"</tr>"
            )
        partes.append("</table>")

    # 5. Diagnósticos e Recomendações (apenas itens com conteúdo)
    com_conteudo = [i for i in itens if i.get("diagnostico") or i.get("recomendacao")]
    if com_conteudo:
        partes.append("<h2>Diagnósticos e Recomendações</h2>")
        for item in com_conteudo:
            nome = escape(item.get("nome", item.get("slug", "—")))
            status = _STATUS_LABELS.get(item.get("status_antes"), "—")
            partes.append(f"<h3>{nome} <em style='color:#6b7280;'>({status})</em></h3>")
            if item.get("diagnostico"):
                partes.append("<p><strong>Diagnóstico:</strong></p>")
                partes.append(f"<p>{escape(item['diagnostico']).replace(chr(10), '<br/>')}</p>")
            if item.get("recomendacao"):
                partes.append("<p><strong>Recomendação:</strong></p>")
                partes.append(f"<p>{escape(item['recomendacao']).replace(chr(10), '<br/>')}</p>")
            if item.get("observacao_seo"):
                partes.append(f"<p><em>Obs. SEO:</em> {escape(item['observacao_seo'])}</p>")

    return "\n".join(partes)
