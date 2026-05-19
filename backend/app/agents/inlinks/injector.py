import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_MAX_INLINKS = 8
_MIN_DISTANCE_WORDS = 100
_MIN_PARAGRAPH_WORDS = 10
_CONTEXTO_CHARS = 90

_HEADING_RE = re.compile(r"^\s*#{1,6}\s")


def _esta_em_cabecalho(texto: str, offset: int) -> bool:
    inicio_linha = texto.rfind("\n", 0, offset) + 1
    fim_linha = texto.find("\n", offset)
    if fim_linha < 0:
        fim_linha = len(texto)
    linha = texto[inicio_linha:fim_linha]
    return bool(_HEADING_RE.match(linha))


@dataclass
class InlinkInjetado:
    url_destino: str
    anchor_text: str
    paragrafo_idx: int
    offset_chars: int
    score_total: float
    score_semantico: float
    score_contexto: float
    status: str = "aplicado"
    motivo_rejeicao: str | None = None
    trecho_contexto: str | None = None
    titulo_destino: str | None = None
    motivo_contexto: str | None = None
    categoria_match: str | None = None
    motivo_sugestao: str | None = None


def _find_paragraph_index(paragrafos: list[str], char_offset: int) -> int:
    cumlen = 0
    for i, para in enumerate(paragrafos):
        cumlen += len(para) + 2
        if cumlen >= char_offset:
            return i
    return max(0, len(paragrafos) - 1)


def _word_position(text: str, char_offset: int) -> int:
    return len(text[:char_offset].split())


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


def _build_tolerant_pattern(anchor: str) -> re.Pattern[str]:
    """Pattern that tolerates accent variations and simple plural ('s' suffix).

    Matches across word characters as a unit, anchored with word boundaries so it
    won't cut a longer word mid-token.
    """
    folded = _strip_accents(anchor)
    parts = re.split(r"(\s+)", folded)
    rebuilt: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.isspace():
            rebuilt.append(r"\s+")
        else:
            rebuilt.append(re.escape(p) + r"s?")
    pattern = r"\b" + "".join(rebuilt) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


def _search_tolerant(haystack: str, anchor: str, start_from: int = 0) -> tuple[int, int, str] | None:
    if not anchor or len(anchor.strip()) < 3:
        return None

    folded_haystack = _strip_accents(haystack)
    if len(folded_haystack) != len(haystack):
        pattern = re.compile(re.escape(anchor), re.IGNORECASE)
        m = pattern.search(haystack, start_from)
        if not m:
            return None
        return m.start(), m.end(), m.group()

    pattern = _build_tolerant_pattern(anchor)
    m = pattern.search(folded_haystack, start_from)
    if not m:
        return None
    start, end = m.start(), m.end()
    return start, end, haystack[start:end]


def _categoria_match(score_semantico: float, score_contexto: float, score_total: float) -> str:
    if score_semantico >= 0.8:
        return "alta_similaridade"
    if score_contexto > score_semantico + 0.1 and score_total >= 0.55:
        return "complemento_contextual"
    if score_total >= 0.7 or score_semantico >= 0.65:
        return "boa_similaridade"
    return "similaridade_media"


def _extrair_trecho_contexto(texto: str, start: int, end: int) -> str:
    ini = max(0, start - _CONTEXTO_CHARS)
    fim = min(len(texto), end + _CONTEXTO_CHARS)
    prefixo = "…" if ini > 0 else ""
    sufixo = "…" if fim < len(texto) else ""
    antes = texto[ini:start]
    ancora = texto[start:end]
    depois = texto[end:fim]
    return f"{prefixo}{antes}«{ancora}»{depois}{sufixo}".replace("\n", " ").strip()


