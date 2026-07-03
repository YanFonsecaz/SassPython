"""Guard reforçado do formatador: pares (âncora, url) idênticos + mutação ≤2%."""
from app.agents.inlinks.formatador import _mutacao_aceitavel, _pares_links

ORIGINAL = (
    "## Introducao\n\n"
    "Este paragrafo fala sobre [loja virtual](https://ex.com/loja) e como comecar a "
    "vender online com pouco investimento inicial no mercado brasileiro atual.\n\n"
    "Um segundo paragrafo bem longo que discute estrategias de marketing digital, "
    "posicionamento de marca e canais de aquisicao pagos e organicos. Cita tambem "
    "[producao de conteudo](https://ex.com/conteudo) como alavanca de crescimento."
)


def test_reparagrafacao_pura_aceita():
    # quebra o 2º parágrafo no ponto final natural, sem mudar texto nem links
    formatado = ORIGINAL.replace(
        "pagos e organicos. Cita tambem ",
        "pagos e organicos.\n\nCita tambem ",
    )
    assert _mutacao_aceitavel(ORIGINAL, formatado)


def test_heading_novo_aceito():
    formatado = ORIGINAL.replace(
        "Um segundo paragrafo bem longo",
        "### Estrategias de marketing\n\nUm segundo paragrafo bem longo",
    )
    assert _mutacao_aceitavel(ORIGINAL, formatado)


def test_mudanca_de_ancora_rejeitada():
    formatado = ORIGINAL.replace("[loja virtual](https://ex.com/loja)", "[loja](https://ex.com/loja)")
    assert not _mutacao_aceitavel(ORIGINAL, formatado)


def test_mudanca_de_url_rejeitada():
    formatado = ORIGINAL.replace("https://ex.com/loja", "https://ex.com/outra")
    assert not _mutacao_aceitavel(ORIGINAL, formatado)


def test_ordem_de_links_trocada_rejeitada():
    a = "[loja virtual](https://ex.com/loja)"
    b = "[producao de conteudo](https://ex.com/conteudo)"
    formatado = ORIGINAL.replace(a, "@@A@@").replace(b, a).replace("@@A@@", b)
    assert not _mutacao_aceitavel(ORIGINAL, formatado)


def test_reescrita_de_texto_rejeitada():
    formatado = ORIGINAL.replace(
        "como comecar a vender online com pouco investimento inicial",
        "estrategias completamente reescritas para conquistar clientes rapidamente",
    )
    assert not _mutacao_aceitavel(ORIGINAL, formatado)


def test_pares_links_extrai_na_ordem():
    assert _pares_links(ORIGINAL) == [
        ("loja virtual", "https://ex.com/loja"),
        ("producao de conteudo", "https://ex.com/conteudo"),
    ]
