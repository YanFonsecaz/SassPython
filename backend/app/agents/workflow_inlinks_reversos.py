import asyncio
import logging
import re
from typing import Any, TypedDict
from urllib.parse import urlparse

import numpy as np
from langgraph.graph import END, StateGraph

from app.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj

_MIN_SEMANTIC_SCORE = 0.40
_MIN_ALVO_CHARS = 1500
_MIN_ALVO_PALAVRAS = 250
_PISO_SLUG_ONLY = 0.30
_FATOR_SLUG_ONLY = 0.65

# Padrões que indicam página não-redacional (listagens, categoria, paginação)
_BOILERPLATE_PATTERNS = (
    "showing 1",  # WooCommerce/WordPress listings ("Showing 1-9 of 18 results")
    "cookielawinfo",
    "cookies that may not be particularly",
)


def _detectar_boilerplate(conteudo: str) -> str | None:
    """Retorna motivo se conteúdo é boilerplate de listagem/cookies, None se OK."""
    if not conteudo:
        return None
    lower = conteudo.lower()
    hits = [p for p in _BOILERPLATE_PATTERNS if p in lower]
    if not hits:
        return None
    # Densidade do boilerplate: se > 30% do texto for tabela de cookies, é lixo
    cookielaw_count = lower.count("cookielawinfo")
    if cookielaw_count >= 3:
        return f"Pagina e principalmente tabela de cookies GDPR ({cookielaw_count} entradas)"
    if "showing 1" in lower and lower.find("showing 1") < 200:
        return "Pagina parece ser uma listagem (categoria, arquivo, paginacao)"
    return None


_CATEGORIA_URL_PATTERNS = (
    "/categoria-produto/",
    "/categoria/",
    "/categorias/",
    "/produto/",
    "/produtos/",
    "/product/",
    "/products/",
    "/product-category/",
    "/cat/",
    "/loja/",
    "/shop/",
    "/colecoes/",
    "/collections/",
    "/p/",
)

_SLUG_SEGMENTOS_GENERICOS = {
    "categoria", "categorias", "produto", "produtos",
    "product", "products", "category", "categories",
    "blog", "post", "posts", "page", "p", "cat",
    "loja", "shop", "store", "tag", "tags",
    "colecao", "colecoes", "collection", "collections",
    "br", "com", "www", "html", "htm", "php",
}

_SLUG_STOPWORDS = {
    "de", "da", "do", "das", "dos", "para", "com",
    "e", "ou", "o", "a", "os", "as", "no", "na",
    "em", "by", "the", "of", "and", "for", "to", "in",
}

_SLUG_NAO_ALFA_RE = re.compile(r"[^a-zA-ZÀ-ÿ]")


