from app.core.scraper import _extrair_titulo_html


def test_extrai_og_title():
    html = '<html><head><meta property="og:title" content="Como começar em programação"></head></html>'
    assert _extrair_titulo_html(html) == "Como começar em programação"


def test_extrai_title_tag_e_remove_sufixo_marca():
    html = "<html><head><title>Roadmap de Programação | Hashtag Treinamentos</title></head></html>"
    assert _extrair_titulo_html(html) == "Roadmap de Programação"


def test_fallback_h1_quando_sem_title():
    html = "<html><body><h1>Currículo de Programação</h1></body></html>"
    assert _extrair_titulo_html(html) == "Currículo de Programação"


def test_decodifica_entidades_html():
    html = "<title>Pre&ccedil;o &amp; Valor</title>"
    assert _extrair_titulo_html(html) == "Preço & Valor"


def test_devolve_vazio_sem_pistas():
    assert _extrair_titulo_html("<html><body>nada</body></html>") == ""


def test_descarta_titulos_curtos_demais():
    assert _extrair_titulo_html("<title>OK</title>") == ""
