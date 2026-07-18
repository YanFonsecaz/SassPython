"""Regras custom do motor SEOTEC — funções nomeadas referenciadas por `regra.funcao`.

Assinatura obrigatória: (item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem.
"""
from app.services.seotec_checklist import ItemChecklist
from app.services.seotec_ingestao import PacoteIngestao
from app.services.seotec_motor import ResultadoItem, _montar_amostra


def _colunas(item: ItemChecklist) -> list[str]:
    return item.evidencia.colunas if item.evidencia else []


def _resultado_lista(item: ItemChecklist, todas: list[dict], afetadas: list[dict]) -> ResultadoItem:
    n = len(afetadas)
    return ResultadoItem(
        status="aprovado" if n == 0 else "reprovado",
        total_avaliadas=len(todas),
        total_afetadas=n,
        amostra=_montar_amostra(afetadas, _colunas(item)),
        truncada=n > len(_montar_amostra(afetadas, _colunas(item))),
    )


def cadeias_redirecionamento(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("redirects")
    if export is None:
        return ResultadoItem(status="sem_dados")
    afetadas = [li for li in export.linhas if (li.get("num_hops") or 0) > 1 and not li.get("loop")]
    return _resultado_lista(item, export.linhas, afetadas)


def loops_redirecionamento(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("redirects")
    if export is None:
        return ResultadoItem(status="sem_dados")
    afetadas = [li for li in export.linhas if li.get("loop")]
    return _resultado_lista(item, export.linhas, afetadas)


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
    return _resultado_lista(item, titles.linhas, afetadas)