def _e_url_categoria_produto(url: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    return any(p in url_lower for p in _CATEGORIA_URL_PATTERNS)


def _extrair_termos_slug(url: str) -> list[str]:
    if not url:
        return []
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return []

    segmentos = path.split("/")
    termos: list[str] = []
    vistos: set[str] = set()

    for seg in segmentos:
        partes = re.split(r"[-_]+", seg)
        for parte in partes:
            limpa = _SLUG_NAO_ALFA_RE.sub("", parte).lower()
            if len(limpa) < 3:
                continue
            if limpa in _SLUG_SEGMENTOS_GENERICOS or limpa in _SLUG_STOPWORDS:
                continue
            if limpa in vistos:
                continue
            vistos.add(limpa)
            termos.append(limpa)

    return termos


def _slug_tem_qualidade(termos: list[str]) -> bool:
    return len(termos) >= 2


def _variacoes_morfologicas(termo: str) -> list[str]:
    """Variações simples PT-BR (plural↔singular, gênero). Heurística."""
    t = termo.lower().strip()
    if len(t) < 4:
        return [t]
    out = {t}
    if t.endswith("es") and len(t) > 5:
        out.add(t[:-2])
    elif t.endswith("s") and len(t) > 4:
        out.add(t[:-1])
    else:
        out.add(t + "s")
        if t.endswith(("r", "l", "z")):
            out.add(t + "es")
    if t.endswith("a"):
        out.add(t[:-1] + "o")
    elif t.endswith("o"):
        out.add(t[:-1] + "a")
    return sorted(out)


def _strip_accents_local(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _contem_termo_local(haystack: str, needle: str) -> bool:
    if not haystack or not needle or len(needle.strip()) < 2:
        return False
    return _strip_accents_local(needle.lower()) in _strip_accents_local(haystack.lower())


def _candidata_tem_keyword_alvo(conteudo_md: str, palavras_alvo: list[str]) -> bool:
    if not conteudo_md or not palavras_alvo:
        return False
    return any(_contem_termo_local(conteudo_md, p) for p in palavras_alvo)


def _construir_pseudo_alvo(url: str, titulo: str, termos_slug: list[str]) -> tuple[str, list[str]]:
    titulo_limpo = (titulo or "").strip()

    bigramas: list[str] = []
    for i in range(len(termos_slug) - 1):
        bigramas.append(f"{termos_slug[i]} {termos_slug[i+1]}")

    todas_formas: list[str] = []
    for t in termos_slug:
        todas_formas.extend(_variacoes_morfologicas(t))
    todas_formas_uniq = list(dict.fromkeys(todas_formas))

    palavras_chave = list(dict.fromkeys(todas_formas_uniq + bigramas))
    if titulo_limpo:
        palavras_chave_lower = {p.lower() for p in palavras_chave}
        for t in titulo_limpo.split():
            t_norm = _SLUG_NAO_ALFA_RE.sub("", t).lower()
            if (
                len(t_norm) >= 3
                and t_norm not in _SLUG_SEGMENTOS_GENERICOS
                and t_norm not in _SLUG_STOPWORDS
                and t_norm not in palavras_chave_lower
            ):
                palavras_chave.append(t_norm)
                palavras_chave_lower.add(t_norm)

    termos_str = ", ".join(termos_slug)
    formas_str = ", ".join(todas_formas_uniq)
    bigramas_str = ", ".join(bigramas) if bigramas else termos_slug[0]
    pseudo = (
        f"# {titulo_limpo or termos_slug[0].title()}\n\n"
        f"Esta pagina apresenta conteudo sobre {termos_str}. "
        f"Termos relacionados: {formas_str}. "
        f"Os principais temas abordados sao {bigramas_str}. "
        f"Aqui voce encontra informacoes, recursos e materiais relacionados a "
        f"{formas_str}. "
        f"O foco da pagina e {' e '.join(termos_slug[:3])}, oferecendo opcoes "
        f"variadas para quem busca {bigramas_str}. "
        f"Categoria: {termos_str}. "
        f"Tema: {formas_str}."
    )
    return pseudo, palavras_chave


def _log_prefix(eid: str) -> str:
    return f"[distribuir eid={eid[:8]}]"


async def _resolver_checkpointer(ctx: dict[str, Any] | None):
    """Prefere checkpointer do ctx (worker warmup); senao usa singleton."""
    from app.agents.checkpointer import get_checkpointer, get_checkpointer_from_ctx

    cp = get_checkpointer_from_ctx(ctx)
    if cp is not None:
        return cp
    return await get_checkpointer()


class EstadoDistribuir(TypedDict):
    execucao_id: str
    usuario_id: str
    cliente_id: str | None

    url_alvo: str
    candidatas_urls: list[str]
    threshold_score: float
    max_inlinks_por_candidata: int
    rel_attr: str
    ancoras_preferidas: list[str]

    alvo_resultado: dict[str, Any]
    alvo_modo: str
    candidatas_resultados: list[dict[str, Any]]
    n_candidatas_validas: int
    n_candidatas_falhas: int

    alvo_embedding: list[float] | None
    candidatas_embeddings: list[dict[str, Any]]
    alvo_metadados: dict[str, Any]

    candidatas_viaveis: list[dict[str, Any]]
    candidatas_descartadas: list[dict[str, Any]]
    falhas_extracao: list[dict[str, Any]]

    candidatas_processadas: list[dict[str, Any]]

    resultado_final: dict[str, Any]


async def node_validar_urls(estado: EstadoDistribuir) -> dict[str, Any]:
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "validar_urls", "Validando e normalizando URLs...")

    from app.core.scraper import _normalizar_url

    alvo_normalizado = _normalizar_url(estado.get("url_alvo", ""))
    urls = estado.get("candidatas_urls", [])
    validas = []
    vistas = set()

    for url in urls:
        n = _normalizar_url(url)
        if n and n not in vistas and n != alvo_normalizado:
            validas.append(n)
            vistas.add(n)

    await publish_event(
        eid, "node_complete", "validar_urls",
        f"{len(validas)} URLs validas de {len(urls)} recebidas (alvo removido se presente)",
    )
    return {"candidatas_urls": validas, "url_alvo": alvo_normalizado}


async def node_extrair_alvo(estado: EstadoDistribuir) -> dict[str, Any]:
    from app.agents.inlinks.extrator import extrair_pilar
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    url_alvo = estado.get("url_alvo", "")
    await publish_event(eid, "node_start", "extrair_alvo", f"Extraindo conteudo da URL alvo: {url_alvo}")

    resultado = await extrair_pilar(url_alvo, None)

    alvo_modo = "pleno"
    pseudo_palavras_chave: list[str] = []

    if not resultado.falhou:
        conteudo = resultado.conteudo_md or ""
        n_chars = len(conteudo.strip())
        n_palavras = len(conteudo.split())
        motivo_boilerplate = _detectar_boilerplate(conteudo)
        conteudo_pobre = (
            motivo_boilerplate is not None
            or n_chars < _MIN_ALVO_CHARS
            or n_palavras < _MIN_ALVO_PALAVRAS
        )

        if conteudo_pobre:
            termos_slug = _extrair_termos_slug(resultado.url_canonica or url_alvo)
            url_categoria = _e_url_categoria_produto(resultado.url_canonica or url_alvo)

            if _slug_tem_qualidade(termos_slug) and (url_categoria or n_chars < 200):
                pseudo_md, pseudo_palavras_chave = _construir_pseudo_alvo(
                    resultado.url_canonica or url_alvo,
                    resultado.titulo,
                    termos_slug,
                )
                resultado.conteudo_md = pseudo_md
                resultado.tokens = len(pseudo_md.split())
                alvo_modo = "slug_only"
                logger.info(
                    "%s alvo_modo=slug_only (termos=%s, motivo=%s)",
                    _log_prefix(eid),
                    ", ".join(termos_slug[:5]),
                    motivo_boilerplate or f"{n_palavras} palavras",
                )
            else:
                resultado.falhou = True
                if motivo_boilerplate:
                    resultado.erro = (
                        f"URL alvo nao tem conteudo redacional util: {motivo_boilerplate}. "
                        f"Tambem nao foi possivel extrair palavras-chave significativas do slug. "
                        f"Use URL de artigo ou landing page com texto."
                    )
                else:
                    resultado.erro = (
                        f"URL alvo extraida com conteudo insuficiente ({n_palavras} palavras, "
                        f"{n_chars} caracteres). Minimo: {_MIN_ALVO_PALAVRAS} palavras. "
                        f"Slug da URL tambem nao tem palavras-chave significativas."
                    )

    if resultado.falhou:
        await publish_event(eid, "node_complete", "extrair_alvo", f"Falha ao extrair alvo: {resultado.erro}")
    else:
        sufixo = " (modo slug_only)" if alvo_modo == "slug_only" else ""
        await publish_event(eid, "node_complete", "extrair_alvo", f"Alvo extraido: {resultado.tokens} tokens{sufixo}")

    return {
        "alvo_resultado": {
            "url": resultado.url,
            "url_canonica": resultado.url_canonica,
            "conteudo_md": resultado.conteudo_md,
            "titulo": resultado.titulo,
            "tokens": resultado.tokens,
            "html_hash": resultado.html_hash,
            "falhou": resultado.falhou,
            "erro": resultado.erro,
            "alvo_modo": alvo_modo,
            "pseudo_palavras_chave": pseudo_palavras_chave,
        },
        "alvo_modo": alvo_modo,
    }


async def node_extrair_candidatas(estado: EstadoDistribuir) -> dict[str, Any]:
    from app.agents.inlinks.extrator import extrair_candidatas
    from app.core.scraper import ScrapeResult
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    urls = estado.get("candidatas_urls", [])
    await publish_event(eid, "node_start", "extrair_candidatas", f"Extraindo {len(urls)} URLs candidatas...")

    async def _on_progress(feito: int, total: int, r: ScrapeResult) -> None:
        sufixo = "(cache)" if r.cache_hit else ("falhou" if r.falhou else "ok")
        await publish_event(
            eid, "node_progress", "extrair_candidatas",
            f"Extraindo URL {feito}/{total} {sufixo}",
        )

    lote = await extrair_candidatas(urls, on_progress=_on_progress)

    await publish_event(
        eid, "node_complete", "extrair_candidatas",
        f"Extraidas {lote.n_sucessos}/{len(urls)} candidatas ({lote.n_falhas} falhas)",
    )

    resultados = [
        {
            "url": r.url,
            "url_canonica": r.url_canonica,
            "conteudo_md": r.conteudo_md,
            "titulo": r.titulo,
            "tokens": r.tokens,
            "html_hash": r.html_hash,
            "falhou": r.falhou,
            "erro": r.erro,
        }
        for r in lote.resultados
    ]

    return {
        "candidatas_resultados": resultados,
        "n_candidatas_validas": lote.n_sucessos,
        "n_candidatas_falhas": lote.n_falhas,
    }


async def node_enriquecer(estado: EstadoDistribuir) -> dict[str, Any]:
    from sqlalchemy import select as sel
    from sqlalchemy.exc import IntegrityError

    from app.agents.inlinks.cleaner import limpar_conteudo
    from app.agents.inlinks.enriquecedor_metadados import enriquecer_metadados
    from app.core.chunker import chunk_texto
    from app.core.embeddings import gerar_embeddings_batch
    from app.core.workflow_events import publish_event
    from app.models.conteudo_vetor import ConteudoVetor

    eid = estado["execucao_id"]
    uid = estado["usuario_id"]
    cliente_id_val = estado.get("cliente_id")
    await publish_event(eid, "node_start", "enriquecer", "Consultando banco vetorial...")

    alvo = estado.get("alvo_resultado", {})
    candidatas = estado.get("candidatas_resultados", [])
    alvo_modo = estado.get("alvo_modo", "pleno")

    todas_urls = []
    if alvo.get("conteudo_md") and not alvo.get("falhou"):
        todas_urls.append({
            "url": alvo.get("url", ""),
            "url_canonica": alvo.get("url_canonica", alvo.get("url", "")),
            "conteudo_md": alvo.get("conteudo_md", ""),
            "titulo": alvo.get("titulo", ""),
            "html_hash": alvo.get("html_hash"),
            "is_alvo": True,
        })
    for c in candidatas:
        if c.get("falhou") or not c.get("conteudo_md"):
            continue
        todas_urls.append({
            "url": c.get("url", ""),
            "url_canonica": c.get("url_canonica", c.get("url", "")),
            "conteudo_md": c.get("conteudo_md", ""),
            "titulo": c.get("titulo", ""),
            "html_hash": c.get("html_hash"),
            "is_alvo": False,
        })

    alvo_embedding = None
    alvo_metadados: dict[str, Any] = {}
    candidatas_embeddings: list[dict[str, Any]] = []
    alvo_chunk_embeddings: list[list[float]] = []

    async with async_session_factory() as session:
        n_reused = 0
        n_cold = 0

        for item in todas_urls:
            url_c = item["url_canonica"]
            html_hash = item.get("html_hash")
            titulo = item.get("titulo", "")

            existing_rows = []
            if html_hash:
                stmt = (
                    sel(ConteudoVetor)
                    .where(
                        ConteudoVetor.usuario_id == uid,
                        ConteudoVetor.url_canonica == url_c,
                        ConteudoVetor.html_hash == html_hash,
                        ConteudoVetor.ativo,
                        ConteudoVetor.tipo_recurso.in_(["pilar", "pilar_slug_only", "candidata"]),
                    )
                    .order_by(ConteudoVetor.chunk_index)
                )
                result = await session.execute(stmt)
                existing_rows = result.scalars().all()

            if existing_rows:
                n_reused += 1
                meta_dict = {
                    "tipo": existing_rows[0].tipo,
                    "intencao": existing_rows[0].intencao,
                    "palavras_chave": existing_rows[0].palavras_chave or [],
                    "entidades": existing_rows[0].atividades or [],
                    "resumo": existing_rows[0].resumo or "",
                    "categoria": existing_rows[0].categoria or "",
                }

                for row in existing_rows:
                    row_emb = list(row.embedding) if row.embedding is not None else None
                    emb_dict = {
                        "url": item["url"],
                        "url_canonica": url_c,
                        "titulo": titulo,
                        "ordem": row.chunk_index or 0,
                        "embedding": row_emb,
                        **meta_dict,
                    }
                    if item["is_alvo"]:
                        if row_emb:
                            alvo_chunk_embeddings.append(row_emb)
                        if not alvo_metadados:
                            alvo_metadados = meta_dict
                    else:
                        candidatas_embeddings.append(emb_dict)
            else:
                n_cold += 1
                markdown_limpo = await limpar_conteudo(item["conteudo_md"], uid)

                meta = await enriquecer_metadados(markdown_limpo, titulo, uid)
                meta_dict = {
                    "tipo": meta.tipo,
                    "intencao": meta.intencao,
                    "palavras_chave": meta.palavras_chave,
                    "entidades": meta.entidades,
                    "resumo": meta.resumo,
                    "categoria": meta.categoria,
                }

                chunks = chunk_texto(markdown_limpo)

                async def _on_batch(batch_idx: int, total_batches: int, n_proc: int, total: int) -> None:
                    await publish_event(
                        eid, "node_progress", "enriquecer",
                        f"Embeddings batch {batch_idx}/{total_batches} ({n_proc}/{total} chunks)",
                    )

                embeddings = await gerar_embeddings_batch(
                    [ch.texto[:8000] for ch in chunks],
                    uid,
                    on_progress=_on_batch,
                )

                for ch, emb in zip(chunks, embeddings, strict=False):
                    if emb is None:
                        continue

                    vetor = ConteudoVetor(
                        usuario_id=uid,
                        cliente_id=cliente_id_val,
                        execucao_id=eid,
                        titulo=titulo,
                        conteudo=ch.texto,
                        tipo=meta.tipo,
                        intencao=meta.intencao,
                        palavras_chave=meta.palavras_chave,
                        atividades=meta.entidades,
                        embedding=emb,
                        url_canonica=url_c,
                        chunk_index=ch.ordem,
                        tipo_recurso=(
                            "pilar_slug_only" if (item["is_alvo"] and alvo_modo == "slug_only")
                            else "pilar" if item["is_alvo"]
                            else "candidata"
                        ),
                        html_hash=html_hash,
                        tokens=ch.tokens,
                        score_base=0.0,
                        ativo=True,
                        resumo=meta.resumo,
                        categoria=meta.categoria,
                    )
                    try:
                        async with session.begin_nested():
                            session.add(vetor)
                            await session.flush()
                    except IntegrityError:
                        stmt2 = (
                            sel(ConteudoVetor)
                            .where(
                                ConteudoVetor.usuario_id == uid,
                                ConteudoVetor.url_canonica == url_c,
                                ConteudoVetor.chunk_index == ch.ordem,
                                ConteudoVetor.ativo,
                            )
                            .order_by(ConteudoVetor.chunk_index)
                        )
                        result2 = await session.execute(stmt2)
                        existing = result2.scalars().first()
                        if existing and existing.embedding is not None:
                            emb = list(existing.embedding)

                    emb_dict = {
                        "url": item["url"],
                        "url_canonica": url_c,
                        "titulo": titulo,
                        "ordem": ch.ordem,
                        "embedding": emb,
                        **meta_dict,
                    }
                    if item["is_alvo"]:
                        if emb is not None:
                            alvo_chunk_embeddings.append(emb)
                        if not alvo_metadados:
                            alvo_metadados = meta_dict
                    else:
                        candidatas_embeddings.append(emb_dict)

                await session.commit()

    from app.core.embeddings import media_embeddings
    if alvo_chunk_embeddings:
        alvo_embedding = media_embeddings(alvo_chunk_embeddings)

    for emb_dict in candidatas_embeddings:
        e = emb_dict.get("embedding")
        if e is not None and not isinstance(e, list):
            emb_dict["embedding"] = list(e)

    n_emb = len(candidatas_embeddings)
    if n_cold == 0:
        msg = f"Reuso completo: {n_reused} URLs do banco vetorial"
    elif n_reused == 0:
        msg = f"Gerando embeddings + metadados (cold) para {n_cold} URLs"
    else:
        msg = f"Reuso de {n_reused} URLs, {n_cold} URLs novas"

    logger.info("%s enriquecer: candidatas_embeddings=%d (%s)", _log_prefix(eid), n_emb, msg)
    await publish_event(eid, "node_complete", "enriquecer", f"{msg} — {n_emb} chunks")

    return _sanitize({
        "alvo_embedding": alvo_embedding,
        "candidatas_embeddings": candidatas_embeddings,
        "alvo_metadados": alvo_metadados,
    })


async def node_filtrar_similaridade(estado: EstadoDistribuir) -> dict[str, Any]:
    from app.core.embeddings import cosine_seguro
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "filtrar_similaridade", "Filtrando candidatas por similaridade...")

    candidatas_resultados = estado.get("candidatas_resultados", [])

    falhas_extracao: list[dict[str, Any]] = []
    for c in candidatas_resultados:
        if c.get("falhou"):
            falhas_extracao.append({
                "url": c.get("url", ""),
                "url_canonica": c.get("url_canonica", c.get("url", "")),
                "titulo": c.get("titulo", ""),
                "status": "falhou_extracao",
                "motivo": c.get("erro") or "Falha ao extrair conteudo da URL",
            })

    alvo_embedding = estado.get("alvo_embedding")
    if alvo_embedding is None:
        await publish_event(eid, "node_complete", "filtrar_similaridade", "Sem embedding do alvo, nenhuma candidata viavel")
        return _sanitize({
            "candidatas_viaveis": [],
            "candidatas_descartadas": [],
            "falhas_extracao": falhas_extracao,
        })

    candidatas_emb = estado.get("candidatas_embeddings", [])
    threshold = estado.get("threshold_score", 0.6)

    candidatas_por_url = {c.get("url"): c for c in candidatas_resultados if not c.get("falhou")}

    best_by_url: dict[str, dict[str, Any]] = {}
    for c in candidatas_emb:
        url = c.get("url", "")
        emb_c = c.get("embedding")
        if emb_c is None or not url:
            continue

        score = cosine_seguro(alvo_embedding, emb_c)
        existing = best_by_url.get(url)
        if existing is None or score > existing["score_semantico"]:
            info_candidata = candidatas_por_url.get(url, {})
            best_by_url[url] = {
                "url": url,
                "url_canonica": c.get("url_canonica", url),
                "titulo": c.get("titulo", info_candidata.get("titulo", "")),
                "resumo": c.get("resumo", ""),
                "palavras_chave": c.get("palavras_chave", []),
                "score_semantico": score,
                "conteudo_md": info_candidata.get("conteudo_md", ""),
            }

    alvo_modo = estado.get("alvo_modo", "pleno")
    if alvo_modo == "slug_only":
        threshold_efetivo = max(threshold * _FATOR_SLUG_ONLY, _PISO_SLUG_ONLY)
        palavras_alvo = estado.get("alvo_resultado", {}).get("pseudo_palavras_chave", [])
        logger.info(
            "%s slug_only: threshold %.2f -> efetivo %.2f (palavras_alvo=%s)",
            _log_prefix(eid),
            threshold,
            threshold_efetivo,
            ", ".join(palavras_alvo[:5]),
        )
    else:
        threshold_efetivo = threshold
        palavras_alvo = []

    viaveis: list[dict[str, Any]] = []
    descartadas: list[dict[str, Any]] = []

    for c in best_by_url.values():
        score = c["score_semantico"]
        if score >= threshold_efetivo:
            c["motivo_viavel"] = f"cosine {score:.2f} >= threshold {threshold_efetivo:.2f}"
            viaveis.append(c)
        elif alvo_modo == "slug_only" and score >= _PISO_SLUG_ONLY:
            if _candidata_tem_keyword_alvo(c.get("conteudo_md", ""), palavras_alvo):
                c["motivo_viavel"] = (
                    f"cosine {score:.2f} baixo, mas candidata contem palavras do slug literalmente"
                )
                logger.info(
                    "%s keyword override: %s (cosine=%.2f)",
                    _log_prefix(eid),
                    c.get("url", ""),
                    score,
                )
                viaveis.append(c)
            else:
                descartadas.append(c)
        else:
            descartadas.append(c)

    viaveis.sort(key=lambda x: x["score_semantico"], reverse=True)
    descartadas.sort(key=lambda x: x["score_semantico"], reverse=True)

    n_viaveis = len(viaveis)
    n_descartadas = len(descartadas)
    n_falhas = len(falhas_extracao)
    await publish_event(
        eid, "node_complete", "filtrar_similaridade",
        f"{n_viaveis} candidatas viaveis, {n_descartadas} sem similaridade suficiente, {n_falhas} falhas na extracao",
    )
    return _sanitize({
        "candidatas_viaveis": viaveis,
        "candidatas_descartadas": descartadas,
        "falhas_extracao": falhas_extracao,
    })


