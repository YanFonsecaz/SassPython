"""Regras custom do motor SEOTEC — funções nomeadas referenciadas por `regra.funcao`.

Assinatura obrigatória: (item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem.
"""
import re
from urllib.parse import urlsplit

from app.services.seotec_checklist import ItemChecklist
from app.services.seotec_ingestao import ExportNormalizado, PacoteIngestao
from app.services.seotec_motor import MAX_AMOSTRA, ResultadoItem, _montar_amostra

_RE_IMAGEM_GENERICA = re.compile(
    r"(?i)^(img|dsc|image|screenshot|whatsapp[- ]image)[-_ ]?\d|^\d+\.(jpe?g|png|webp|gif)$"
)


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
    if not export.linhas:
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


def uso_tipo_schema(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    """Verifica se algum recurso structured_data usa o `tipo` parametrizado.

    Nunca reprova: ausência do tipo é apenas atenção (o usuário rebaixa p/ n/a
    quando o tipo simplesmente não se aplica ao site).
    """
    export = pacote.exports.get("structured_data")
    if export is None:
        return ResultadoItem(status="sem_dados")
    tipo = (item.regra.parametros if item.regra else {}).get("tipo")
    linhas = export.linhas
    total_avaliadas = len(linhas)
    presente = any(tipo in (li.get("tipos") or []) for li in linhas)
    if presente:
        return ResultadoItem(status="aprovado", total_avaliadas=total_avaliadas)
    return ResultadoItem(status="atencao", total_avaliadas=total_avaliadas, total_afetadas=0, amostra=[])


def _base_www(host: str) -> tuple[str, bool]:
    """Retorna (domínio-base, tinha_www) a partir de um host."""
    host = (host or "").lower()
    if host.startswith("www."):
        return host[4:], True
    return host, False


def www_vs_non_www(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("internal")
    if export is None:
        return ResultadoItem(status="sem_dados")
    linhas = export.linhas
    por_base: dict[str, dict[str, list[dict]]] = {}
    for li in linhas:
        host = urlsplit(li.get("address") or "").hostname or ""
        if not host:
            continue
        base, tinha_www = _base_www(host)
        lado = "www" if tinha_www else "non_www"
        por_base.setdefault(base, {"www": [], "non_www": []})[lado].append(li)
    afetadas: list[dict] = []
    for lados in por_base.values():
        if lados["www"] and lados["non_www"]:
            minoritario = lados["www"] if len(lados["www"]) <= len(lados["non_www"]) else lados["non_www"]
            afetadas.extend(minoritario)
    return _resultado_lista(item, linhas, afetadas, export)


def trailing_slash_misto(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("internal")
    if export is None:
        return ResultadoItem(status="sem_dados")
    linhas = export.linhas
    por_endereco: dict[str, list[dict]] = {}
    for li in linhas:
        address = (li.get("address") or "").strip()
        if address:
            por_endereco.setdefault(address, []).append(li)
    afetadas: list[dict] = []
    vistos: set[str] = set()
    for address in por_endereco:
        if address in vistos:
            continue
        sem_barra = address[:-1] if address.endswith("/") else address
        com_barra = sem_barra + "/"
        path = urlsplit(sem_barra).path
        if path in ("", "/"):
            continue
        if sem_barra in por_endereco and com_barra in por_endereco:
            vistos.add(sem_barra)
            vistos.add(com_barra)
            afetadas.extend(por_endereco[sem_barra])
            afetadas.extend(por_endereco[com_barra])
    return _resultado_lista(item, linhas, afetadas, export)


def case_sensitive_urls(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    export = pacote.exports.get("internal")
    if export is None:
        return ResultadoItem(status="sem_dados")
    linhas = export.linhas
    grupos: dict[str, dict[str, list[dict]]] = {}
    for li in linhas:
        address = li.get("address") or ""
        grupos.setdefault(address.lower(), {}).setdefault(address, []).append(li)
    afetadas: list[dict] = []
    for variantes in grupos.values():
        if len(variantes) > 1:
            for lst in variantes.values():
                afetadas.extend(lst)
    return _resultado_lista(item, linhas, afetadas, export)


def imagens_nome_generico(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    """Sinaliza imagens com nome de arquivo genérico. Nunca ultrapassa `atencao`."""
    export = pacote.exports.get("images")
    if export is None:
        return ResultadoItem(status="sem_dados")
    linhas = export.linhas
    afetadas = []
    for li in linhas:
        nome = urlsplit(li.get("address") or "").path.rsplit("/", 1)[-1]
        if _RE_IMAGEM_GENERICA.search(nome):
            afetadas.append(li)
    resultado = _resultado_lista(item, linhas, afetadas, export)
    if resultado.status == "reprovado":
        resultado = resultado.model_copy(update={"status": "atencao"})
    return resultado
