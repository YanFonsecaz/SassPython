"""Testes do auto-avaliador de itens manuais SEOTec.

Valida os avaliadores HTML (breadcrumbs, nav, footer, rel=author, etc.)
com snippets de HTML positivo/negativo, e o avaliador de URLs.
"""
from app.services.seotec_auto_avaliador import (
    _avaliar_avaliacoes_clientes,
    _avaliar_backlink_blog,
    _avaliar_barra_navegacao,
    _avaliar_biografia_autor,
    _avaliar_breadcrumbs,
    _avaliar_breadcrumbs_clicaveis,
    _avaliar_conteudo_escondido,
    _avaliar_conteudo_html_nao_js,
    _avaliar_h1_acima_dobra,
    _avaliar_otimizacao_url,
    _avaliar_rel_author,
    _avaliar_rodape,
    avaliar_manual_site,
)
from app.services.seotec_page_fetcher import PaginaBaixada, PaginasSite


def _site(home_html="", blog_html="", produto_html=""):
    s = PaginasSite(dominio="https://exemplo.com")
    if home_html:
        s.paginas["homepage"] = PaginaBaixada("https://exemplo.com", 200, home_html)
    if blog_html:
        s.paginas["blog"] = PaginaBaixada("https://exemplo.com/blog", 200, blog_html)
    if produto_html:
        s.paginas["produto"] = PaginaBaixada("https://exemplo.com/produto/x", 200, produto_html)
    return s


class TestBarraNavegacao:
    def test_aprovado_com_nav_e_links(self):
        html = "<html><body><nav><a href='/'>Home</a><a href='/sobre'>Sobre</a><a href='/blog'>Blog</a><a href='/contato'>Contato</a><a href='/faq'>FAQ</a></nav></body></html>"
        r = _avaliar_barra_navegacao(_site(html))
        assert r.status == "aprovado"
        assert r.evidencias["links_nav"] >= 5

    def test_reprovado_sem_nav(self):
        html = "<html><body><div>sem nav</div></body></html>"
        r = _avaliar_barra_navegacao(_site(html))
        assert r.status == "reprovado"

    def test_sem_dados_homepage_vazia(self):
        r = _avaliar_barra_navegacao(_site())
        assert r.status == "sem_dados"


class TestRodape:
    def test_aprovado_com_footer_links(self):
        html = "<html><body><footer><a href='/sobre'>Sobre</a><a href='/privacidade'>Privacidade</a><a href='/termos'>Termos</a></footer></body></html>"
        r = _avaliar_rodape(_site(html))
        assert r.status == "aprovado"

    def test_reprovado_sem_footer(self):
        html = "<html><body><div>conteudo</div></body></html>"
        r = _avaliar_rodape(_site(html))
        assert r.status == "reprovado"


class TestBreadcrumbs:
    def test_aprovado_todas_paginas_com_breadcrumb(self):
        html = "<html><body><nav class='breadcrumb'><a href='/'>Home</a> > <a href='/cat'>Categoria</a></nav></body></html>"
        site = PaginasSite(dominio="https://x.com")
        site.paginas["p1"] = PaginaBaixada("https://x.com/p1", 200, html)
        site.paginas["p2"] = PaginaBaixada("https://x.com/p2", 200, html)
        r = _avaliar_breadcrumbs(site)
        assert r.status == "aprovado"

    def test_atencao_apenas_algumas_paginas(self):
        html_com = "<html><body><nav class='breadcrumb'>bc</nav></body></html>"
        html_sem = "<html><body>sem bc</body></html>"
        site = PaginasSite(dominio="https://x.com")
        site.paginas["p1"] = PaginaBaixada("https://x.com/p1", 200, html_com)
        site.paginas["p2"] = PaginaBaixada("https://x.com/p2", 200, html_sem)
        r = _avaliar_breadcrumbs(site)
        assert r.status == "atencao"

    def test_reprovado_nenhuma_pagina_com_breadcrumb(self):
        html = "<html><body>sem bc</body></html>"
        site = PaginasSite(dominio="https://x.com")
        site.paginas["p1"] = PaginaBaixada("https://x.com/p1", 200, html)
        r = _avaliar_breadcrumbs(site)
        assert r.status == "reprovado"


class TestRelAuthor:
    def test_aprovado_com_rel_author(self):
        html = '<html><body><a rel="author" href="/author/joao">Joao</a></body></html>'
        site = _site(html)
        r = _avaliar_rel_author(site)
        assert r.status == "aprovado"

    def test_reprovado_sem_rel_author(self):
        html = "<html><body><a href='/author'>Autor</a></body></html>"
        site = _site(html)
        r = _avaliar_rel_author(site)
        assert r.status == "reprovado"


class TestBiografiaAutor:
    def test_aprovado_com_schema_author(self):
        html = '<html><body><div itemprop="author" itemtype="http://schema.org/Person">Joao Silva</div></body></html>'
        r = _avaliar_biografia_autor(_site(html))
        assert r.status == "aprovado"

    def test_atencao_sem_author(self):
        html = "<html><body><article>Post</article></body></html>"
        r = _avaliar_biografia_autor(_site(html))
        assert r.status == "atencao"


class TestAvaliacoesClientes:
    def test_aprovado_com_aggregate_rating(self):
        html = '<html><body><div itemtype="https://schema.org/AggregateRating"><span>4.5</span></div></body></html>'
        r = _avaliar_avaliacoes_clientes(_site(produto_html=html))
        assert r.status == "aprovado"

    def test_atencao_sem_reviews(self):
        html = "<html><body><h1>Produto</h1></body></html>"
        r = _avaliar_avaliacoes_clientes(_site(produto_html=html))
        assert r.status == "atencao"


