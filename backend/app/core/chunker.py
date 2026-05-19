import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MAX_TOKENS = 800
_OVERLAP_TOKENS = 100


@dataclass
class Chunk:
    texto: str
    tokens: int
    ordem: int


def chunk_texto(texto: str, max_tokens: int = _MAX_TOKENS, overlap: int = _OVERLAP_TOKENS) -> list[Chunk]:
    paragrafos = texto.split("\n\n")
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_tokens = 0
    ordem = 0

    for paragrafo in paragrafos:
        p_tokens = _estimate_tokens(paragrafo)
        if p_tokens == 0:
            continue

        if buffer_tokens + p_tokens > max_tokens and buffer:
            chunk_text = "\n\n".join(buffer)
            chunks.append(Chunk(texto=chunk_text, tokens=buffer_tokens, ordem=ordem))
            ordem += 1

            overlap_text = chunks[-1].texto
            overlap_words = overlap_text.split()
            overlap_part = " ".join(overlap_words[-overlap:]) if len(overlap_words) > overlap else overlap_text

            buffer = [overlap_part, paragrafo]
            buffer_tokens = _estimate_tokens(overlap_part) + p_tokens
        else:
            buffer.append(paragrafo)
            buffer_tokens += p_tokens

    if buffer:
        chunk_text = "\n\n".join(buffer)
        chunks.append(Chunk(texto=chunk_text, tokens=buffer_tokens, ordem=ordem))

    return chunks


def _estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)