async def node_inserir_em_cada(estado: EstadoDistribuir) -> dict[str, Any]:
    from app.agents.inlinks.inseridor import inserir_inlinks
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    uid = estado["usuario_id"]
    alvo = estado.get("alvo_resultado", {})
    candidatas_viaveis = estado.get("candidatas_viaveis", [])
    candidatas_descartadas = estado.get("candidatas_descartadas", [])
    falhas_extracao = estado.get("falhas_extracao", [])
    max_inlinks = estado.get("max_inlinks_por_candidata", 1)
    estado.get("rel_attr", "noopener")
    threshold = estado.get("threshold_score", 0.6)
    ancoras_pref: list[str] = estado.get("ancoras_preferidas", [])

    resultados: list[dict[str, Any]] = []

    for c in falhas_extracao:
        resultados.append(c)

    for c in candidatas_descartadas:
        resultados.append({
            "url": c["url"],
            "url_canonica": c.get("url_canonica", c["url"]),
            "titulo": c.get("titulo", ""),
            "status": "sem_match",
            "score_semantico": c.get("score_semantico"),
            "motivo": (
                f"Similaridade {c['score_semantico']:.2f} abaixo do threshold {threshold:.2f}. "
                f"O conteudo da candidata nao tem tema suficientemente proximo da URL alvo."
            ),
        })

    if not candidatas_viaveis:
        await publish_event(eid, "node_complete", "inserir_em_cada", f"Nenhuma candidata viavel para inserir ({len(resultados)} ja processadas)")
        return _sanitize({"candidatas_processadas": resultados})

    await publish_event(
        eid, "node_start", "inserir_em_cada",
        f"Inserindo link para URL alvo em {len(candidatas_viaveis)} candidatas...",
    )

    alvo_base = {
        "url": alvo.get("url_canonica", alvo.get("url", "")),
        "url_canonica": alvo.get("url_canonica", alvo.get("url", "")),
        "titulo": alvo.get("titulo", ""),
        "url_destino": alvo.get("url_canonica", alvo.get("url", "")),
        "resumo": estado.get("alvo_metadados", {}).get("resumo", ""),
        "palavras_chave": estado.get("alvo_metadados", {}).get("palavras_chave", []),
        "categoria": estado.get("alvo_metadados", {}).get("categoria", ""),
    }

    semaforo = asyncio.Semaphore(10)
    lock = asyncio.Lock()

    async def _inserir_candidata(idx: int, candidata: dict[str, Any]):
        url = candidata["url"]
        conteudo_md = candidata.get("conteudo_md", "")

        if not conteudo_md:
            async with lock:
                resultados.append({
                    "url": url,
                    "url_canonica": candidata.get("url_canonica", url),
                    "titulo": candidata.get("titulo", ""),
                    "status": "sem_match",
                    "motivo": "Conteudo vazio",
                })
            return

        # Usa o cosine real alvo x candidata calculado em node_filtrar_similaridade.
        # Sem reranker LLM nesta ferramenta, score_total = score_semantico.
        score_real = float(candidata.get("score_semantico", 0.5))
        candidato_alvo = {
            **alvo_base,
            "score_semantico": score_real,
            "score_contexto": score_real,
            "score_total": score_real,
        }

        async with semaforo:
            try:
                markdown_modificado, inseridos = await inserir_inlinks(
                    conteudo_md, [candidato_alvo], uid, max_inlinks=max_inlinks,
                    ancoras_preferidas=ancoras_pref or None,
                )
            except Exception as e:
                logger.error("%s inserir_candidata falhou %s: %s", _log_prefix(eid), url, e)
                async with lock:
                    resultados.append({
                        "url": url,
                        "url_canonica": candidata.get("url_canonica", url),
                        "titulo": candidata.get("titulo", ""),
                        "status": "falhou_extracao",
                        "motivo": f"Erro ao inserir: {str(e)[:200]}",
                    })
                return

        async with lock:
            feito = idx + 1
            await publish_event(
                eid, "node_progress", "inserir_em_cada",
                f"Inserido em candidata {feito}/{len(candidatas_viaveis)}",
            )

        if not inseridos:
            async with lock:
                resultados.append({
                    "url": url,
                    "url_canonica": candidata.get("url_canonica", url),
                    "titulo": candidata.get("titulo", ""),
                    "status": "sem_match",
                    "motivo": "Inseridor nao encontrou trecho adequado para ancora",
                    "score_semantico": candidata.get("score_semantico"),
                })
            return

        il = inseridos[0]
        async with lock:
            resultados.append({
                "url": url,
                "url_canonica": candidata.get("url_canonica", url),
                "titulo": candidata.get("titulo", ""),
                "status": il.status,
                "markdown_modificado": markdown_modificado,
                "anchor_text": il.anchor_text,
                "trecho_original": il.trecho_original,
                "paragrafo_idx": il.paragrafo_idx,
                "score_total": float(il.score_total),
                "score_semantico": float(il.score_semantico),
                "score_contexto": float(il.score_contexto),
                "justificativa": il.motivo_contexto or il.motivo_sugestao,
                "motivo_rejeicao": il.motivo_rejeicao,
                "trecho_contexto": il.trecho_contexto,
                "categoria_match": il.categoria_match,
                "ancora_preferida_usada": il.ancora_preferida_usada,
            })

    tasks = [_inserir_candidata(i, c) for i, c in enumerate(candidatas_viaveis)]
    await asyncio.gather(*tasks)

    n_aplicadas = sum(1 for r in resultados if r["status"] == "aplicado")
    n_sugestoes = sum(1 for r in resultados if r["status"] == "sugestao_manual")
    n_sem = sum(1 for r in resultados if r["status"] == "sem_match")
    n_falhas = sum(1 for r in resultados if r["status"] == "falhou_extracao")

    await publish_event(
        eid, "node_complete", "inserir_em_cada",
        f"Resultado: {n_aplicadas} aplicadas, {n_sugestoes} sugestoes, {n_sem} sem match, {n_falhas} falhas",
    )
    return _sanitize({"candidatas_processadas": resultados})


