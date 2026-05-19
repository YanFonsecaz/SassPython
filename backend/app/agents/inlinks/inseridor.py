import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.agents.base import BaseAgent
from app.agents.inlinks.injector import (
    _categoria_match,
    _esta_em_cabecalho,
    _extrair_trecho_contexto,
    _strip_accents,
)
from app.core.embeddings import cosine_seguro, gerar_embeddings_batch

logger = logging.getLogger(__name__)

_MIN_DISTANCE_WORDS_BASE = 100
_MAX_CONECTOR_WORDS = 3
_TOP_N_PARAGRAFOS = 5
_MIN_PARAGRAFO_CHARS = 80
_MIN_INSERCAO_SEMANTICA = 0.50
_MIN_INSERCAO_SEMANTICA_KW_VALIDA = 0.35
_MIN_ANCORA_TITULO = 0.35
_MIN_SEMANTIC_FALLBACK = 0.40
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


async def inserir_inlinks(
    pilar_markdown: str,
    candidatos: list[dict[str, Any]],
    usuario_id: str,
    max_inlinks: int = 8,
) -> tuple[str, list[InlinkInserido]]:
    if not pilar_markdown.strip() or not candidatos:
        return pilar_markdown, []

    paragrafos = pilar_markdown.split("\n\n")
    candidatos_top = sorted(
        candidatos, key=lambda c: c.get("score_total", 0), reverse=True
    )[:max_inlinks]

    textos_paragrafos = [p[:2000] for p in paragrafos]
    paragrafos_embeddings = await gerar_embeddings_batch(
        textos_paragrafos, usuario_id
    )

    todas_insercoes: list[dict[str, Any]] = []
    propostas_por_candidato: list[tuple[dict[str, Any], dict[str, Any][str, Any] | None]] = []

    for c in candidatos_top:
        contexto_paragrafos = await _selecionar_paragrafos_relevantes(
            paragrafos,
            c,
            paragrafos_embeddings,
            usuario_id,
        )
        if not contexto_paragrafos:
            logger.info("Inseridor: candidato %s sem parágrafos elegíveis", c.get("url"))
            propostas_por_candidato.append((c, None))
            continue

        proposta = await _propor_insercao_para_candidato(
            c, contexto_paragrafos, usuario_id
        )
        if not proposta:
            propostas_por_candidato.append((c, None))
            continue

        propostas_por_candidato.append((c, proposta))

    pares_para_validar: list[tuple[dict[str, Any], dict[str, Any]]] = []
    textos_batch: list[str] = []
    for c, proposta in propostas_por_candidato:
        if not proposta:
            continue
        if proposta.get("_inseridor_vazio"):
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

    for i, (_c, proposta) in enumerate(pares_para_validar):
        emb_ctx = embs_batch[i * 4] if i * 4 < len(embs_batch) else None
        emb_dst = embs_batch[i * 4 + 1] if i * 4 + 1 < len(embs_batch) else None
        emb_anc = embs_batch[i * 4 + 2] if i * 4 + 2 < len(embs_batch) else None
        emb_tit = embs_batch[i * 4 + 3] if i * 4 + 3 < len(embs_batch) else None

        cosine_contexto = cosine_seguro(emb_ctx, emb_dst) if emb_ctx is not None and emb_dst is not None else 1.0
        cosine_ancora = cosine_seguro(emb_anc, emb_tit) if emb_anc is not None and emb_tit is not None else 1.0

        # Se a validação dura por palavra-chave (_validar_palavra_chave_destino)
        # já passou, confiamos nela e relaxamos o piso de cosine âncora-destino.
        # Caso contrário, usa o piso conservador.
        kw_ja_validada = not proposta.get("forcar_sugestao_manual")
        piso_semantico = _MIN_INSERCAO_SEMANTICA_KW_VALIDA if kw_ja_validada else _MIN_INSERCAO_SEMANTICA

        if cosine_contexto < piso_semantico:
            proposta["forcar_sugestao_manual"] = True
            proposta["motivo_sugestao"] = (
                f"Baixa relação semântica entre âncora e destino (cos={cosine_contexto:.2f} < {piso_semantico:.2f})."
            )
        elif cosine_ancora < _MIN_ANCORA_TITULO:
            proposta["forcar_sugestao_manual"] = True
            proposta["motivo_sugestao"] = "Âncora genérica — não menciona termo específico do destino."
        todas_insercoes.append(proposta)

    min_dist = _calcular_min_distance(pilar_markdown, max_inlinks)
    logger.info(
        "Inseridor: min_distance_words=%d (palavras=%d, max=%d)",
        min_dist, len(pilar_markdown.split()), max_inlinks,
    )
    return _aplicar_insercoes(
        pilar_markdown, paragrafos, candidatos_top, todas_insercoes,
        min_distance_words=min_dist,
    )


