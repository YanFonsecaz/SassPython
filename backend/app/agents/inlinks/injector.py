import logging
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)

_CONTEXTO_CHARS = 90

_HEADING_RE = re.compile(r"^\s*#{1,6}\s")


def _esta_em_cabecalho(texto: str, offset: int) -> bool:
    inicio_linha = texto.rfind("\n", 0, offset) + 1
    fim_linha = texto.find("\n", offset)
    if fim_linha < 0:
        fim_linha = len(texto)
    linha = texto[inicio_linha:fim_linha]
    return bool(_HEADING_RE.match(linha))


def _strip_accents(s: str) -> str:
    """Remove diacritics keeping per-character positions stable.

    NFD (not NFKD) avoids decomposing ligatures and compatibility chars, so
    `len(_strip_accents(s)) == len(s)` for the precomposed Latin text we
    typically deal with — letting offsets in the folded string map directly
    back to the original.
    """
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)
    )


def _categoria_match(score_semantico: float, score_contexto: float, score_total: float) -> str:
    if score_semantico >= 0.8:
        return "alta_similaridade"
    if score_contexto > score_semantico + 0.1 and score_total >= 0.55:
        return "complemento_contextual"
    if score_total >= 0.7 or score_semantico >= 0.65:
        return "boa_similaridade"
    return "similaridade_media"


# SPEC_Inlinks_Badges_Pela_Decisao_Do_Juiz: a categoria da badge deriva da
# DECISÃO do juiz (status + confiança), não de cortes de cosine. Quem decidiu
# a qualidade foi o juiz; o cosine é só um detalhe secundário na UI.
# Thresholds 0.85/0.70 são chute inicial calibrável com o golden set do eval.
def _categoria_match_por_decisao(status: str, confianca: float | None, *, cta: bool = False) -> str:
    if cta:
        # Link deliberado (não inferido): casa como conexão sólida.
        return "boa_similaridade"
    if status == "sugestao_manual":
        return "similaridade_media"
    if status == "rejeitado":
        return "similaridade_media"
    # status == "aplicado" — decide pela confiança do juiz. Sem confiança
    # registrada, trata como baixa (pede revisão) — nunca assume "forte".
    if confianca is None:
        return "complemento_contextual"
    if confianca >= 0.85:
        return "alta_similaridade"
    if confianca >= 0.70:
        return "boa_similaridade"
    return "complemento_contextual"


def _extrair_trecho_contexto(texto: str, start: int, end: int) -> str:
    ini = max(0, start - _CONTEXTO_CHARS)
    fim = min(len(texto), end + _CONTEXTO_CHARS)
    prefixo = "…" if ini > 0 else ""
    sufixo = "…" if fim < len(texto) else ""
    antes = texto[ini:start]
    ancora = texto[start:end]
    depois = texto[end:fim]
    return f"{prefixo}{antes}«{ancora}»{depois}{sufixo}".replace("\n", " ").strip()


def remover_links_rejeitados(pilar_modificado: str, inlinks_revisados: list[dict[str, Any]]) -> str:
    texto = pilar_modificado
    for il in inlinks_revisados:
        if il.get("status") == "aplicado":
            continue
        ancora = il.get("anchor_text") or ""
        url = il.get("url_destino") or ""
        if not ancora or not url:
            continue
        marca = f"[{ancora}]({url})"
        texto = texto.replace(marca, ancora, 1)
    return texto