def injetar_inlinks(
    pilar_markdown: str,
    candidatos: list[dict[str, Any]],
    max_inlinks: int = _MAX_INLINKS,
) -> tuple[str, list[InlinkInjetado]]:
    if not pilar_markdown.strip():
        return pilar_markdown, []

    candidatos_ordenados = sorted(
        candidatos, key=lambda x: x.get("score_total", 0), reverse=True
    )
    candidatos_ordenados = candidatos_ordenados[:max_inlinks]

    substituicoes: list[dict[str, Any]] = []
    substituicoes_sugestao: list[dict[str, Any]] = []
    posicoes_ocupadas: list[tuple[int, int]] = []

    for c in candidatos_ordenados:
        ancoras = c.get("ancoras_opcoes", [c.get("titulo", "")])
        url = c["url"]
        if not ancoras or not url:
            continue

        match_info = None
        teve_match_em_heading = False

        for anchor in ancoras:
            if not anchor:
                continue
            search_from = 0
            while True:
                hit = _search_tolerant(pilar_markdown, anchor, start_from=search_from)
                if not hit:
                    break
                start, end, matched_text = hit
                if _esta_em_cabecalho(pilar_markdown, start):
                    teve_match_em_heading = True
                    search_from = end
                    continue
                match_info = {
                    "url": url,
                    "anchor": anchor,
                    "start": start,
                    "end": end,
                    "matched_text": matched_text,
                    "score_total": c.get("score_total", 0),
                    "score_semantico": c.get("score_semantico", 0),
                    "score_contexto": c.get("score_contexto", 0),
                    "titulo_destino": c.get("titulo", ""),
                    "motivo_contexto": c.get("motivo_contexto", ""),
                }
                break
            if match_info:
                break

        if not match_info:
            if teve_match_em_heading:
                substituicoes_sugestao.append({
                    "url": url,
                    "titulo_destino": c.get("titulo", ""),
                    "ancoras_opcoes": [a for a in ancoras if a],
                    "score_total": c.get("score_total", 0),
                    "score_semantico": c.get("score_semantico", 0),
                    "score_contexto": c.get("score_contexto", 0),
                    "motivo_contexto": c.get("motivo_contexto", ""),
                    "motivo_sugestao": "As âncoras propostas só aparecem em cabeçalhos. Reescreva um parágrafo do pilar para incluir o termo e linkar manualmente.",
                })
            continue

        start = match_info["start"]
        end = match_info["end"]

        overlaps = any(
            start < existing_end and end > existing_start
            for existing_start, existing_end in posicoes_ocupadas
        )
        if overlaps:
            continue

        word_pos = _word_position(pilar_markdown, start)
        too_close = False
        for es, _ee in posicoes_ocupadas:
            existing_word_pos = _word_position(pilar_markdown, es)
            if abs(word_pos - existing_word_pos) < _MIN_DISTANCE_WORDS:
                too_close = True
                break
        if too_close:
            continue

        match_info["trecho_contexto"] = _extrair_trecho_contexto(
            pilar_markdown, start, end
        )

        posicoes_ocupadas.append((start, end))
        substituicoes.append(match_info)

    substituicoes.sort(key=lambda x: x["start"], reverse=True)

    texto = pilar_markdown
    for s in substituicoes:
        link = f"[{s['matched_text']}]({s['url']})"
        texto = texto[: s["start"]] + link + texto[s["end"] :]

    paragrafos = [p for p in texto.split("\n\n") if p.strip()]

    injetados = []
    for s in sorted(substituicoes, key=lambda x: x["start"]):
        para_idx = _find_paragraph_index(paragrafos, s["start"])
        injetados.append(
            InlinkInjetado(
                url_destino=s["url"],
                anchor_text=s["matched_text"],
                paragrafo_idx=para_idx,
                offset_chars=s["start"],
                score_total=s["score_total"],
                score_semantico=s["score_semantico"],
                score_contexto=s["score_contexto"],
                trecho_contexto=s.get("trecho_contexto"),
                titulo_destino=s.get("titulo_destino") or None,
                motivo_contexto=s.get("motivo_contexto") or None,
                categoria_match=_categoria_match(
                    s["score_semantico"], s["score_contexto"], s["score_total"]
                ),
            )
        )

    for s in substituicoes_sugestao:
        injetados.append(
            InlinkInjetado(
                url_destino=s["url"],
                anchor_text=s["ancoras_opcoes"][0] if s["ancoras_opcoes"] else "",
                paragrafo_idx=0,
                offset_chars=0,
                score_total=s["score_total"],
                score_semantico=s["score_semantico"],
                score_contexto=s["score_contexto"],
                status="sugestao_manual",
                titulo_destino=s.get("titulo_destino") or None,
                motivo_contexto=s.get("motivo_contexto") or None,
                motivo_sugestao=s.get("motivo_sugestao"),
                categoria_match=_categoria_match(
                    s["score_semantico"], s["score_contexto"], s["score_total"]
                ),
            )
        )

    return texto, injetados


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
