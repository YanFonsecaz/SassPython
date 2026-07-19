from app.services.seotec_checklist import carregar_checklist, recarregar_checklist
from app.services.seotec_ingestao import ExportNormalizado, PacoteIngestao
from app.services.seotec_motor import avaliar_pacote
from app.services.seotec_motor_custom import (
    cadeias_redirecionamento,
    case_sensitive_urls,
    hierarquia_headings,
    imagens_nome_generico,
    loops_redirecionamento,
    metas_no_head,
    pagina_404_adequada,
    sitemap_otimizado,
    title_igual_h1,
    trailing_slash_misto,
    uso_tipo_schema,
    www_vs_non_www,
)
from tests.unit.test_seotec_motor import _item, _pacote  # reusa builders


def test_cadeias():
    pacote = _pacote(redirects=[
        {"address": "https://a/", "destino_final": "https://c/", "num_hops": 3, "loop": False},
        {"address": "https://b/", "destino_final": "https://d/", "num_hops": 1, "loop": False},
    ])
    r = cadeias_redirecionamento(_item(None, ["address", "destino_final", "num_hops"]), pacote)
    assert r.status == "reprovado"
    assert r.total_afetadas == 1
    assert r.amostra[0]["num_hops"] == 3


def test_loops():
    pacote = _pacote(redirects=[
        {"address": "https://a/", "destino_final": "https://a/", "num_hops": 2, "loop": True},
        {"address": "https://b/", "destino_final": "https://d/", "num_hops": 1, "loop": False},
    ])
    r = loops_redirecionamento(_item(None, ["address", "destino_final"]), pacote)
    assert (r.status, r.total_afetadas) == ("reprovado", 1)


def test_loops_sem_ocorrencia_aprova():
    pacote = _pacote(redirects=[
        {"address": "https://b/", "destino_final": "https://d/", "num_hops": 1, "loop": False},
    ])
    assert loops_redirecionamento(_item(None), pacote).status == "aprovado"


def test_title_igual_h1():
    pacote = _pacote(
        page_titles=[
            {"address": "https://a/", "title": "Mesma Coisa", "title_length": 11, "ocorrencias": 1},
            {"address": "https://b/", "title": "Título", "title_length": 6, "ocorrencias": 1},
        ],
        h1=[
            {"address": "https://a/", "h1": "mesma coisa", "ocorrencias": 1},
            {"address": "https://b/", "h1": "Outro H1", "ocorrencias": 1},
        ],
    )
    r = title_igual_h1(_item(None, ["address", "title", "h1"]), pacote)
    assert r.total_afetadas == 1  # comparação case-insensitive
    assert r.amostra[0]["h1"] == "mesma coisa"


def test_title_igual_h1_sem_export_h1():
    pacote = _pacote(page_titles=[{"address": "https://a/", "title": "X"}])
    assert title_igual_h1(_item(None), pacote).status == "sem_dados"


def test_cadeias_redirecionamento_total_antes_corte():
    """Verifica que total_avaliadas usa total_antes_corte, não len(linhas)."""
    export = ExportNormalizado(
        linhas=[
            {"address": "https://a/", "destino_final": "https://c/", "num_hops": 3, "loop": False},
            {"address": "https://b/", "destino_final": "https://d/", "num_hops": 1, "loop": False},
        ],
        total_antes_corte=600,  # 600 redirecionamentos, mas só 2 retornadas após corte
    )
    pacote = PacoteIngestao(
        schema_version=1, dominio="https://exemplo.com.br",
        exports={"redirects": export}
    )
    r = cadeias_redirecionamento(_item(None, ["address", "destino_final", "num_hops"]), pacote)
    assert r.total_avaliadas == 600, f"Esperava 600 (total_antes_corte), mas recebeu {r.total_avaliadas}"


