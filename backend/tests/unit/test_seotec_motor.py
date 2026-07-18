from app.services.seotec_checklist import EvidenciaDef, ImpactoItem, ItemChecklist, RegraFiltro, RegraItem
from app.services.seotec_ingestao import ExportNormalizado, PacoteIngestao
from app.services.seotec_motor import avaliar_item


def _item(regra: RegraItem | None, evidencia: list[str] | None = None, fonte: str = "sf") -> ItemChecklist:
    return ItemChecklist(
        slug="item-teste", nome="Item teste", peso=5, prioridade="medium",
        implementacao="obrigatoria", responsavel=["dev"],
        impacto=ImpactoItem(direto=True), fonte=fonte, regra=regra,
        evidencia=EvidenciaDef(colunas=evidencia or []),
    )


def _pacote(**exports: list[dict]) -> PacoteIngestao:
    return PacoteIngestao(
        schema_version=1, dominio="https://exemplo.com.br",
        exports={k: ExportNormalizado(linhas=v, total_antes_corte=len(v)) for k, v in exports.items()},
    )


def test_contagem_vazio_reprova():
    regra = RegraItem(export="page_titles", tipo="contagem",
                      filtro=RegraFiltro(campo="title", op="vazio"))
    pacote = _pacote(page_titles=[
        {"address": "https://a/", "title": ""},
        {"address": "https://b/", "title": "Ok"},
    ])
    r = avaliar_item(_item(regra, ["address", "title"]), pacote)
    assert r.status == "reprovado"
    assert r.total_avaliadas == 2
    assert r.total_afetadas == 1
    assert r.amostra == [{"address": "https://a/", "title": ""}]


def test_contagem_zero_afetadas_aprova():
    regra = RegraItem(export="page_titles", tipo="contagem",
                      filtro=RegraFiltro(campo="title", op="vazio"))
    pacote = _pacote(page_titles=[{"address": "https://a/", "title": "Ok"}])
    assert avaliar_item(_item(regra), pacote).status == "aprovado"


def test_atencao_max():
    regra = RegraItem(export="page_titles", tipo="limiar",
                      filtro=RegraFiltro(campo="title_length", op="maior", valor=63),
                      atencao_max=5)
    pacote = _pacote(page_titles=[
        {"address": "https://a/", "title_length": 90},
        {"address": "https://b/", "title_length": 40},
    ])
    assert avaliar_item(_item(regra), pacote).status == "atencao"


def test_op_entre_e_duplicado():
    regra_entre = RegraItem(export="response_codes", tipo="contagem",
                            filtro=RegraFiltro(campo="status_code", op="entre", valor=[400, 499]))
    pacote = _pacote(response_codes=[
        {"address": "https://a/", "status_code": 404},
        {"address": "https://b/", "status_code": 200},
        {"address": "https://c/", "status_code": 500},
    ])
    r = avaliar_item(_item(regra_entre), pacote)
    assert (r.status, r.total_afetadas) == ("reprovado", 1)

    regra_dup = RegraItem(export="h1", tipo="contagem",
                          filtro=RegraFiltro(campo="h1", op="duplicado"))
    pacote2 = _pacote(h1=[
        {"address": "https://a/", "h1": "Igual"},
        {"address": "https://b/", "h1": "Igual"},
        {"address": "https://c/", "h1": "Diferente"},
        {"address": "https://d/", "h1": ""},
        {"address": "https://e/", "h1": ""},
    ])
    r2 = avaliar_item(_item(regra_dup), pacote2)
    assert r2.total_afetadas == 2  # vazios não contam como duplicados


def test_op_regex_e_len_maior():
    regra_rx = RegraItem(export="internal", tipo="contagem",
                         filtro=RegraFiltro(campo="address", op="regex", valor="_|%20"))
    pacote = _pacote(internal=[
        {"address": "https://a/pagina_ruim"},
        {"address": "https://a/pagina-boa"},
    ])
    assert avaliar_item(_item(regra_rx), pacote).total_afetadas == 1

    regra_len = RegraItem(export="internal", tipo="contagem",
                          filtro=RegraFiltro(campo="address", op="len_maior", valor=20))
    assert avaliar_item(_item(regra_len), pacote).total_afetadas == 1  # só "…pagina_ruim" (21 chars)


def test_existencia():
    regra = RegraItem(export="robots", tipo="existencia", campo="existe")
    assert avaliar_item(_item(regra), _pacote(robots=[{"existe": True}])).status == "aprovado"
    assert avaliar_item(_item(regra), _pacote(robots=[{"existe": False}])).status == "reprovado"
    regra_lista = RegraItem(export="robots", tipo="existencia", campo="sitemaps_declarados")
    assert avaliar_item(_item(regra_lista), _pacote(robots=[{"sitemaps_declarados": []}])).status == "reprovado"


def test_proporcao():
    regra = RegraItem(export="internal", tipo="proporcao",
                      filtro=RegraFiltro(campo="address", op="regex", valor="/$"),
                      limite_proporcao=0.2)
    pacote = _pacote(internal=[
        {"address": "https://a/x/"},
        {"address": "https://a/y"},
        {"address": "https://a/z"},
    ])
    # 1/3 = 33% > 20% => reprovado
    assert avaliar_item(_item(regra), pacote).status == "reprovado"


def test_export_ausente_sem_dados():
    regra = RegraItem(export="page_titles", tipo="contagem",
                      filtro=RegraFiltro(campo="title", op="vazio"))
    assert avaliar_item(_item(regra), _pacote()).status == "sem_dados"


def test_item_sf_sem_regra_sem_dados():
    assert avaliar_item(_item(None), _pacote()).status == "sem_dados"


def test_na_se_export_vazio():
    regra = RegraItem(export="redirects", tipo="contagem",
                      filtro=RegraFiltro(campo="redirect_type", op="igual", valor=302),
                      na_se_export_vazio=True)
    assert avaliar_item(_item(regra), _pacote(redirects=[])).status == "na"
