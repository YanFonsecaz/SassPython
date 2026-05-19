from app.agents.inlinks.injector import _esta_em_cabecalho, injetar_inlinks, remover_links_rejeitados


def test_remove_apenas_rejeitados():
    md = (
        "Comece com [passos iniciais](https://ex.com/a). "
        "Depois [escolher linguagem](https://ex.com/b). "
        "E por fim [um portfolio](https://ex.com/c)."
    )
    inlinks = [
        {"anchor_text": "passos iniciais", "url_destino": "https://ex.com/a", "status": "aplicado"},
        {"anchor_text": "escolher linguagem", "url_destino": "https://ex.com/b", "status": "rejeitado_revisor"},
        {"anchor_text": "um portfolio", "url_destino": "https://ex.com/c", "status": "aplicado"},
    ]
    saneado = remover_links_rejeitados(md, inlinks)
    assert "[passos iniciais](https://ex.com/a)" in saneado
    assert "[escolher linguagem]" not in saneado
    assert "escolher linguagem" in saneado
    assert "[um portfolio](https://ex.com/c)" in saneado


def test_no_op_quando_todos_aplicados():
    md = "Texto com [link](https://ex.com)."
    inlinks = [{"anchor_text": "link", "url_destino": "https://ex.com", "status": "aplicado"}]
    assert remover_links_rejeitados(md, inlinks) == md


def test_ignora_anchor_ou_url_vazios():
    md = "Texto."
    inlinks = [
        {"anchor_text": "", "url_destino": "https://ex.com", "status": "rejeitado_revisor"},
        {"anchor_text": "x", "url_destino": "", "status": "rejeitado_revisor"},
    ]
    assert remover_links_rejeitados(md, inlinks) == md


def test_detecta_heading_atx():
    md = "Texto comum.\n\n## Título com palavra-chave aqui\n\nMais texto."
    pos_h2 = md.index("palavra-chave")
    pos_normal = md.index("Texto comum")
    assert _esta_em_cabecalho(md, pos_h2) is True
    assert _esta_em_cabecalho(md, pos_normal) is False


def test_detecta_h1_a_h6():
    for prefixo in ["#", "##", "###", "####", "#####", "######"]:
        md = f"{prefixo} Cabeçalho aqui"
        assert _esta_em_cabecalho(md, md.index("aqui")) is True


def test_nao_confunde_hashtag_inline():
    md = "Use a hashtag #python no Twitter."
    assert _esta_em_cabecalho(md, md.index("python")) is False


def test_injector_pula_candidato_em_cabecalho():
    md = (
        "Antes do título.\n\n"
        "## Por que é importante construir um portfólio desde o início?\n\n"
        "Construir um portfólio leva tempo, mas vale a pena no longo prazo."
    )
    candidatos = [{
        "url": "https://ex.com/portfolio",
        "titulo": "Guia de portfólio",
        "ancoras_opcoes": ["construir um portfólio"],
        "score_total": 0.8,
        "score_semantico": 0.85,
        "score_contexto": 0.75,
    }]
    modificado, injetados = injetar_inlinks(md, candidatos)
    assert "## Por que é importante construir um portfólio desde o início?" in modificado
    assert "[Construir um portfólio](https://ex.com/portfolio)" in modificado
    assert len(injetados) == 1