def test_sitemap_otimizado():
    pacote = _pacote(sitemaps=[
        {"sitemap_url": "https://a/s1.xml", "status_code": 200, "total_urls": 100},
        {"sitemap_url": "https://a/s2.xml", "status_code": 404, "total_urls": 0},
    ])
    r = sitemap_otimizado(_item(None, ["sitemap_url", "status_code", "total_urls"]), pacote)
    assert (r.status, r.total_afetadas) == ("reprovado", 1)


def test_sitemap_otimizado_ok():
    pacote = _pacote(sitemaps=[{"sitemap_url": "https://a/s.xml", "status_code": 200, "total_urls": 50}])
    assert sitemap_otimizado(_item(None), pacote).status == "aprovado"


def test_pagina_404_adequada():
    ok = _pacote(pagina_404=[{"url_testada": "https://a/xyz", "status_code": 404, "soft_404": False}])
    soft = _pacote(pagina_404=[{"url_testada": "https://a/xyz", "status_code": 200, "soft_404": True}])
    assert pagina_404_adequada(_item(None), ok).status == "aprovado"
    assert pagina_404_adequada(_item(None), soft).status == "reprovado"
    assert pagina_404_adequada(_item(None), _pacote()).status == "sem_dados"


def test_pagina_404_export_vazio_sem_dados():
    """Export presente mas zero linhas deve retornar sem_dados, não reprovado fabricado."""
    assert pagina_404_adequada(_item(None), _pacote(pagina_404=[])).status == "sem_dados"


def test_metas_no_head():
    pacote = _pacote(
        page_titles=[
            {"address": "https://a/", "title": "", "title_length": 0, "ocorrencias": 0},
            {"address": "https://b/", "title": "Ok", "title_length": 2, "ocorrencias": 1},
        ],
        meta_description=[
            {"address": "https://a/", "meta_description": "", "meta_description_length": 0, "ocorrencias": 0},
            {"address": "https://b/", "meta_description": "", "meta_description_length": 0, "ocorrencias": 0},
        ],
    )
    r = metas_no_head(_item(None, ["address"]), pacote)
    assert r.total_afetadas == 1  # só a/ não tem NENHUMA meta


def test_hierarquia_headings():
    pacote = _pacote(h1=[
        {"address": "https://a/", "h1": "", "ocorrencias": 0, "h2_ocorrencias": 3},
        {"address": "https://b/", "h1": "Tem", "ocorrencias": 1, "h2_ocorrencias": 2},
    ])
    assert hierarquia_headings(_item(None, ["address"]), pacote).total_afetadas == 1


def test_hierarquia_headings_sem_coluna():
    pacote = _pacote(h1=[{"address": "https://a/", "h1": "", "ocorrencias": 0}])
    assert hierarquia_headings(_item(None), pacote).status == "sem_dados"


def test_avaliar_pacote_com_checklist_real():
    recarregar_checklist()
    ck = carregar_checklist()
    pacote = _pacote(
        page_titles=[{"address": "https://a/", "title": "", "title_length": 0, "ocorrencias": 1}],
    )
    resultados = avaliar_pacote(ck, pacote, faltantes=["h1"])
    assert resultados["title-tag-ausente-ou-vazia"].status == "reprovado"
    # export declarado como faltante -> sem_dados mesmo sem regra rodar
    assert resultados["tag-h1-ausente-ou-vazia"].status == "sem_dados"
    # item sf sem regra (fora da fatia) -> sem_dados
    assert resultados["conteudo-duplicado"].status == "sem_dados"
    # itens manuais/gsc/cwv-link não aparecem
    assert "analise-de-logfile" not in resultados
    assert all(s in {"aprovado", "atencao", "reprovado", "na", "sem_dados"}
               for s in (r.status for r in resultados.values()))


