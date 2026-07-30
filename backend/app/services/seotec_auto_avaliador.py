"""Avaliador automático de itens manuais SEOTec via HTML parse.

Avalia itens que não vêm do Screaming Frog mas podem ser determinados
programaticamente a partir do HTML das páginas do site.

Usa selectolax (parser rápido baseado em C) para extrair:
- Breadcrumbs (HTML + BreadcrumbList schema)
- Barra de navegação (<nav>)
- Rodapé (<footer>)
- rel="author"
- Biografia de autor
- Avaliações de clientes (review schema)
- Conteúdo injetado por HTML (texto visível no raw HTML)
- Conteúdo escondido (display:none/visibility:hidden em blocos de texto)
- H1 acima da dobra (posição no HTML)
- Otimização geral da URL (heuristic)
- Backlink domínio↔blog

Fail-open: se análise falhar ou página não baixada, retorna StatusItem "sem_dados".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

from app.services.seotec_page_fetcher import PaginasSite

logger = logging.getLogger(__name__)


@dataclass
class ResultadoAuto:
    status: str  # "aprovado" | "atencao" | "reprovado" | "sem_dados"
    evidencias: dict


_SEM_DADOS = ResultadoAuto("sem_dados", {})


def _tem_robots_noindex(html: str) -> bool:
    """Verifica se a página tem meta robots noindex (não deve ser avaliada)."""
    if not html:
        return False
    match = re.search(r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']*)["\']', html, re.I)
    return bool(match and "noindex" in match.group(1).lower())


def _text_len(html: str) -> int:
    """Conta caracteres de texto visível (sem tags, sem scripts/styles)."""
    if not html:
        return 0
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript"):
        tag.decompose()
    return len(tree.body.text(separator=" ").strip()) if tree.body else 0


# --- Avaliadores individuais ---

def _avaliar_breadcrumbs(site: PaginasSite) -> ResultadoAuto:
    """Breadcrumbs encontrados e disponíveis em todas as páginas."""
    paginas = [p for p in site.paginas.values() if p.status_code == 200 and p.html]
    if not paginas:
        return _SEM_DADOS

    com_breadcrumb = 0
    for pag in paginas:
        tree = HTMLParser(pag.html)
        nav_bc = tree.css_first("nav.breadcrumb, nav[aria-label='breadcrumb'], .breadcrumb, [itemscope][itemtype*='BreadcrumbList']")
        schema_bc = False
        if "BreadcrumbList" in pag.html:
            schema_bc = True
        if nav_bc or schema_bc:
            com_breadcrumb += 1

    if com_breadcrumb == len(paginas):
        return ResultadoAuto("aprovado", {"paginas_com_breadcrumb": com_breadcrumb, "total": len(paginas)})
    elif com_breadcrumb > 0:
        return ResultadoAuto("atencao", {"paginas_com_breadcrumb": com_breadcrumb, "total": len(paginas)})
    return ResultadoAuto("reprovado", {"paginas_com_breadcrumb": 0, "total": len(paginas)})


def _avaliar_breadcrumbs_clicaveis(site: PaginasSite) -> ResultadoAuto:
    """Breadcrumbs: você pode clicar nas últimas 2-3 páginas?"""
    paginas = [p for p in site.paginas.values() if p.status_code == 200 and p.html]
    if not paginas:
        return _SEM_DADOS

    avaliadas = 0
    todos_clicaveis = True
    for pag in paginas:
        tree = HTMLParser(pag.html)
        bc = tree.css_first("nav.breadcrumb, .breadcrumb, [itemtype*='BreadcrumbList']")
        if bc is None:
            continue
        avaliadas += 1
        links = bc.css("a[href]")
        if len(links) < 2:
            todos_clicaveis = False
            break

    if avaliadas == 0:
        return _SEM_DADOS
    if todos_clicaveis:
        return ResultadoAuto("aprovado", {"breadcrumb_links_min": 2, "paginas_avaliadas": avaliadas})
    return ResultadoAuto("atencao", {"breadcrumb_links_min": 0, "paginas_avaliadas": avaliadas})


def _avaliar_barra_navegacao(site: PaginasSite) -> ResultadoAuto:
    """Há uma barra de navegação otimizada?"""
    hp = site.homepage
    if not hp or not hp.html:
        return _SEM_DADOS

    tree = HTMLParser(hp.html)
    nav = tree.css_first("nav, header nav, [role='navigation']")
    if nav is None:
        return ResultadoAuto("reprovado", {"nav_encontrado": False})

    links = nav.css("a[href]")
    num_links = len(links)
    if num_links >= 5:
        return ResultadoAuto("aprovado", {"nav_encontrado": True, "links_nav": num_links})
    elif num_links > 0:
        return ResultadoAuto("atencao", {"nav_encontrado": True, "links_nav": num_links})
    return ResultadoAuto("reprovado", {"nav_encontrado": True, "links_nav": 0})


def _avaliar_rodape(site: PaginasSite) -> ResultadoAuto:
    """O site tem rodapé otimizado?"""
    hp = site.homepage
    if not hp or not hp.html:
        return _SEM_DADOS

    tree = HTMLParser(hp.html)
    footer = tree.css_first("footer, [role='contentinfo']")
    if footer is None:
        return ResultadoAuto("reprovado", {"footer_encontrado": False})

    links_footer = len(footer.css("a[href]"))
    if links_footer >= 3:
        return ResultadoAuto("aprovado", {"footer_encontrado": True, "links_footer": links_footer})
    elif links_footer > 0:
        return ResultadoAuto("atencao", {"footer_encontrado": True, "links_footer": links_footer})
    return ResultadoAuto("reprovado", {"footer_encontrado": True, "links_footer": 0})


def _avaliar_backlink_blog(site: PaginasSite) -> ResultadoAuto:
    """Há backlink do site (domínio) para o blog e vice-versa?"""
    hp = site.homepage
    blog = site.blog
    if not hp or not hp.html:
        return _SEM_DADOS

    dominio_host = urlparse(site.dominio).hostname or ""

    # Homepage → blog
    hp_tree = HTMLParser(hp.html)
    hp_tem_blog = False
    if blog:
        for a in hp_tree.css("a[href]"):
            href = a.attributes.get("href", "")
            if blog and blog.url in href:
                hp_tem_blog = True
                break
            if "/blog" in href.lower() or "/noticias" in href.lower():
                hp_tem_blog = True
                break

    # Blog → homepage
    blog_tem_hp = False
    if blog and blog.html:
        blog_tree = HTMLParser(blog.html)
        for a in blog_tree.css("a[href]"):
            href = a.attributes.get("href", "")
            if dominio_host in href and "blog" not in href.lower():
                blog_tem_hp = True
                break

    if not site.blog:
        # Sem blog detectado — não aplicável
        return ResultadoAuto("sem_dados", {"motivo": "blog_nao_detectado"})

    if hp_tem_blog and blog_tem_hp:
        return ResultadoAuto("aprovado", {"hp_para_blog": True, "blog_para_hp": True})
    elif hp_tem_blog or blog_tem_hp:
        return ResultadoAuto("atencao", {"hp_para_blog": hp_tem_blog, "blog_para_hp": blog_tem_hp})
    return ResultadoAuto("reprovado", {"hp_para_blog": False, "blog_para_hp": False})


def _avaliar_biografia_autor(site: PaginasSite) -> ResultadoAuto:
    """Página com biografia do autor (blog)."""
    blog = site.blog or site.homepage
    if not blog or not blog.html:
        return _SEM_DADOS

    tree = HTMLParser(blog.html)
    author_el = (
        tree.css_first("[rel='author'], [itemprop='author'], .author-bio, .author-info, .post-author")
    )
    schema_author = '"author"' in blog.html and ('"Person"' in blog.html or '"person"' in blog.html.lower())

    if author_el or schema_author:
        return ResultadoAuto("aprovado", {"author_bio_encontrado": True})
    return ResultadoAuto("atencao", {"author_bio_encontrado": False, "motivo": "sem_elemento_author_visivel"})


def _avaliar_rel_author(site: PaginasSite) -> ResultadoAuto:
    """Implementação de rel='author' (blog)."""
    paginas = [p for p in site.paginas.values() if p.status_code == 200 and p.html]
    if not paginas:
        return _SEM_DADOS

    com_rel_author = 0
    for pag in paginas:
        if 'rel="author"' in pag.html or "rel='author'" in pag.html:
            com_rel_author += 1

    if com_rel_author > 0:
        return ResultadoAuto("aprovado", {"paginas_com_rel_author": com_rel_author, "total": len(paginas)})
    return ResultadoAuto("reprovado", {"paginas_com_rel_author": 0, "total": len(paginas)})


def _avaliar_avaliacoes_clientes(site: PaginasSite) -> ResultadoAuto:
    """Avaliação dos clientes (página de produto) — schema Review/AggregateRating."""
    paginas = [site.produto or site.homepage]
    paginas = [p for p in paginas if p and p.status_code == 200 and p.html]
    if not paginas:
        return _SEM_DADOS

    for pag in paginas:
        tree = HTMLParser(pag.html)
        review_el = tree.css_first(
            "[itemtype*='Review'], [itemtype*='AggregateRating'], .reviews, .product-reviews, [data-rating]"
        )
        schema_review = any(
            kw in pag.html for kw in ['"Review"', '"AggregateRating"', '"ratingValue"', '"reviewCount"']
        )
        if review_el or schema_review:
            return ResultadoAuto("aprovado", {"review_encontrado": True})

    return ResultadoAuto("atencao", {"review_encontrado": False})


def _avaliar_conteudo_html_nao_js(site: PaginasSite) -> ResultadoAuto:
    """Conteúdo injetado por HTML, não JS — texto visível no raw HTML."""
    hp = site.homepage
    if not hp or not hp.html:
        return _SEM_DADOS

    texto_len = _text_len(hp.html)
    # Heurística: se o texto visível do HTML cru tem > 200 chars, o conteúdo está no HTML
    if texto_len > 500:
        return ResultadoAuto("aprovado", {"texto_visivel_chars": texto_len})
    elif texto_len > 200:
        return ResultadoAuto("atencao", {"texto_visivel_chars": texto_len})
    return ResultadoAuto("reprovado", {"texto_visivel_chars": texto_len, "motivo": "conteudo_possivelmente_js"})


def _avaliar_conteudo_escondido(site: PaginasSite) -> ResultadoAuto:
    """Não há conteúdo escondido (display:none em blocos de texto)."""
    hp = site.homepage
    if not hp or not hp.html:
        return _SEM_DADOS

    tree = HTMLParser(hp.html)
    escondidos = 0
    for el in tree.css("[style]"):
        style = el.attributes.get("style", "")
        if "display:none" in style.replace(" ", "").lower() or "visibility:hidden" in style.replace(" ", "").lower():
            texto = el.text(strip=True)
            if len(texto) > 50:
                escondidos += 1

    # Também verificar classes comuns de esconder
    for el in tree.css(".hidden, .sr-only:not(focusable), [aria-hidden='true']"):
        texto = el.text(strip=True)
        if len(texto) > 200:
            escondidos += 1

    if escondidos == 0:
        return ResultadoAuto("aprovado", {"blocos_escondidos": 0})
    elif escondidos <= 2:
        return ResultadoAuto("atencao", {"blocos_escondidos": escondidos})
    return ResultadoAuto("reprovado", {"blocos_escondidos": escondidos})


def _avaliar_h1_acima_dobra(site: PaginasSite) -> ResultadoAuto:
    """Heading H1 acima da dobra — posição no HTML (heurística)."""
    hp = site.homepage
    if not hp or not hp.html:
        return _SEM_DADOS

    tree = HTMLParser(hp.html)
    h1 = tree.css_first("h1")
    if h1 is None:
        return _SEM_DADOS

    # Heurística: calcular a posição do <h1> como fração do HTML total
    h1_pos = hp.html.find("<h1")
    if h1_pos < 0:
        h1_pos = hp.html.lower().find("<h1")
    total_len = len(hp.html)

    if total_len == 0:
        return _SEM_DADOS

    fracao = h1_pos / total_len
    if fracao < 0.15:
        return ResultadoAuto("aprovado", {"h1_pos_fracao": round(fracao, 3)})
    elif fracao < 0.30:
        return ResultadoAuto("atencao", {"h1_pos_fracao": round(fracao, 3)})
    return ResultadoAuto("reprovado", {"h1_pos_fracao": round(fracao, 3)})


def _avaliar_otimizacao_url(urls_internas: list[dict]) -> ResultadoAuto:
    """Otimização geral da URL — usa palavras-chave segmentadas (hífens)."""
    if not urls_internas:
        return _SEM_DADOS

    boas = 0
    ruins = 0
    for linha in urls_internas:
        url = str(linha.get("address") or "")
        if not url:
            continue
        path = urlparse(url).path.strip("/")
        if not path:
            continue
        # URL "boa": usa hífens como separador, sem parâmetros longos, sem camelCase
        tem_hifens = "-" in path
        tem_underscore = "_" in path
        tem_query_longa = len(urlparse(url).query) > 50

        if tem_hifens and not tem_underscore and not tem_query_longa:
            boas += 1
        else:
            ruins += 1

    total = boas + ruins
    if total == 0:
        return _SEM_DADOS

    pct = boas / total
    if pct >= 0.8:
        return ResultadoAuto("aprovado", {"urls_otimizadas_pct": round(pct * 100), "total": total})
    elif pct >= 0.5:
        return ResultadoAuto("atencao", {"urls_otimizadas_pct": round(pct * 100), "total": total})
    return ResultadoAuto("reprovado", {"urls_otimizadas_pct": round(pct * 100), "total": total})


# --- Registro de avaliadores ---

AVALIADORES: dict[str, callable] = {
    "breadcrumbs-encontrados-e-disponiveis-em-todas-as-paginas": _avaliar_breadcrumbs,
    "breadcrumbs-voce-pode-clicar-nas-ultimas-2-3-paginas": _avaliar_breadcrumbs_clicaveis,
    "ha-uma-barra-de-navegacao-otimizada": _avaliar_barra_navegacao,
    "o-site-tem-rodape-otimizado": _avaliar_rodape,
    "ha-backlink-do-site-dominio-para-o-blog-subdominio-e-vice-versa": _avaliar_backlink_blog,
    "pagina-com-biografia-do-autor-blog": _avaliar_biografia_autor,
    "implementacao-de-rel-author-blog": _avaliar_rel_author,
    "avaliacao-dos-clientes-pagina-de-produto": _avaliar_avaliacoes_clientes,
    "conteudo-injetado-por-html-nao-js": _avaliar_conteudo_html_nao_js,
    "nao-ha-conteudo-escondido": _avaliar_conteudo_escondido,
    "heading-h1-acima-da-dobra": _avaliar_h1_acima_dobra,
}


def avaliar_manual_site(
    site: PaginasSite,
    urls_internas: list[dict],
) -> dict[str, ResultadoAuto]:
    """Executa todos os avaliadores aplicáveis.

    Retorna dict[slug, ResultadoAuto] apenas para itens que pôde avaliar.
    """
    resultados: dict[str, ResultadoAuto] = {}

    # Avaliadores que usam PaginasSite
    for slug, func in AVALIADORES.items():
        try:
            resultado = func(site)
            if resultado.status != "sem_dados":
                resultados[slug] = resultado
        except Exception as exc:
            logger.warning("avaliador_erro %s: %s", slug, exc)

    # Otimização de URL (usa URLs do export, não páginas baixadas)
    try:
        r = _avaliar_otimizacao_url(urls_internas)
        if r.status != "sem_dados":
            resultados["otimizacao-geral-da-url-usa-de-palavras-chave-segmentadas"] = r
    except Exception as exc:
        logger.warning("avaliador_url_erro: %s", exc)

    logger.info(
        "auto_avaliador_concluido site=%s avaliados=%d",
        site.dominio, len(resultados),
    )
    return resultados
