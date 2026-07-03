import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.agents.inlinks.injector import (
    _categoria_match,
    _esta_em_cabecalho,
    _extrair_trecho_contexto,
    _strip_accents,
)
from app.core.embeddings import cosine_seguro, gerar_embeddings_batch

logger = logging.getLogger(__name__)

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

_MIN_DISTANCE_WORDS_BASE = 100
_MAX_CONECTOR_WORDS = 3
_TOP_N_PARAGRAFOS = 8
_MAX_PARAGRAFOS_CONTEXTO = 12
_MIN_PARAGRAFO_CHARS = 80
# Pisos de cosine usados APENAS no modo legado (aplicar_pisos_legado=True).
# No modo padrão o LLM juiz decide; os cosines viram sinais registrados.
_MIN_INSERCAO_SEMANTICA = 0.50
_MIN_INSERCAO_SEMANTICA_KW_VALIDA = 0.35
_MIN_ANCORA_TITULO = 0.35
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s")
_CODE_FENCE_RE = re.compile(r"^\s*```")

_STOPWORDS_GENERICAS = {
    "abrir", "fazer", "criar", "montar", "começar", "comecar", "iniciar", "ter", "ser", "estar",
    "ir", "vir", "saber", "conhecer", "ver",
    "negócio", "negocio", "empresa", "negócios", "negocios", "empresas",
    "investimento", "investimentos", "dinheiro", "lucro", "ganhar", "renda",
    "guia", "passos", "dicas", "tipo", "tipos", "opção", "opcao", "opções", "opcoes",
    "como", "qual", "quais", "que", "tudo", "completo", "completa", "ideal", "melhor",
    "novo", "nova", "pratico", "prático",
}


class DecisaoInsercaoSchema(BaseModel):
    decisao: str = Field(
        description=(
            "aplicar = existe ancora natural e tema relacionado; "
            "sugerir = tema relacionado mas sem ancora natural no texto atual; "
            "descartar = sem relacao tematica real"
        )
    )
    paragrafo_idx: int = Field(default=-1, description="Indice LOCAL do paragrafo (0..N-1); -1 se descartar")
    trecho_original: str = Field(default="", description="2-6 palavras CONTINUAS copiadas EXATAMENTE do paragrafo")
    anchor_text: str = Field(default="", description="Texto da ancora; por padrao igual ao trecho_original")
    conector_antes: str = Field(default="")
    conector_depois: str = Field(default="")
    confianca: float = Field(default=0.5, description="Confianca na decisao, de 0.0 a 1.0")
    motivo: str = Field(
        default="",
        description="1 frase clara e legivel para usuario leigo explicando a decisao. OBRIGATORIO.",
    )


def _normalize_token(s: str) -> str:
    return _strip_accents(s.lower())


def _contem_termo(haystack: str, needle: str) -> bool:
    if not haystack or not needle or len(needle.strip()) < 2:
        return False
    return _normalize_token(needle) in _normalize_token(haystack)