class TestConteudoHTML:
    def test_aprovado_texto_visivel_suficiente(self):
        html = "<html><body>" + "<p>Conteudo real da pagina com texto suficiente para passar no teste.</p>" * 10 + "</body></html>"
        r = _avaliar_conteudo_html_nao_js(_site(html))
        assert r.status == "aprovado"

    def test_reprovado_pagina_quase_vazia(self):
        html = "<html><body><div></div></body></html>"
        r = _avaliar_conteudo_html_nao_js(_site(html))
        assert r.status == "reprovado"


class TestConteudoEscondido:
    def test_aprovado_sem_escondidos(self):
        html = "<html><body><p>texto visivel</p></body></html>"
        r = _avaliar_conteudo_escondido(_site(html))
        assert r.status == "aprovado"

    def test_reprovado_muitos_escondidos(self):
        blocos = "".join(
            f'<div style="display:none">{"x" * 80}</div>' for _ in range(5)
        )
        html = f"<html><body>{blocos}</body></html>"
        r = _avaliar_conteudo_escondido(_site(html))
        assert r.status == "reprovado"


class TestH1AcimaDobra:
    def test_aprovado_h1_no_inicio(self):
        html = '<html><body><h1>Titulo Principal</h1>' + "<p>x</p>" * 500 + "</body></html>"
        r = _avaliar_h1_acima_dobra(_site(html))
        assert r.status == "aprovado"

    def test_reprovado_h1_no_final(self):
        html = "<html><body>" + "<p>x</p>" * 500 + '<h1>Titulo</h1></body></html>'
        r = _avaliar_h1_acima_dobra(_site(html))
        assert r.status == "reprovado"

    def test_sem_dados_sem_h1(self):
        html = "<html><body><p>sem h1</p></body></html>"
        r = _avaliar_h1_acima_dobra(_site(html))
        assert r.status == "sem_dados"


class TestOtimizacaoURL:
    def test_aprovado_urls_com_hifens(self):
        urls = [
            {"address": "https://x.com/como-fazer-seo"},
            {"address": "https://x.com/blog/marketing-digital"},
            {"address": "https://x.com/faq/perguntas-frequentes"},
        ]
        r = _avaliar_otimizacao_url(urls)
        assert r.status == "aprovado"

    def test_reprovado_urls_com_underscore_e_query(self):
        urls = [
            {"address": "https://x.com/como_fazer_seo?id=12345678901234567890"},
            {"address": "https://x.com/blog_marketing_digital?ref=xyz"},
        ]
        r = _avaliar_otimizacao_url(urls)
        assert r.status == "reprovado"

    def test_sem_dados_lista_vazia(self):
        r = _avaliar_otimizacao_url([])
        assert r.status == "sem_dados"


class TestBacklinkBlog:
    def test_aprovado_hp_e_blog_se_linkam(self):
        hp_html = '<html><body><a href="https://exemplo.com/blog">Blog</a></body></html>'
        blog_html = '<html><body><a href="https://exemplo.com">Home</a></body></html>'
        r = _avaliar_backlink_blog(_site(hp_html, blog_html))
        assert r.status == "aprovado"

    def test_atencao_hp_nao_linka_para_blog_mas_blog_linka_hp(self):
        hp_html = "<html><body><p>sem link blog</p></body></html>"
        blog_html = '<html><body><a href="https://exemplo.com">Home</a></body></html>'
        r = _avaliar_backlink_blog(_site(hp_html, blog_html))
        assert r.status == "atencao"

    def test_sem_dados_sem_blog(self):
        hp_html = "<html><body>home</body></html>"
        r = _avaliar_backlink_blog(_site(hp_html))
        assert r.status == "sem_dados"


class TestBreadcrumbsClicaveis:
    def test_aprovado_com_links_clicaveis(self):
        html = '<html><body><nav class="breadcrumb"><a href="/">Home</a> <a href="/cat">Cat</a></nav></body></html>'
        site = PaginasSite(dominio="https://x.com")
        site.paginas["p1"] = PaginaBaixada("https://x.com/p1", 200, html)
        r = _avaliar_breadcrumbs_clicaveis(site)
        assert r.status == "aprovado"


class TestIntegracaoAvaliarManualSite:
    def test_retorna_dict_vazio_quando_sem_paginas(self):
        site = PaginasSite(dominio="https://x.com")
        urls = [{"address": "https://x.com/p1"}]
        r = avaliar_manual_site(site, urls)
        # Otimizacao URL sempre roda
        assert "otimizacao-geral-da-url-usa-de-palavras-chave-segmentadas" in r

    def test_avalia_multiplos_itens_com_html_completo(self):
        html = """
        <html><body>
            <nav><a href="/">Home</a><a href="/sobre">Sobre</a><a href="/blog">Blog</a>
            <a href="/contato">Contato</a><a href="/faq">FAQ</a></nav>
            <nav class="breadcrumb"><a href="/">Home</a> > <a href="/cat">Cat</a></nav>
            <h1>Titulo Principal</h1>
            <p>Conteudo real da pagina com texto suficiente.</p>
            <footer><a href="/sobre">Sobre</a><a href="/termos">Termos</a><a href="/privacidade">Privacidade</a></footer>
            <a rel="author" href="/author/joao">Joao</a>
        </body></html>
        """
        site = _site(html)
        urls = [
            {"address": "https://exemplo.com/como-fazer-seo"},
            {"address": "https://exemplo.com/blog/marketing-digital"},
        ]
        resultados = avaliar_manual_site(site, urls)
        assert len(resultados) >= 5
        assert resultados["ha-uma-barra-de-navegacao-otimizada"].status == "aprovado"
        assert resultados["o-site-tem-rodape-otimizado"].status == "aprovado"
        assert resultados["otimizacao-geral-da-url-usa-de-palavras-chave-segmentadas"].status == "aprovado"
