"""Regras custom do motor SEOTEC — funções nomeadas referenciadas por `regra.funcao`.

Assinatura obrigatória: (item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem.
"""
from app.services.seotec_checklist import ItemChecklist
from app.services.seotec_ingestao import ExportNormalizado, PacoteIngestao
from app.services.seotec_motor import MAX_AMOSTRA, ResultadoItem, _montar_amostra


def _colunas(item: ItemChecklist) -> list[str]:
    return item.evidencia.colunas if item.evidencia else []


def _export_redirects(pacote: PacoteIngestao) -> ExportNormalizado | None:
    """Retorna o export de redirects, ou None se ausente."""
    return pacote.exports.get("redirects")


def _resultado_lista(
    item: ItemChecklist,
    todas: list[dict],
    afetadas: list[dict],
    export: ExportNormalizado | None = None,
) -> ResultadoItem:
    n = len(afetadas)
    colunas = _colunas(item)
    amostra = _montar_amostra(afetadas, colunas)
    total_avaliadas = export.total_antes_corte if export else len(todas)
    return ResultadoItem(
        status="aprovado" if n == 0 else "reprovado",
        total_avaliadas=total_avaliadas,
        total_afetadas=n,
        amostra=amostra,
        truncada=len(afetadas) > MAX_AMOSTRA,
    )


def cadeias_redirecionamento(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = _export_redirects(pacote)
    if export is None:
        return ResultadoItem(status="sem_dados")
    afetadas = [li for li in export.linhas if (li.get("num_hops") or 0) > 1 and not li.get("loop")]
    return _resultado_lista(item, export.linhas, afetadas, export)


def loops_redirecionamento(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = _export_redirects(pacote)
    if export is None:
        return ResultadoItem(status="sem_dados")
    afetadas = [li for li in export.linhas if li.get("loop")]
    return _resultado_lista(item, export.linhas, afetadas, export)


def title_igual_h1(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    titles = pacote.exports.get("page_titles")
    h1s = pacote.exports.get("h1")
    if titles is None or h1s is None:
        return ResultadoItem(status="sem_dados")
    h1_por_url = {li.get("address"): (li.get("h1") or "") for li in h1s.linhas}
    afetadas = []
    for li in titles.linhas:
        title = (li.get("title") or "").strip().lower()
        h1 = h1_por_url.get(li.get("address"), "").strip().lower()
        if title and h1 and title == h1:
            afetadas.append({**li, "h1": h1_por_url[li.get("address")]})
    return _resultado_lista(item, titles.linhas, afetadas, titles)


def sitemap_otimizado(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("sitemaps")
    if export is None:
        return ResultadoItem(status="sem_dados")
    afetadas = [
        li for li in export.linhas
        if li.get("status_code") != 200 or (li.get("total_urls") or 0) > 50000 or (li.get("total_urls") or 0) == 0
    ]
    return _resultado_lista(item, export.linhas, afetadas, export)


def pagina_404_adequada(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("pagina_404")
    if export is None:
        return ResultadoItem(status="sem_dados")
    linha = export.linhas[0] if export.linhas else {}
    aprovado = linha.get("status_code") == 404 and not linha.get("soft_404")
    afetadas = [] if aprovado else [linha]
    return _resultado_lista(item, export.linhas, afetadas, export)


def metas_no_head(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    titles = pacote.exports.get("page_titles")
    metas = pacote.exports.get("meta_description")
    if titles is None or metas is None:
        return ResultadoItem(status="sem_dados")
    meta_por_url = {li.get("address"): (li.get("meta_description") or "") for li in metas.linhas}
    afetadas = []
    for li in titles.linhas:
        title = (li.get("title") or "").strip()
        meta = meta_por_url.get(li.get("address"), "").strip()
        if not title and not meta:
            afetadas.append(li)
    return _resultado_lista(item, titles.linhas, afetadas, titles)


def hierarquia_headings(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("h1")
    if export is None:
        return ResultadoItem(status="sem_dados")
    if not any(li.get("h2_ocorrencias") is not None for li in export.linhas):
        return ResultadoItem(status="sem_dados")
    afetadas = [
        li for li in export.linhas
        if not (li.get("h1") or "") and (li.get("h2_ocorrencias") or 0) > 0
    ]
    return _resultado_lista(item, export.linhas, afetadas, export)
