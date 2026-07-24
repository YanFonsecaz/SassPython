"""Detecção de plataforma SEOTec (SPEC_SEOTEC_Agentes_IA §2).

SEOTec não tem payload Lighthouse (como o CWV), então reusa os MESMOS
marcadores de URL do CWV (``services/cwv_plataforma.py URL_SIGNATURES``)
escaneando as URLs do export ``internal``. Detecção por consenso: a plataforma
que aparecer em mais URLs vence.

Retorna o tipo ``Plataforma`` da KB de soluções (``geral`` quando nenhum
marcador casa ou o empate/desconhecido). Mapeia ``outros``/``desconhecida`` do
CWV para ``geral`` (a KB só tem variações para plataformas concretas).
"""
from collections import Counter

from app.services.cwv_plataforma import URL_SIGNATURES
from app.services.seotec_ingestao import PacoteIngestao


def _normalizar(plataforma_cwv: str) -> str:
    """CWV usa 'outros'/'desconhecida'; a KB de soluções trata como 'geral'."""
    if plataforma_cwv in ("outros", "desconhecida"):
        return "geral"
    return plataforma_cwv


def detectar_plataforma(pacote: PacoteIngestao) -> str:
    """Detecta a plataforma do site escaneando as URLs internas.

    Fail-open: retorna ``"geral"`` quando o export ``internal`` está ausente/vazio
    ou nenhum marcador casa (a KB cai na recomendação canônica).
    """
    export = pacote.exports.get("internal")
    if export is None or not export.linhas:
        return "geral"

    contagem: Counter[str] = Counter()
    for linha in export.linhas:
        url = str(linha.get("address") or "")
        if not url:
            continue
        url_lower = url.lower()
        for marcador, plataforma in URL_SIGNATURES:
            if marcador.lower() in url_lower:
                contagem[plataforma] += 1
                break  # 1 voto por URL (marcador mais específico já vem primeiro)

    if not contagem:
        return "geral"

    vencedora = contagem.most_common(1)[0][0]
    return _normalizar(vencedora)