async def node_persistir(estado: EstadoDistribuir) -> dict[str, Any]:
    from app.core.workflow_events import publish_event
    from app.models.inlink_sugerido import InlinkSugerido
    from app.services import ferramenta_service

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "persistir", "Persistindo resultados...")

    candidatas = estado.get("candidatas_processadas", [])
    alvo = estado.get("alvo_resultado", {})
    url_alvo = alvo.get("url_canonica", alvo.get("url", ""))

    n_aplicadas = sum(1 for c in candidatas if c["status"] == "aplicado")
    n_sugestoes = sum(1 for c in candidatas if c["status"] == "sugestao_manual")
    n_sem_match = sum(1 for c in candidatas if c["status"] == "sem_match")
    n_falhas = sum(1 for c in candidatas if c["status"] == "falhou_extracao")
    n_validas = estado.get("n_candidatas_validas", 0)

    async with async_session_factory() as session:
        versao_n = 1
        from sqlalchemy import select as sel

        from app.models.versao_artigo import VersaoArtigo

        existing = await session.execute(
            sel(VersaoArtigo).where(VersaoArtigo.execucao_id == eid).order_by(VersaoArtigo.versao.desc())
        )
        ultima = existing.scalar_one_or_none()
        if ultima:
            versao_n = ultima.versao + 1

        idx_versao = 0
        bulk_objs = []
        for c in candidatas:
            if c["status"] == "aplicado" and c.get("markdown_modificado"):
                origem = f"distribuir_v{idx_versao}"[:30]
                await ferramenta_service.salvar_versao(
                    session,
                    execucao_id=eid,
                    versao=versao_n + idx_versao,
                    origem=origem,
                    titulo=c.get("titulo", f"Candidata {idx_versao}")[:500],
                    conteudo_markdown=c["markdown_modificado"],
                    contagem_palavras=len(c["markdown_modificado"].split()),
                )
                idx_versao += 1

            if c["status"] in ("aplicado", "sugestao_manual"):
                motivo_final = c.get("motivo_rejeicao") or c.get("justificativa")
                bulk_objs.append(InlinkSugerido(
                    execucao_id=eid,
                    url_origem=c.get("url_canonica", c["url"]),
                    url_destino=url_alvo,
                    anchor_text=c.get("anchor_text", ""),
                    paragrafo_idx=c.get("paragrafo_idx", 0),
                    offset_chars=0,
                    score_total=c.get("score_total", 0),
                    score_semantico=c.get("score_semantico", 0),
                    score_contexto=c.get("score_contexto", 0),
                    status=c["status"],
                    motivo_rejeicao=motivo_final,
                    rel_attr=estado.get("rel_attr", "noopener"),
                    trecho_contexto=c.get("trecho_contexto"),
                    titulo_destino=alvo.get("titulo", ""),
                    trecho_original=c.get("trecho_original"),
                    categoria_match=c.get("categoria_match"),
                ))

        if bulk_objs:
            session.add_all(bulk_objs)
            await session.flush()

        await session.commit()

    resultado_final = {
        "url_alvo": url_alvo,
        "titulo_alvo": alvo.get("titulo", ""),
        "alvo_modo": alvo.get("alvo_modo", "pleno"),
        "n_candidatas_validas": n_validas,
        "n_aplicadas": n_aplicadas,
        "n_sugestoes": n_sugestoes,
        "n_sem_match": n_sem_match,
        "n_falhas": n_falhas,
        "candidatas": [
            {
                "url": c["url"],
                "url_canonica": c.get("url_canonica", c["url"]),
                "titulo": c.get("titulo", ""),
                "status": c["status"],
                "anchor_text": c.get("anchor_text"),
                "trecho_original": c.get("trecho_original"),
                "paragrafo_idx": c.get("paragrafo_idx"),
                "justificativa": c.get("justificativa"),
                "score_total": c.get("score_total"),
                "score_semantico": c.get("score_semantico"),
                "motivo": c.get("motivo"),
                "markdown_modificado": c.get("markdown_modificado"),
                "trecho_contexto": c.get("trecho_contexto"),
                "categoria_match": c.get("categoria_match"),
                "ancora_preferida_usada": c.get("ancora_preferida_usada"),
            }
            for c in candidatas
        ],
    }

    await publish_event(eid, "node_complete", "persistir", "Resultados persistidos")
    return _sanitize({"resultado_final": resultado_final})