def _calcular_min_distance(pilar_markdown: str, max_inlinks: int) -> int:
    n_palavras = len(pilar_markdown.split())
    if max_inlinks <= 0:
        return _MIN_DISTANCE_WORDS_BASE
    distancia = max(50, min(200, n_palavras // (max_inlinks * 2)))
    return distancia


def _texto_destino(candidato: dict[str, Any]) -> str:
    titulo = candidato.get("titulo", "") or ""
    resumo = candidato.get("resumo", "") or ""
    if resumo.strip():
        return f"{titulo} {resumo[:300]}"

    categoria = candidato.get("categoria", "") or ""
    palavras = candidato.get("palavras_chave", []) or []
    palavras_str = ", ".join(palavras[:10]) if isinstance(palavras, list) else str(palavras)
    fallback = " ".join(filter(None, [titulo, categoria, palavras_str]))
    return fallback or titulo

_CONECTOR_REDUNDANTE_RE = re.compile(
    r"\b(veja|leia|confira|saiba|assista|descubra|entenda|sobre|em|no|na)\b",
    re.IGNORECASE,
)


def _ha_conector_no_entorno(paragrafo: str, local_offset: int) -> bool:
    janela = paragrafo[max(0, local_offset - 30):local_offset]
    return bool(_CONECTOR_REDUNDANTE_RE.search(janela))


def _paragrafo_elegivel(p: str) -> bool:
    stripped = p.strip()
    if len(stripped) < _MIN_PARAGRAFO_CHARS:
        return False
    if stripped.startswith("#"):
        return False
    if _LIST_ITEM_RE.match(stripped):
        return False
    return not _CODE_FENCE_RE.match(stripped)


@dataclass
class InlinkInserido:
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
    trecho_original: str | None = None
    conector_antes: str | None = None
    conector_depois: str | None = None
    ancora_preferida_usada: bool = False
    confianca: float | None = None
    sinal_cos_contexto: float | None = None
    sinal_cos_ancora: float | None = None


async def _gerar_cta_fallback(
    paragrafos: list[str],
    paragrafos_embeddings: list[Any],
    candidato: dict[str, Any],
    ancora: str,
    usuario_id: str,
) -> dict[str, Any] | None:
    consulta = _texto_destino(candidato)[:1500]
    emb_consulta_lst = await gerar_embeddings_batch([consulta], usuario_id)
    emb_consulta = emb_consulta_lst[0] if emb_consulta_lst else None
    if emb_consulta is None:
        return None

    scored: list[tuple[int, str, float]] = []
    for i, (p, emb_p) in enumerate(zip(paragrafos, paragrafos_embeddings, strict=False)):
        if emb_p is None or not _paragrafo_elegivel(p):
            continue
        if "leia também:" in p.lower() or p.strip().endswith(">"):
            continue
        cosine = cosine_seguro(emb_consulta, emb_p)
        scored.append((i, p, float(cosine)))

    if not scored:
        return None

    scored.sort(key=lambda x: x[2], reverse=True)
    p_idx, _paragrafo, cos = scored[0]
    if cos < 0.55:
        return None

    return {
        "url_destino": candidato["url"],
        "paragrafo_idx": p_idx,
        "anchor_text": ancora,
        "trecho_original": "",
        "_modo_cta": True,
        "_ancora_cta": ancora,
        "justificativa": (
            f"Nenhuma âncora natural coube no texto atual. "
            f"CTA adicionado no fim do parágrafo {p_idx} (cosine={cos:.2f})."
        ),
    }


async def inserir_inlinks(
    pilar_markdown: str,
    candidatos: list[dict[str, Any]],
    usuario_id: str,
    max_inlinks: int = 8,
    ancoras_preferidas: list[str] | None = None,
    permitir_cta_fallback: bool = True,
    objetivo_linkagem: str | None = None,
    aplicar_pisos_legado: bool = False,
) -> tuple[str, list[InlinkInserido]]:
    if not pilar_markdown.strip() or not candidatos:
        return pilar_markdown, []

    pilar_markdown = re.sub(r"\n{3,}", "\n\n", pilar_markdown)
    paragrafos = pilar_markdown.split("\n\n")
    candidatos_top = sorted(
        candidatos, key=lambda c: c.get("score_total", 0), reverse=True
    )[:max_inlinks]

    textos_paragrafos = [p[:2000] for p in paragrafos]
    paragrafos_embeddings = await gerar_embeddings_batch(
        textos_paragrafos, usuario_id
    )

    todas_insercoes: list[dict[str, Any]] = []

    async def _processar_candidato(c: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        contexto_paragrafos = await _selecionar_paragrafos_relevantes(
            paragrafos,
            c,
            paragrafos_embeddings,
            usuario_id,
            ancoras_preferidas=ancoras_preferidas,
        )
        if not contexto_paragrafos:
            logger.info("Inseridor: candidato %s sem parágrafos elegíveis", c.get("url"))
            return (c, None)

        proposta = await _propor_insercao_para_candidato(
            c, contexto_paragrafos, usuario_id,
            ancoras_preferidas=ancoras_preferidas,
            objetivo_linkagem=objetivo_linkagem,
        )
        return (c, proposta)

    propostas_por_candidato: list[tuple[dict[str, Any], dict[str, Any] | None]] = list(
        await asyncio.gather(*(_processar_candidato(c) for c in candidatos_top))
    )

    pares_para_validar: list[tuple[dict[str, Any], dict[str, Any]]] = []
    textos_batch: list[str] = []
    for c, proposta in propostas_por_candidato:
        if not proposta:
            continue
        if proposta.get("_inseridor_vazio") or proposta.get("_descartado"):
            todas_insercoes.append(proposta)
            continue
        p_idx = proposta.get("paragrafo_idx", -1)
        trecho = proposta.get("trecho_original", "")
        anchor = proposta.get("anchor_text") or trecho
        paragrafo = paragrafos[p_idx] if 0 <= p_idx < len(paragrafos) else ""
        contexto = f"{trecho} {paragrafo[:200]}"
        destino = _texto_destino(c)
        titulo = c.get("titulo", "") or ""

        pares_para_validar.append((c, proposta))
        textos_batch.append(contexto)
        textos_batch.append(destino)
        textos_batch.append(anchor)
        textos_batch.append(titulo)

    embs_batch: list[Any] = []
    if textos_batch:
        embs_batch = await gerar_embeddings_batch(textos_batch, usuario_id)

    # Cosines viram SINAIS registrados na proposta (funil/telemetria). Só decidem
    # status no modo legado (rollback do Distribuir via aplicar_pisos_legado).
    for i, (_c, proposta) in enumerate(pares_para_validar):
        emb_ctx = embs_batch[i * 4] if i * 4 < len(embs_batch) else None
        emb_dst = embs_batch[i * 4 + 1] if i * 4 + 1 < len(embs_batch) else None
        emb_anc = embs_batch[i * 4 + 2] if i * 4 + 2 < len(embs_batch) else None
        emb_tit = embs_batch[i * 4 + 3] if i * 4 + 3 < len(embs_batch) else None

        if emb_ctx is None or emb_dst is None:
            if aplicar_pisos_legado:
                proposta["forcar_sugestao_manual"] = True
                proposta["motivo_sugestao"] = "Não foi possível validar semanticamente (embedding indisponível)."
            todas_insercoes.append(proposta)
            continue

        cosine_contexto = cosine_seguro(emb_ctx, emb_dst)
        cosine_ancora = cosine_seguro(emb_anc, emb_tit) if (emb_anc is not None and emb_tit is not None) else 0.0
        proposta["sinal_cos_contexto"] = round(float(cosine_contexto), 3)
        proposta["sinal_cos_ancora"] = round(float(cosine_ancora), 3)

        if aplicar_pisos_legado:
            _aplicar_portoes_legado(proposta, cosine_contexto, cosine_ancora)
        todas_insercoes.append(proposta)

    # CTA fallback ("> Leia também:") quando o usuário optou e nenhuma proposta
    # natural sobreviveu. Sem âncoras preferidas, usa o título do destino.
    nenhuma_valida = not any(
        p for _, p in propostas_por_candidato
        if p
        and not p.get("forcar_sugestao_manual")
        and not p.get("_inseridor_vazio")
        and not p.get("_descartado")
    )
    if permitir_cta_fallback and nenhuma_valida and candidatos_top:
        ancora_cta = (
            ancoras_preferidas[0]
            if ancoras_preferidas
            else (candidatos_top[0].get("titulo") or "").strip()[:60]
        )
        if ancora_cta:
            cta_proposta = await _gerar_cta_fallback(
                paragrafos, paragrafos_embeddings, candidatos_top[0], ancora_cta, usuario_id,
            )
            if cta_proposta:
                todas_insercoes.append(cta_proposta)

    min_dist = _calcular_min_distance(pilar_markdown, max_inlinks)
    logger.info(
        "Inseridor: min_distance_words=%d (palavras=%d, max=%d)",
        min_dist, len(pilar_markdown.split()), max_inlinks,
    )
    texto, inseridos, colisoes = _aplicar_insercoes(
        pilar_markdown, paragrafos, candidatos_top, todas_insercoes,
        min_distance_words=min_dist,
        ancoras_preferidas=ancoras_preferidas,
        finalizar_colisoes=False,
    )

    if colisoes:
        # 1 retry por proposta que caiu apenas por proximidade de outro inlink:
        # re-julga excluindo do contexto TODO parágrafo dentro do raio de
        # min_distance das inserções aceitas (não só o parágrafo exato) —
        # senão o juiz escolhe o vizinho e colide de novo.
        candidatos_by_url = {c.get("url"): c for c in candidatos_top}
        inicio_palavras: list[int] = []
        pos = 0
        for p in paragrafos:
            inicio_palavras.append(pos)
            pos += len(p.split())
        posicoes_aceitas = [
            _word_position(texto, il.offset_chars)
            for il in inseridos if il.status == "aplicado"
        ]
        ocupados: set[int] = set()
        for idx, inicio in enumerate(inicio_palavras):
            fim = inicio + len(paragrafos[idx].split())
            if any(inicio - min_dist < ap < fim + min_dist for ap in posicoes_aceitas):
                ocupados.add(idx)
        substitutas: dict[int, dict[str, Any]] = {}
        for ins in colisoes:
            c = candidatos_by_url.get(ins.get("url_destino"))
            nova: dict[str, Any] | None = None
            if c and ocupados:
                contexto2 = await _selecionar_paragrafos_relevantes(
                    paragrafos, c, paragrafos_embeddings, usuario_id,
                    ancoras_preferidas=ancoras_preferidas,
                    excluir_idx=ocupados,
                )
                if contexto2:
                    nota = (
                        "ATENÇÃO: outros trechos deste artigo já receberam links próximos. "
                        "Escolha um parágrafo DIFERENTE dentre os fornecidos, ou responda "
                        'decisao="descartar" se nenhum servir.'
                    )
                    nova = await _propor_insercao_para_candidato(
                        c, contexto2, usuario_id,
                        ancoras_preferidas=ancoras_preferidas,
                        objetivo_linkagem=objetivo_linkagem,
                        nota_densidade=nota,
                    )
            if nova and not nova.get("_inseridor_vazio") and not nova.get("forcar_sugestao_manual"):
                substitutas[id(ins)] = nova
            else:
                substitutas[id(ins)] = {
                    **ins,
                    "forcar_sugestao_manual": True,
                    "motivo_sugestao": "Muito próximo de outro inlink (2 tentativas).",
                }
        insercoes_v2 = [substitutas.get(id(p), p) for p in todas_insercoes]
        texto, inseridos, _ = _aplicar_insercoes(
            pilar_markdown, paragrafos, candidatos_top, insercoes_v2,
            min_distance_words=min_dist,
            ancoras_preferidas=ancoras_preferidas,
            finalizar_colisoes=True,
        )

    return texto, inseridos


class _InseridorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings

        model = settings.inseridor_llm_model if settings.llm_provider == "openai" else None
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.inlinks_inseridor_temperature,
        )

    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage

        from app.core.llm_guard import chamada_llm_mensagem_com_retry

        response = await chamada_llm_mensagem_com_retry(
            self.llm, [HumanMessage(content=prompt)], self.usuario_id
        )
        return response.content


def _termos_keyword_destino(candidato: dict[str, Any]) -> list[str]:
    termos: list[str] = []
    palavras = candidato.get("palavras_chave") or []
    if isinstance(palavras, list):
        termos.extend(str(p).strip() for p in palavras if p and len(str(p).strip()) >= 3)
    titulo = candidato.get("titulo", "") or ""
    for t in titulo.split():
        t_clean = t.strip(",.:;!?()[]\"'").lower()
        if len(t_clean) >= 4 and _normalize_token(t_clean) not in _STOPWORDS_GENERICAS:
            termos.append(t_clean)
    vistos: set[str] = set()
    out: list[str] = []
    for t in termos:
        n = _normalize_token(t)
        if n in _STOPWORDS_GENERICAS or n in vistos or len(n) < 3:
            continue
        vistos.add(n)
        out.append(t)
    return out


def _aplicar_portoes_legado(
    proposta: dict[str, Any], cosine_contexto: float, cosine_ancora: float
) -> None:
    """Pisos de cosine pré-julgamento-único. Ativos apenas com aplicar_pisos_legado=True
    (rollback do Distribuir). Serão removidos quando o juiz único estiver validado."""
    if proposta.get("forcar_sugestao_manual"):
        return
    if cosine_contexto < _MIN_INSERCAO_SEMANTICA_KW_VALIDA:
        proposta["forcar_sugestao_manual"] = True
        proposta["motivo_sugestao"] = (
            f"Baixa relação semântica entre âncora e destino "
            f"(cos={cosine_contexto:.2f} < {_MIN_INSERCAO_SEMANTICA_KW_VALIDA:.2f})."
        )
    elif cosine_ancora < _MIN_ANCORA_TITULO:
        proposta["forcar_sugestao_manual"] = True
        proposta["motivo_sugestao"] = "Âncora genérica — não menciona termo específico do destino."


def _keyword_boost(paragrafo: str, termos: list[str]) -> float:
    if not termos or not paragrafo:
        return 0.0
    matches = sum(1 for t in termos if _contem_termo(paragrafo, t))
    if matches == 0:
        return 0.0
    return min(0.25, 0.08 * matches)


def _ancora_preferida_match(texto: str, ancoras: list[str]) -> str | None:
    if not texto or not ancoras:
        return None
    texto_norm = _strip_accents(texto.lower())
    for ancora in ancoras:
        ancora_norm = _strip_accents(ancora.lower())
        if ancora_norm in texto_norm:
            return ancora
        palavras = ancora_norm.split()
        if len(palavras) > 1 and all(p in texto_norm for p in palavras):
            return ancora
    return None


def _ancora_preferida_boost(paragrafo: str, ancoras: list[str]) -> float:
    if not ancoras or not paragrafo:
        return 0.0
    return 0.60 if _ancora_preferida_match(paragrafo, ancoras) else 0.0


def _link_existente_em(paragrafo: str, offset: int) -> str | None:
    if not paragrafo or offset < 0:
        return None
    for m in _MD_LINK_RE.finditer(paragrafo):
        if m.start() <= offset < m.end():
            return m.group(2)
    return None


async def _selecionar_paragrafos_relevantes(
    paragrafos: list[str],
    candidato: dict[str, Any],
    paragrafos_embeddings: list[Any],
    usuario_id: str,
    top_n: int = _TOP_N_PARAGRAFOS,
    ancoras_preferidas: list[str] | None = None,
    excluir_idx: set[int] | None = None,
) -> list[tuple[int, str]]:
    consulta = _texto_destino(candidato)[:1500]
    emb_consulta_lst = await gerar_embeddings_batch([consulta], usuario_id)
    emb_consulta = emb_consulta_lst[0] if emb_consulta_lst else None
    termos_kw = _termos_keyword_destino(candidato)
    excluir = excluir_idx or set()

    if emb_consulta is None:
        elegiveis = [
            (i, p) for i, p in enumerate(paragrafos)
            if _paragrafo_elegivel(p) and i not in excluir
        ]
        if termos_kw:
            scored_kw = [(i, p, _keyword_boost(p, termos_kw)) for i, p in elegiveis]
            scored_kw.sort(key=lambda x: x[2], reverse=True)
            return [(i, p) for i, p, _ in scored_kw[:top_n]]
        return elegiveis[:top_n]

    scored: list[tuple[int, str, float, float]] = []
    for i, (p, emb_p) in enumerate(zip(paragrafos, paragrafos_embeddings, strict=False)):
        if emb_p is None or not _paragrafo_elegivel(p) or i in excluir:
            continue
        cosine = cosine_seguro(emb_consulta, emb_p)
        boost = _keyword_boost(p, termos_kw)
        ap_boost = _ancora_preferida_boost(p, ancoras_preferidas) if ancoras_preferidas else 0.0
        scored.append((i, p, float(cosine) + boost + ap_boost, boost))

    scored.sort(key=lambda x: x[2], reverse=True)
    top = scored[:top_n]

    # Garantia de recall: parágrafos com match lexical de keyword do destino
    # entram no contexto mesmo fora do top-N por cosine (cap total).
    ja_incluidos = {i for i, _, _, _ in top}
    for i, p, s, b in scored[top_n:]:
        if len(top) >= _MAX_PARAGRAFOS_CONTEXTO:
            break
        if b > 0 and i not in ja_incluidos:
            top.append((i, p, s, b))
            ja_incluidos.add(i)

    if ancoras_preferidas:
        top.sort(key=lambda x: _ancora_preferida_match(x[1], ancoras_preferidas) is not None, reverse=True)

    n_kw_match = sum(1 for _, _, _, b in top if b > 0)
    logger.info(
        "Inseridor: %d parágrafos de contexto para %s — %d com keyword match (termos=%s)",
        len(top), candidato.get("url", "?")[-60:], n_kw_match,
        ", ".join(termos_kw[:5]),
    )
    return [(i, p) for i, p, _, _ in top]


async def _propor_insercao_para_candidato(
    candidato: dict[str, Any],
    contexto_paragrafos: list[tuple[int, str]],
    usuario_id: str,
    ancoras_preferidas: list[str] | None = None,
    objetivo_linkagem: str | None = None,
    nota_densidade: str | None = None,
) -> dict[str, Any] | None:
    """Julgamento único: o LLM decide aplicar/sugerir/descartar com contexto completo.

    Não há portão semântico depois desta decisão — apenas validações determinísticas
    (trecho literal, heading/lista, link duplicado, densidade) em _aplicar_insercoes.
    """
    agente = _InseridorAgent(usuario_id)
    prompt = _build_prompt_focado(
        candidato, contexto_paragrafos,
        ancoras_preferidas=ancoras_preferidas,
        objetivo_linkagem=objetivo_linkagem,
        nota_densidade=nota_densidade,
    )
    logger.info(
        "Inseridor: prompt para %s (%d chars, %d parágrafos)\n%s\n---END PROMPT---",
        candidato.get("url", "?"),
        len(prompt),
        len(contexto_paragrafos),
        prompt[:3000],
    )

    parsed: dict[str, Any] | None = None
    try:
        parsed_obj = await agente.invoke_structured(prompt, DecisaoInsercaoSchema)
        parsed = parsed_obj.model_dump()
    except Exception as e:
        logger.warning("Inseridor structured falhou para %s: %s; tentando fallback parsing", candidato.get("url"), e)
        try:
            resposta = await agente._invoke_llm(prompt)
            parsed = _parse_proposta_unica(resposta)
        except Exception as e2:
            logger.warning("Inseridor LLM fallback falhou para %s: %s", candidato.get("url"), e2)
            return None

    if not parsed:
        logger.warning("Inseridor: LLM não respondeu com decisão para %s.", candidato.get("url"))
        termos_kw = _termos_keyword_destino(candidato)
        motivo = (
            f"A IA não conseguiu avaliar este destino ({', '.join(termos_kw[:3]) or 'sem termos'}). "
            f"Revise manualmente se um link faz sentido."
        )
        return {
            "url_destino": candidato["url"],
            "anchor_text": "",
            "trecho_original": "",
            "paragrafo_idx": 0,
            "forcar_sugestao_manual": True,
            "motivo_sugestao": motivo,
            "_inseridor_vazio": True,
        }

    decisao = str(parsed.get("decisao") or "").strip().lower()
    motivo = (parsed.get("motivo") or parsed.get("justificativa") or "").strip()
    confianca = parsed.get("confianca")
    trecho = (parsed.get("trecho_original") or "").strip()

    if decisao == "descartar":
        return {
            "url_destino": candidato["url"],
            "anchor_text": "",
            "trecho_original": "",
            "paragrafo_idx": -1,
            "_descartado": True,
            "motivo_rejeicao": motivo or "Sem relação temática real entre o artigo e o destino.",
            "confianca": confianca,
        }

    if decisao == "sugerir" or not trecho:
        return {
            "url_destino": candidato["url"],
            "anchor_text": (parsed.get("anchor_text") or "").strip(),
            "trecho_original": trecho,
            "paragrafo_idx": 0,
            "forcar_sugestao_manual": True,
            "motivo_sugestao": motivo or (
                "Tema relacionado, mas nenhum trecho atual serve de âncora natural."
            ),
            "confianca": confianca,
        }

    idx_local = parsed.get("paragrafo_idx", -1)
    if not isinstance(idx_local, int) or not (0 <= idx_local < len(contexto_paragrafos)):
        logger.warning(
            "Inseridor: paragrafo_idx fora do contexto local (%s) para %s",
            idx_local, candidato.get("url"),
        )
        return None

    idx_global, paragrafo_completo = contexto_paragrafos[idx_local]
    parsed["paragrafo_idx"] = idx_global
    parsed["url_destino"] = candidato["url"]
    parsed["justificativa"] = motivo

    if ancoras_preferidas and parsed:
        ancora_no_paragrafo = _ancora_preferida_match(paragrafo_completo, ancoras_preferidas)
        anchor_llm = (parsed.get("anchor_text") or "").strip()
        if ancora_no_paragrafo and not _ancora_preferida_match(anchor_llm, ancoras_preferidas):
            parsed["anchor_text"] = ancora_no_paragrafo
            if ancora_no_paragrafo.lower() in paragrafo_completo.lower():
                parsed["trecho_original"] = ancora_no_paragrafo
            logger.info(
                "Inseridor: forcando anchor_text para ancora preferida '%s' (LLM havia escolhido '%s')",
                ancora_no_paragrafo, anchor_llm,
            )

    # Sinal informativo (não decide status): a âncora menciona termo do destino?
    termos_kw = _termos_keyword_destino(candidato)
    ancora_texto = f"{parsed.get('anchor_text') or ''} {parsed.get('trecho_original') or ''}"
    parsed["sinal_ancora_contem_termo_destino"] = any(
        _contem_termo(ancora_texto, t) for t in termos_kw
    )

    return parsed


def _build_prompt_focado(
    candidato: dict[str, Any],
    contexto: list[tuple[int, str]],
    ancoras_preferidas: list[str] | None = None,
    objetivo_linkagem: str | None = None,
    nota_densidade: str | None = None,
) -> str:
    blocos = ""
    for local_idx, (_, texto) in enumerate(contexto):
        blocos += f"\n[L{local_idx}] {texto}\n"

    palavras_destino = candidato.get("palavras_chave") or []
    if isinstance(palavras_destino, list):
        kws_str = ", ".join(str(p) for p in palavras_destino if p)
    else:
        kws_str = str(palavras_destino)

    ancoras_block = ""
    if ancoras_preferidas:
        linhas = "\n".join(f'- "{a}"' for a in ancoras_preferidas)
        ancoras_block = f"""
ANCORAS PREFERIDAS (PRIORIDADE MAXIMA):
{linhas}

REGRA ZERO (sobrepoe todas as outras): se QUALQUER paragrafo contem uma destas ancoras
(literal, flexionada, ou cobertura por todas as palavras), VOCE DEVE:
1. Responder decisao="aplicar" escolhendo esse paragrafo (mesmo se outro pareca mais natural).
2. Usar a ancora preferida LITERAL como `anchor_text` (sem truncar).
3. Copiar `trecho_original` do paragrafo de forma que CONTENHA a ancora.

So aplique a rubrica geral abaixo quando NENHUM paragrafo contem variante de
uma ancora preferida.

EXEMPLO 0 — ancora preferida no paragrafo (PRIORIDADE):

ANCORAS PREFERIDAS: ["livros para mulheres cristas"]
Paragrafo L0: "... livros para mulheres cristas representam mais de 40% do nosso catalogo ..."
URL destino: /categoria-produto/livros/mulheres/

Resposta CORRETA:
{{"decisao": "aplicar", "paragrafo_idx": 0,
  "trecho_original": "livros para mulheres cristas representam",
  "anchor_text": "livros para mulheres cristas", "confianca": 0.9,
  "motivo": "Trecho contem ancora preferida literal."}}

Resposta INCORRETA (truncou ancora preferida):
{{"anchor_text": "livros", ...}}
"""

    objetivo_block = ""
    if objetivo_linkagem:
        objetivo_block = f"""
OBJETIVO ESTRATEGICO DA LINKAGEM:
{objetivo_linkagem}

Use esse objetivo como filtro de qualidade: prefira ancoras e trechos
alinhados a essa intencao. Se o objetivo mencionar "conversao" ou
"categoria de produto", priorize ancoras com substantivos especificos
do nicho comercial (nao termos vagos como "tema" ou "papel").
"""

    nota_block = f"\n{nota_densidade}\n" if nota_densidade else ""
    n_paragrafos = len(contexto)

    return f"""Você é um editor sênior de SEO. Você decide, SOZINHO e UMA ÚNICA VEZ, se este artigo
deve linkar para a URL de destino abaixo — e onde. Não há outro filtro semântico depois de você:
seja criterioso, mas não covarde. Links internos bem colocados ajudam o leitor e o SEO.

URL DESTINO:
- URL: {candidato['url']}
- Título: {candidato.get('titulo', '')}
- Palavras-chave do destino: {kws_str}
- Resumo: {candidato.get('resumo', '')[:300]}
- Categoria: {candidato.get('categoria', '')}
{objetivo_block}{ancoras_block}{nota_block}
PARÁGRAFOS CANDIDATOS DO ARTIGO:
{blocos}

DECIDA (`decisao`):
- "aplicar": existe um trecho literal em algum parágrafo que funciona como âncora NATURAL
  (o leitor entende para onde o link leva e a frase continua gramatical) E o tema do parágrafo
  tem relação direta OU fortemente complementar com o destino. Relação por sinônimo ou termo
  do mesmo domínio é VÁLIDA mesmo que a palavra exata não esteja na lista de palavras-chave
  (ex.: "revenda sem estoque" pode ancorar um destino sobre dropshipping). Guias do MESMO
  assunto para outro segmento/público também são fortemente complementares e DEVEM linkar
  quando houver trecho natural (ex.: artigo sobre CNAE de comércio linka o guia de CNAE de
  serviços no trecho que fala de outras atividades — o leitor com atividade mista precisa dos dois).
- "sugerir": o tema é relacionado, mas nenhum trecho atual serve de âncora natural — o texto
  precisaria de ajuste. Explique no `motivo` O QUE o autor deve ajustar
  (ex.: "mencionar contabilidade no parágrafo sobre formalização").
- "descartar": não há relação temática real entre o artigo e o destino. NUNCA force um link.
  Explique o `motivo` em termos de temas (ex.: "o artigo fala de CNAE de varejo; o destino
  fala de contratação PJ — o leitor não ganharia nada com o link").

REGRAS DURAS (para decisao="aplicar"):
1. `trecho_original`: 2-6 palavras CONTÍNUAS, COPIADAS EXATAMENTE de um dos parágrafos acima.
   NÃO PARAFRASEIE — a inserção falha se o trecho não existir literalmente no texto.
2. `anchor_text` (por padrão igual ao trecho_original) deve nomear o conceito específico do
   destino — nunca termos vazios como "negócio", "empresa", "clique aqui", "este tipo", "como fazer".
3. PROIBIDO usar trechos de cabeçalhos, listas ou blocos de código.
4. Conectores `conector_antes`/`conector_depois` (até 3 palavras cada) SOMENTE quando a transição
   já existir no texto; não crie contexto novo nem repita palavras vizinhas ao trecho.
5. `motivo`: SEMPRE preenchido, 1 frase, linguagem de usuário final (sem jargão técnico).
6. `confianca`: 0.0 a 1.0 — sua confiança na decisão.

EXEMPLO aplicar (sinônimo de domínio):
Parágrafo L2: "...a revenda sem estoque vem crescendo entre novos empreendedores..."
Destino: "Como abrir uma loja virtual (dropshipping)"
Resposta: {{"decisao": "aplicar", "paragrafo_idx": 2, "trecho_original": "revenda sem estoque",
"anchor_text": "revenda sem estoque", "confianca": 0.85,
"motivo": "O parágrafo trata de revenda sem estoque, que é exatamente o modelo dropshipping do destino."}}

EXEMPLO sugerir:
Destino: "Contabilidade para MEI" e o artigo só cita "formalização" de passagem.
Resposta: {{"decisao": "sugerir", "paragrafo_idx": -1, "confianca": 0.6,
"motivo": "Adicionar uma menção a contabilidade no parágrafo sobre formalização permitiria um link natural."}}

EXEMPLO descartar:
Destino: "Guia de marketplace" e o artigo é sobre escolha de CNAE de comércio varejista sem citar venda em plataformas.
Resposta: {{"decisao": "descartar", "paragrafo_idx": -1, "confianca": 0.8,
"motivo": "O artigo trata da escolha de CNAE; o destino fala de vender em marketplaces — temas desconectados para o leitor."}}

Agora responda APENAS com JSON, no mesmo formato, para o caso real.
Use `paragrafo_idx` LOCAL entre 0 e {max(0, n_paragrafos - 1)} (referente a L0..L{max(0, n_paragrafos - 1)})."""


def _parse_proposta_unica(response: str) -> dict[str, Any] | None:
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            if not data:
                return None
            if "decisao" in data:
                return data
            if "trecho_original" in data and "paragrafo_idx" in data:
                # Formato antigo (sem decisao) — trecho presente implica aplicar.
                data.setdefault("decisao", "aplicar" if data.get("trecho_original") else "sugerir")
                return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _truncate_conector(conector: str) -> str:
    if not conector:
        return ""
    words = conector.split()
    if len(words) > _MAX_CONECTOR_WORDS:
        return " ".join(words[:_MAX_CONECTOR_WORDS])
    return conector


def _find_trecho_in_paragrafo(paragrafo: str, trecho_original: str) -> int | None:
    if not trecho_original or len(trecho_original.strip()) < 2:
        return None
    folded_p = _strip_accents(paragrafo.lower())
    folded_t = _strip_accents(trecho_original.lower())
    idx = folded_p.find(folded_t)
    if idx >= 0:
        return idx
    pattern = r"\b" + r"\s*".join(re.escape(w) + r"s?" for w in trecho_original.split()) + r"\b"
    m = re.search(pattern, folded_p, re.IGNORECASE)
    if m:
        return m.start()
    return None


def _find_trecho_qualquer_paragrafo(
    paragrafos: list[str], trecho: str, exclude_idx: int
) -> tuple[int, int] | None:
    for i, p in enumerate(paragrafos):
        if i == exclude_idx or not _paragrafo_elegivel(p):
            continue
        offset = _find_trecho_in_paragrafo(p, trecho)
        if offset is not None:
            return i, offset
    return None


def _word_position(text: str, char_offset: int) -> int:
    return len(text[:char_offset].split())


def _aplicar_insercoes(
    pilar_markdown: str,
    paragrafos: list[str],
    candidatos: list[dict[str, Any]],
    insercoes_raw: list[dict[str, Any]],
    min_distance_words: int = _MIN_DISTANCE_WORDS_BASE,
    ancoras_preferidas: list[str] | None = None,
    finalizar_colisoes: bool = True,
) -> tuple[str, list[InlinkInserido], list[dict[str, Any]]]:
    """Aplica as inserções válidas e retorna (texto, itens, colisões).

    `colisoes` são propostas que caíram APENAS por proximidade de outro inlink;
    com finalizar_colisoes=True elas viram sugestao_manual (comportamento final),
    com False são devolvidas ao chamador para 1 retry com outro parágrafo.
    """
    candidatos_by_url = {c.get("url"): c for c in candidatos}

    validas: list[dict[str, Any]] = []
    sugestoes: list[dict[str, Any]] = []
    descartes: list[dict[str, Any]] = []
    colisoes: list[dict[str, Any]] = []
    accepted_word_positions: list[int] = []

    for ins in insercoes_raw:
        url = ins.get("url_destino", "")
        c = candidatos_by_url.get(url)
        if not c:
            continue

        if ins.get("_descartado"):
            descartes.append(ins)
            continue

        if ins.get("_inseridor_vazio"):
            sugestoes.append({**ins, "motivo_sugestao": ins.get("motivo_sugestao")})
            continue

        if ins.get("_modo_cta"):
            cta_p_idx = ins.get("paragrafo_idx", -1)
            if cta_p_idx < 0 or cta_p_idx >= len(paragrafos):
                continue
            ancora_cta = ins.get("_ancora_cta", "")
            cta_md = f"\n\n> Leia também: [{ancora_cta}]({ins['url_destino']})"
            global_offset = sum(len(p) + 2 for p in paragrafos[:cta_p_idx + 1]) - 2
            validas.append({
                "url": ins["url_destino"],
                "paragrafo_idx": cta_p_idx,
                "global_offset": global_offset,
                "trecho_original": "",
                "anchor_text": ancora_cta,
                "conector_antes": cta_md,
                "conector_depois": "",
                "justificativa": ins.get("justificativa", ""),
                "candidato": c,
                "_modo_cta": True,
            })
            continue

        p_idx = ins.get("paragrafo_idx", -1)
        if p_idx < 0 or p_idx >= len(paragrafos):
            continue

        if ins.get("forcar_sugestao_manual"):
            sugestoes.append({**ins, "motivo_sugestao": ins.get("motivo_sugestao", "Baixa relevância semântica.")})
            continue

        paragrafo = paragrafos[p_idx]
        if _esta_em_cabecalho(paragrafo, 0):
            sugestoes.append({**ins, "motivo_sugestao": "Parágrafo indicado é um cabeçalho."})
            continue

        if _LIST_ITEM_RE.match(paragrafo.strip()):
            sugestoes.append({**ins, "motivo_sugestao": "Parágrafo indicado é um item de lista."})
            continue

        trecho_original = ins.get("trecho_original", "")
        local_offset = _find_trecho_in_paragrafo(paragrafo, trecho_original)
        if local_offset is None:
            fallback = _find_trecho_qualquer_paragrafo(paragrafos, trecho_original, exclude_idx=p_idx)
            if fallback is None:
                sugestoes.append({
                    **ins,
                    "motivo_sugestao": f"Trecho '{trecho_original[:50]}' não encontrado em nenhum parágrafo elegível.",
                })
                continue
            p_idx, local_offset = fallback
            paragrafo = paragrafos[p_idx]

        url_existente = _link_existente_em(paragrafo, local_offset)
        if url_existente:
            from app.core.scraper import _normalizar_url
            url_alvo_norm = _normalizar_url(url)
            url_existente_norm = _normalizar_url(url_existente)
            if url_alvo_norm == url_existente_norm:
                sugestoes.append({
                    **ins,
                    "motivo_sugestao": "Trecho ja e link para a URL alvo. Nenhuma acao necessaria.",
                })
                continue
            else:
                sugestoes.append({
                    **ins,
                    "motivo_sugestao": (
                        f"Trecho '{trecho_original[:50]}' já é link para outra URL ({url_existente[:60]}). "
                        f"Avalie manualmente se substituir traz ganho estratégico."
                    ),
                })
                continue

        conector_antes = _truncate_conector(ins.get("conector_antes", "")).strip()
        conector_depois = _truncate_conector(ins.get("conector_depois", "")).strip()

        if conector_antes and _ha_conector_no_entorno(paragrafo, local_offset):
            conector_antes = ""

        if conector_antes:
            before_trecho = paragrafo[max(0, local_offset - 40):local_offset].lower()
            ca_words = conector_antes.lower().split()
            if ca_words and ca_words[-1] in before_trecho[-30:]:
                conector_antes = ""

        if conector_depois:
            after_trecho = paragrafo[local_offset + len(trecho_original):local_offset + len(trecho_original) + 40].lower()
            cd_words = conector_depois.lower().split()
            if cd_words and cd_words[0] in after_trecho[:30]:
                conector_depois = ""
            elif not conector_depois.startswith((" ", ",", ".", ";", "-")):
                conector_depois = " " + conector_depois

        global_offset = sum(len(p) + 2 for p in paragrafos[:p_idx]) + local_offset

        word_pos = _word_position(pilar_markdown, global_offset)
        too_close = any(abs(word_pos - wp) < min_distance_words for wp in accepted_word_positions)
        if too_close:
            if finalizar_colisoes:
                sugestoes.append({**ins, "motivo_sugestao": "Muito próximo de outro inlink."})
            else:
                colisoes.append(ins)
            continue

        accepted_word_positions.append(word_pos)
        validas.append({
            "url": url,
            "paragrafo_idx": p_idx,
            "global_offset": global_offset,
            "trecho_original": trecho_original,
            "anchor_text": ins.get("anchor_text") or trecho_original,
            "conector_antes": conector_antes,
            "conector_depois": conector_depois,
            "justificativa": ins.get("justificativa", ""),
            "candidato": c,
            "confianca": ins.get("confianca"),
            "sinal_cos_contexto": ins.get("sinal_cos_contexto"),
            "sinal_cos_ancora": ins.get("sinal_cos_ancora"),
        })

    validas.sort(key=lambda x: x["global_offset"], reverse=True)

    texto = pilar_markdown

    for v in validas:
        if v.get("_modo_cta"):
            offset = v["global_offset"]
            ca = v["conector_antes"]
            texto = texto[:offset] + ca + texto[offset:]
            v["link_md_len"] = len(ca)
            continue

        offset = v["global_offset"]
        trecho_len = len(v["trecho_original"])

        anchor = v["anchor_text"]
        url = v["url"]
        ca = v["conector_antes"]
        cd = v["conector_depois"]

        link_md = f"{ca}[{anchor}]({url}){cd}"
        texto = texto[:offset] + link_md + texto[offset + trecho_len:]
        v["link_md_len"] = len(link_md)

    inseridos: list[InlinkInserido] = []

    shift = 0
    for v in sorted(validas, key=lambda x: x["global_offset"]):
        c = v["candidato"]
        final_start = v["global_offset"] + shift
        final_end = final_start + v["link_md_len"]
        trecho_ctx = _extrair_trecho_contexto(texto, final_start, final_end)

        inseridos.append(InlinkInserido(
            url_destino=v["url"],
            anchor_text=v["anchor_text"],
            paragrafo_idx=v["paragrafo_idx"],
            offset_chars=final_start,
            score_total=c.get("score_total", 0),
            score_semantico=c.get("score_semantico", 0),
            score_contexto=c.get("score_contexto", 0),
            trecho_contexto=trecho_ctx,
            titulo_destino=c.get("titulo", "") or None,
            motivo_contexto=v.get("justificativa") or c.get("motivo_contexto", "") or None,
            categoria_match=_categoria_match(
                c.get("score_semantico", 0), c.get("score_contexto", 0), c.get("score_total", 0)
            ),
            trecho_original=v["trecho_original"],
            conector_antes=v["conector_antes"] or None,
            conector_depois=v["conector_depois"] or None,
            ancora_preferida_usada=bool(
                ancoras_preferidas
                and _ancora_preferida_match(v["anchor_text"], ancoras_preferidas)
            ),
            confianca=v.get("confianca"),
            sinal_cos_contexto=v.get("sinal_cos_contexto"),
            sinal_cos_ancora=v.get("sinal_cos_ancora"),
        ))
        shift += v["link_md_len"] - len(v["trecho_original"])

    for s in sugestoes:
        url = s.get("url_destino", "")
        c = candidatos_by_url.get(url, {})
        inseridos.append(InlinkInserido(
            url_destino=url,
            anchor_text=s.get("anchor_text", s.get("trecho_original", "")),
            paragrafo_idx=s.get("paragrafo_idx", 0),
            offset_chars=0,
            score_total=c.get("score_total", 0),
            score_semantico=c.get("score_semantico", 0),
            score_contexto=c.get("score_contexto", 0),
            status="sugestao_manual",
            titulo_destino=c.get("titulo", "") or None,
            motivo_contexto=c.get("motivo_contexto", "") or None,
            motivo_sugestao=s.get("motivo_sugestao"),
            categoria_match=_categoria_match(
                c.get("score_semantico", 0), c.get("score_contexto", 0), c.get("score_total", 0)
            ),
            trecho_original=s.get("trecho_original"),
            confianca=s.get("confianca"),
            sinal_cos_contexto=s.get("sinal_cos_contexto"),
            sinal_cos_ancora=s.get("sinal_cos_ancora"),
        ))

    for d in descartes:
        url = d.get("url_destino", "")
        c = candidatos_by_url.get(url, {})
        inseridos.append(InlinkInserido(
            url_destino=url,
            anchor_text="",
            paragrafo_idx=-1,
            offset_chars=0,
            score_total=c.get("score_total", 0),
            score_semantico=c.get("score_semantico", 0),
            score_contexto=c.get("score_contexto", 0),
            status="rejeitado",
            motivo_rejeicao=d.get("motivo_rejeicao") or "Sem relação temática real com o destino.",
            titulo_destino=c.get("titulo", "") or None,
            categoria_match=_categoria_match(
                c.get("score_semantico", 0), c.get("score_contexto", 0), c.get("score_total", 0)
            ),
            confianca=d.get("confianca"),
        ))

    return texto, inseridos, colisoes