class _InseridorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(usuario_id)
        # Override do modelo apenas para o Inseridor — tarefa exige maior
        # precisão de cópia literal e discernimento contextual entre candidatos.
        from app.config import settings
        if settings.llm_provider == "openai" and settings.inseridor_llm_model:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.inseridor_llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.openai_api_key,
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


def _keyword_boost(paragrafo: str, termos: list[str]) -> float:
    if not termos or not paragrafo:
        return 0.0
    matches = sum(1 for t in termos if _contem_termo(paragrafo, t))
    if matches == 0:
        return 0.0
    return min(0.25, 0.08 * matches)


async def _selecionar_paragrafos_relevantes(
    paragrafos: list[str],
    candidato: dict[str, Any],
    paragrafos_embeddings: list[Any],
    usuario_id: str,
    top_n: int = _TOP_N_PARAGRAFOS,
) -> list[tuple[int, str]]:
    consulta = _texto_destino(candidato)[:1500]
    emb_consulta_lst = await gerar_embeddings_batch([consulta], usuario_id)
    emb_consulta = emb_consulta_lst[0] if emb_consulta_lst else None
    termos_kw = _termos_keyword_destino(candidato)

    if emb_consulta is None:
        elegiveis = [(i, p) for i, p in enumerate(paragrafos) if _paragrafo_elegivel(p)]
        if termos_kw:
            scored_kw = [(i, p, _keyword_boost(p, termos_kw)) for i, p in elegiveis]
            scored_kw.sort(key=lambda x: x[2], reverse=True)
            return [(i, p) for i, p, _ in scored_kw[:top_n]]
        return elegiveis[:top_n]

    scored: list[tuple[int, str, float, float]] = []
    for i, (p, emb_p) in enumerate(zip(paragrafos, paragrafos_embeddings, strict=False)):
        if emb_p is None or not _paragrafo_elegivel(p):
            continue
        cosine = cosine_seguro(emb_consulta, emb_p)
        boost = _keyword_boost(p, termos_kw)
        scored.append((i, p, float(cosine) + boost, boost))

    scored.sort(key=lambda x: x[2], reverse=True)
    n_kw_match = sum(1 for _, _, _, b in scored[:top_n] if b > 0)
    logger.info(
        "Inseridor: top-%d parágrafos para %s — %d com keyword match (termos=%s)",
        top_n, candidato.get("url", "?")[-60:], n_kw_match,
        ", ".join(termos_kw[:5]),
    )
    return [(i, p) for i, p, _, _ in scored[:top_n]]