def test_uso_tipo_schema_presente_e_ausente():
    from app.services.seotec_checklist import RegraItem

    pacote = _pacote(structured_data=[
        {"address": "https://a/", "tipos": ["Article", "WebSite"], "erros": 0, "avisos": 0},
    ])
    item = _item(RegraItem(export="structured_data", tipo="custom", funcao="uso_tipo_schema",
                           parametros={"tipo": "Article"}))
    assert uso_tipo_schema(item, pacote).status == "aprovado"
    item2 = _item(RegraItem(export="structured_data", tipo="custom", funcao="uso_tipo_schema",
                            parametros={"tipo": "Product"}))
    assert uso_tipo_schema(item2, pacote).status == "atencao"


def test_www_vs_non_www():
    misto = _pacote(internal=[
        {"address": "https://www.ex.com/a"}, {"address": "https://ex.com/b"},
    ])
    ok = _pacote(internal=[{"address": "https://www.ex.com/a"}, {"address": "https://www.ex.com/b"}])
    assert www_vs_non_www(_item(None, ["address"]), misto).status == "reprovado"
    assert www_vs_non_www(_item(None), ok).status == "aprovado"


def test_trailing_slash_misto():
    misto = _pacote(internal=[{"address": "https://ex.com/a"}, {"address": "https://ex.com/a/"}])
    ok = _pacote(internal=[{"address": "https://ex.com/a/"}, {"address": "https://ex.com/b/"}])
    assert trailing_slash_misto(_item(None, ["address"]), misto).status == "reprovado"
    assert trailing_slash_misto(_item(None), ok).status == "aprovado"


def test_case_sensitive_urls():
    misto = _pacote(internal=[{"address": "https://ex.com/Pagina"}, {"address": "https://ex.com/pagina"}])
    assert case_sensitive_urls(_item(None, ["address"]), misto).status == "reprovado"


def test_imagens_nome_generico():
    pacote = _pacote(images=[
        {"address": "https://ex.com/img/IMG_1234.jpg", "size_bytes": 1000, "alt_text": "x"},
        {"address": "https://ex.com/img/produto-azul.jpg", "size_bytes": 1000, "alt_text": "x"},
    ])
    r = imagens_nome_generico(_item(None, ["address"]), pacote)
    assert (r.status, r.total_afetadas) == ("atencao", 1)


def test_avaliar_pacote_dados_estruturados():
    recarregar_checklist()
    ck = carregar_checklist()
    pacote = _pacote(structured_data=[
        {"address": "https://a/", "tipos": ["Article", "WebSite"], "erros": 2, "avisos": 1},
    ])
    r = avaliar_pacote(ck, pacote, faltantes=[])
    assert r["uso-de-markup-de-dados-estruturados"].status == "aprovado"
    assert r["uso-do-tipo-de-esquema-article"].status == "aprovado"
    assert r["uso-do-tipo-de-esquema-product"].status == "atencao"
    assert r["nao-ha-erros-no-esquema-de-marcacao"].status == "reprovado"
    assert r["nao-ha-avisos-no-esquema-de-marcacao"].status == "atencao"


def test_avaliar_pacote_hreflang_e_amp():
    recarregar_checklist()
    ck = carregar_checklist()
    # site SEM hreflang/AMP: exports presentes e vazios -> na
    vazio = _pacote(hreflang=[], amp=[])
    r = avaliar_pacote(ck, vazio, faltantes=[])
    assert r["links-de-retorno-ausentes"].status == "na"
    assert r["amp-nao-indexavel"].status == "na"
    # site COM problemas
    cheio = _pacote(
        hreflang=[{"address": "https://a/", "problema": "retorno_ausente"},
                  {"address": "https://b/", "problema": None}],
        amp=[{"address": "https://a/", "amp_url": "https://a/amp/", "problema": "html_nao_amp"}],
    )
    r2 = avaliar_pacote(ck, cheio, faltantes=[])
    assert r2["links-de-retorno-ausentes"].status == "reprovado"
    assert r2["diretiva-de-idioma-alternativo-hreflang-no-cabecalho-do-codigo-fonte"].status == "aprovado"
    assert r2["html-declarada-como-amp-html"].status == "reprovado"
    assert r2["uso-de-urls-hreflang-com-codigo-de-status-200"].status == "aprovado"