def _rota_apos_extrair_alvo(estado: EstadoDistribuir) -> str:
    if estado.get("alvo_resultado", {}).get("falhou"):
        return "persistir_falha_alvo"
    return "extrair_candidatas"


async def node_persistir_falha_alvo(estado: EstadoDistribuir) -> dict[str, Any]:
    eid = estado["execucao_id"]
    alvo = estado.get("alvo_resultado", {})
    from app.core.workflow_events import publish_event
    await publish_event(eid, "node_start", "persistir_falha_alvo", "Alvo invalido — finalizando sem processar candidatas")
    resultado_final = {
        "url_alvo": alvo.get("url_canonica", alvo.get("url", "")),
        "titulo_alvo": alvo.get("titulo", ""),
        "alvo_modo": alvo.get("alvo_modo", "pleno"),
        "n_candidatas_validas": 0,
        "n_aplicadas": 0,
        "n_sugestoes": 0,
        "n_sem_match": 0,
        "n_falhas": 0,
        "candidatas": [],
        "alvo_invalido": True,
        "motivo_alvo": alvo.get("erro", "URL alvo nao processavel"),
    }
    await publish_event(eid, "node_complete", "persistir_falha_alvo", f"Alvo invalido: {alvo.get('erro', 'erro desconhecido')[:100]}")
    return _sanitize({"resultado_final": resultado_final})