async def _propor_insercao_para_candidato(
    candidato: dict[str, Any],
    contexto_paragrafos: list[tuple[int, str]],
    usuario_id: str,
) -> dict[str, Any] | None:
    agente = _InseridorAgent(usuario_id)
    prompt = _build_prompt_focado(candidato, contexto_paragrafos)
    logger.info(
        "Inseridor: prompt para %s (%d chars, %d parágrafos)\n%s\n---END PROMPT---",
        candidato.get("url", "?"),
        len(prompt),
        len(contexto_paragrafos),
        prompt[:3000],
    )
    try:
        resposta = await agente._invoke_llm(prompt)
        logger.info(
            "Inseridor: resposta para %s: %s",
            candidato.get("url", "?"),
            (resposta or "")[:500],
        )
        parsed = _parse_proposta_unica(resposta)
    except Exception as e:
        logger.warning("Inseridor LLM falhou para %s: %s", candidato.get("url"), e)
        return None

    if not parsed:
        logger.warning(
            "Inseridor: LLM não propôs inserção para %s. Resposta: %s",
            candidato.get("url"),
            (resposta or "")[:400],
        )
        termos_kw = _termos_keyword_destino(candidato)
        motivo = (
            f"Inseridor não encontrou parágrafo do pilar com termos do destino "
            f"({', '.join(termos_kw[:5])}). Considere reescrever o pilar mencionando o nicho."
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

    motivo_kw = await _validar_palavra_chave_destino(parsed, candidato, paragrafo_completo, usuario_id)
    if motivo_kw:
        logger.info(
            "Inseridor: palavra_chave_destino falhou para %s: %s",
            candidato.get("url"), motivo_kw,
        )
        parsed["forcar_sugestao_manual"] = True
        parsed["motivo_sugestao"] = motivo_kw

    return parsed


def _build_prompt_focado(
    candidato: dict[str, Any], contexto: list[tuple[int, str]]
) -> str:
    blocos = ""
    for local_idx, (_, texto) in enumerate(contexto):
        blocos += f"\n[L{local_idx}] {texto}\n"

    palavras_destino = candidato.get("palavras_chave") or []
    if isinstance(palavras_destino, list):
        kws_str = ", ".join(str(p) for p in palavras_destino if p)
    else:
        kws_str = str(palavras_destino)

    return f"""Você é um especialista em SEO. Recebe parágrafos candidatos e UMA URL de destino.
Sua tarefa: escolher UM parágrafo e UM trecho contínuo desse parágrafo para virar âncora do link.

URL DESTINO:
- URL: {candidato['url']}
- Título: {candidato.get('titulo', '')}
- Palavras-chave do destino: {kws_str}
- Resumo: {candidato.get('resumo', '')[:200]}

PARÁGRAFOS DISPONÍVEIS:
{blocos}

REGRAS (em ordem de prioridade):
1. Escolha o parágrafo cujo TEMA bate com o destino, não pela palavra solta.
2. `trecho_original`: 2-5 palavras CONTÍNUAS, COPIADAS EXATAMENTE de um dos parágrafos acima. NÃO PARAFRASEIE.
3. `anchor_text`: por padrão igual ao trecho_original.
4. Conectores `conector_antes` / `conector_depois` (até 3 palavras cada). Use SOMENTE quando o trecho_original já estiver naturalmente conectado ao redor e faltarem palavras de transição. NÃO use para criar contexto que não existe no parágrafo. Se o tema do parágrafo não tem relação clara com o destino, prefira NÃO propor inserção. O conector NÃO deve repetir palavras que já existem imediatamente após o trecho_original.
5. PROIBIDO inserir em: cabeçalhos, listas, blocos de código (já filtramos, dupla checagem).
6. **NÃO force link onde não há conexão temática.** Se o tema do parágrafo é diferente do destino, retorne `{{}}`. É melhor ter menos links com qualidade do que links forçados.
7. **`palavra_chave_destino`**: ESCOLHA OBRIGATORIAMENTE uma das **palavras-chave do destino** listadas acima (ou um substantivo presente no título do destino). NÃO invente sinônimos do pilar — se o conceito do parágrafo NÃO está na lista de palavras-chave do destino, retorne `{{}}`. NÃO use palavras genéricas como "negócio", "empresa", "abrir", "tipo", "investimento", "como".

EXEMPLO 1 — match literal direto (caminho padrão):

Parágrafo L0: "Restaurante que ofereça um cardápio específico, com estrutura para entregas, aproveita o crescimento do delivery."
URL destino: como-abrir-um-restaurante
Palavras-chave do destino: ["restaurante", "gastronomia", "cardápio", "delivery"]

Resposta:
{{"paragrafo_idx": 0, "trecho_original": "Restaurante que ofereça", "anchor_text": "Restaurante", "palavra_chave_destino": "restaurante", "justificativa": "Trecho menciona 'restaurante' literalmente; destino aprofunda como abrir um restaurante."}}

EXEMPLO 2 — match por sinônimo PRESENTE na lista (caminho válido):

Parágrafo L1: "Python é uma das linguagens mais populares para iniciantes."
URL destino: melhor-linguagem-iniciantes / Palavras-chave: ["linguagem", "Python", "iniciantes"]

Resposta:
{{"paragrafo_idx": 1, "trecho_original": "Python é uma das linguagens", "anchor_text": "Python", "palavra_chave_destino": "Python", "justificativa": "Trecho menciona 'Python', que é uma das palavras-chave do destino."}}

EXEMPLO 3 — quando recusar (sem match no parágrafo NEM na lista):

Parágrafo: "Antes de empreender, faça um estudo de mercado completo."
URL destino: como-abrir-uma-imobiliaria / Palavras-chave: ["imobiliária", "imóveis", "corretagem"]

Nenhum termo das palavras-chave aparece no parágrafo. Resposta: {{}}.

REGRA DE DECISÃO: se algum termo das palavras-chave do destino aparece literalmente em algum parágrafo (mesmo flexionado), você DEVE propor uma inserção. Só retorne {{}} quando nenhum parágrafo menciona termos específicos do destino.

Agora responda APENAS com JSON, no mesmo formato, para o caso real. Use `paragrafo_idx` 0, 1, 2, 3 ou 4 referente a L0/L1/L2/L3/L4."""


def _parse_proposta_unica(response: str) -> dict[str, Any] | None:
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            if not data:
                return None
            if "trecho_original" in data and "paragrafo_idx" in data:
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


def _termos_validos_destino(candidato: dict[str, Any], palavra_chave_principal: str) -> list[str]:
    termos = [palavra_chave_principal]
    palavras = candidato.get("palavras_chave") or []
    if isinstance(palavras, list):
        termos.extend(str(p) for p in palavras)

    validos: list[str] = []
    vistos: set[str] = set()
    for t in termos:
        t_raw = (t or "").strip()
        if len(t_raw) < 3:
            continue
        t_norm = _normalize_token(t_raw)
        if t_norm in _STOPWORDS_GENERICAS:
            continue
        if t_norm in vistos:
            continue
        vistos.add(t_norm)
        validos.append(t_raw)
    return validos


async def _validar_palavra_chave_destino(
    parsed: dict[str, Any],
    candidato: dict[str, Any],
    paragrafo_completo: str,
    usuario_id: str,
) -> str | None:
    kw_raw = (parsed.get("palavra_chave_destino") or "").strip()
    if not kw_raw or len(kw_raw) < 2:
        return "Inseridor não nomeou termo específico do destino."

    kw_norm = _normalize_token(kw_raw)
    if kw_norm in _STOPWORDS_GENERICAS:
        return f"Termo '{kw_raw}' é muito genérico para servir de âncora específica."

    titulo = candidato.get("titulo", "") or ""
    resumo = candidato.get("resumo", "") or ""
    palavras_chave = candidato.get("palavras_chave", []) or []
    palavras_chave_str = " ".join(palavras_chave) if isinstance(palavras_chave, list) else str(palavras_chave)
    destino_texto = f"{titulo} {resumo} {palavras_chave_str}"

    if not _contem_termo(destino_texto, kw_raw):
        destino_curto = f"{titulo} {resumo[:300]}"
        embs = await gerar_embeddings_batch([kw_raw, destino_curto], usuario_id)
        if embs and embs[0] is not None and embs[1] is not None:
            cos = cosine_seguro(embs[0], embs[1])
            logger.info(
                "Inseridor: kw '%s' fora das palavras-chave do destino (cos=%.3f). Rejeitando.",
                kw_raw, cos,
            )
        palavras_chave_lista = palavras_chave if isinstance(palavras_chave, list) else []
        amostra = ", ".join(f"'{p}'" for p in palavras_chave_lista[:5])
        return (
            f"Termo '{kw_raw}' não está nas palavras-chave do destino. "
            f"Inseridor deveria escolher um da lista: {amostra}."
        )

    termos_validos = _termos_validos_destino(candidato, kw_raw)
    if not termos_validos:
        return f"Nenhum termo específico do destino disponível para validação (kw='{kw_raw}')."

    anchor = parsed.get("anchor_text") or ""
    trecho = parsed.get("trecho_original") or ""
    ancora_texto = f"{anchor} {trecho} {paragrafo_completo}"

    for termo in termos_validos:
        if _contem_termo(ancora_texto, termo):
            return None

    termos_str = ", ".join(f"'{t}'" for t in termos_validos[:5])
    return (
        f"Âncora não menciona nenhum termo específico do destino. "
        f"Esperado um de: {termos_str}."
    )


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
) -> tuple[str, list[InlinkInserido]]:
    candidatos_by_url = {c.get("url"): c for c in candidatos}

    validas: list[dict[str, Any]] = []
    sugestoes: list[dict[str, Any]] = []
    accepted_word_positions: list[int] = []

    for ins in insercoes_raw:
        url = ins.get("url_destino", "")
        c = candidatos_by_url.get(url)
        if not c:
            continue

        if ins.get("_inseridor_vazio"):
            sugestoes.append({**ins, "motivo_sugestao": ins.get("motivo_sugestao")})
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
            sugestoes.append({**ins, "motivo_sugestao": "Muito próximo de outro inlink."})
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
        })

    validas.sort(key=lambda x: x["global_offset"], reverse=True)

    texto = pilar_markdown

    for v in validas:
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

    for v in sorted(validas, key=lambda x: x["global_offset"]):
        c = v["candidato"]
        offset = v["global_offset"]

        trecho_ctx = _extrair_trecho_contexto(texto, offset, offset + v["link_md_len"])

        inseridos.append(InlinkInserido(
            url_destino=v["url"],
            anchor_text=v["anchor_text"],
            paragrafo_idx=v["paragrafo_idx"],
            offset_chars=offset,
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
        ))

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
        ))

    return texto, inseridos