def criar_workflow_distribuir(checkpointer=None):
    workflow = StateGraph(EstadoDistribuir)

    workflow.add_node("validar_urls", node_validar_urls)
    workflow.add_node("extrair_alvo", node_extrair_alvo)
    workflow.add_node("extrair_candidatas", node_extrair_candidatas)
    workflow.add_node("enriquecer", node_enriquecer)
    workflow.add_node("filtrar_similaridade", node_filtrar_similaridade)
    workflow.add_node("inserir_em_cada", node_inserir_em_cada)
    workflow.add_node("persistir", node_persistir)
    workflow.add_node("persistir_falha_alvo", node_persistir_falha_alvo)

    workflow.set_entry_point("validar_urls")
    workflow.add_edge("validar_urls", "extrair_alvo")
    workflow.add_conditional_edges("extrair_alvo", _rota_apos_extrair_alvo, {
        "extrair_candidatas": "extrair_candidatas",
        "persistir_falha_alvo": "persistir_falha_alvo",
    })
    workflow.add_edge("extrair_candidatas", "enriquecer")
    workflow.add_edge("enriquecer", "filtrar_similaridade")
    workflow.add_edge("filtrar_similaridade", "inserir_em_cada")
    workflow.add_edge("inserir_em_cada", "persistir")
    workflow.add_edge("persistir", END)
    workflow.add_edge("persistir_falha_alvo", END)

    return workflow.compile(checkpointer=checkpointer)


async def executar_workflow_distribuir_inlinks(execucao_id: str, ctx: dict[str, Any] | None = None) -> None:
    from app.services import ferramenta_service

    try:
        async with async_session_factory() as session:
            await ferramenta_service.atualizar_execucao(session, execucao_id, status="executando")
            await session.commit()

            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if not execucao:
                return

            entrada = execucao.entrada_json

        estado_inicial: EstadoDistribuir = {
            "execucao_id": execucao_id,
            "usuario_id": str(execucao.usuario_id),
            "cliente_id": str(execucao.cliente_id) if execucao.cliente_id else None,
            "url_alvo": entrada.get("url_alvo", ""),
            "candidatas_urls": entrada.get("candidatas_urls", []),
            "threshold_score": entrada.get("threshold_score", 0.6),
            "max_inlinks_por_candidata": entrada.get("max_inlinks_por_candidata", 1),
            "rel_attr": entrada.get("rel_attr", "noopener"),
            "ancoras_preferidas": entrada.get("ancoras_preferidas", []),
        }

        timeout = getattr(settings, "workflow_distribuir_inlinks_timeout", 1800)
        checkpointer = await _resolver_checkpointer(ctx)
        workflow = criar_workflow_distribuir(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": f"distribuir_{execucao_id}"}}
        await asyncio.wait_for(
            _run_workflow_distribuir(workflow, estado_inicial, config, execucao_id),
            timeout=timeout,
        )

    except asyncio.CancelledError:
        logger.info("%s Workflow distribuir cancelado", _log_prefix(execucao_id))
        async with async_session_factory() as session:
            from app.services import credito_service

            execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
            if execucao and execucao.status == "executando":
                reserva = ferramenta_service._obter_reserva_estimada("distribuir_inlinks", execucao)
                if reserva > 0:
                    await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
                await ferramenta_service.atualizar_execucao(
                    session, execucao_id, status="cancelada", creditos_cobrados=0,
                )
                await session.commit()
        raise

    except TimeoutError:
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Workflow distribuir inlinks excedeu o tempo limite", ferramenta="distribuir_inlinks")
            await session.commit()
    except Exception as e:
        logger.error("%s Workflow distribuir falhou: %s", _log_prefix(execucao_id), e)
        async with async_session_factory() as session:
            await ferramenta_service.finalizar_falha(session, execucao_id, "Erro interno do workflow distribuir inlinks", ferramenta="distribuir_inlinks")
            await session.commit()


async def _run_workflow_distribuir(workflow, estado_inicial, config, execucao_id: str) -> None:
    from app.services import ferramenta_service

    async for _event in workflow.astream(estado_inicial, config=config, version="v2"):
        pass

    snapshot = await workflow.aget_state(config)
    estado_final = snapshot.values if snapshot else None

    async with async_session_factory() as session:
        execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
        if execucao and execucao.status == "executando":
            resultado = _extrair_resultado_distribuir(estado_final)
            await ferramenta_service.finalizar_sucesso_distribuir_inlinks(session, execucao_id, resultado)
            await session.commit()


def _extrair_resultado_distribuir(estado: dict[str, Any] | None) -> dict[str, Any]:
    if not estado:
        return {"candidatas": [], "n_aplicadas": 0, "n_sugestoes": 0, "n_sem_match": 0, "n_falhas": 0}

    resultado = estado.get("resultado_final", {})
    if resultado:
        return resultado

    return {
        "url_alvo": estado.get("alvo_resultado", {}).get("url_canonica", ""),
        "titulo_alvo": estado.get("alvo_resultado", {}).get("titulo", ""),
        "n_candidatas_validas": estado.get("n_candidatas_validas", 0),
        "n_aplicadas": 0,
        "n_sugestoes": 0,
        "n_sem_match": 0,
        "n_falhas": 0,
        "candidatas": [],
    }
