import pytest

from app.services.seotec_checklist import (
    ChecklistSeotec,
    RegraFiltro,
    RegraItem,
    carregar_checklist,
    recarregar_checklist,
)


@pytest.fixture(autouse=True)
def _limpar_cache():
    recarregar_checklist()
    yield
    recarregar_checklist()


def test_carrega_seed_real():
    ck = carregar_checklist()
    assert isinstance(ck, ChecklistSeotec)
    assert len(ck.itens()) == 124
    assert sum(i.peso for i in ck.itens()) == 940


def test_item_por_slug_com_regra():
    ck = carregar_checklist()
    item = ck.itens_por_slug()["title-tag-ausente-ou-vazia"]
    assert item.fonte == "sf"
    assert item.categoria == "Tag <title>"
    assert item.regra.export == "page_titles"
    assert item.regra.tipo == "contagem"
    assert item.regra.filtro.op == "vazio"


def test_item_sf_sem_regra_permitido():
    ck = carregar_checklist()
    item = ck.itens_por_slug()["conteudo-duplicado"]
    assert item.fonte == "sf"
    assert item.regra is None


def test_regra_filtro_entre_exige_lista_de_dois_numeros():
    with pytest.raises(Exception):
        RegraFiltro(campo="status_code", op="entre", valor=[1])


def test_regra_item_extra_forbid_rejeita_chave_desconhecida():
    with pytest.raises(Exception):
        RegraItem(
            export="x",
            tipo="contagem",
            filtro=RegraFiltro(campo="c", op="vazio"),
            chave_errada=1,
        )


def test_regra_filtro_extra_forbid_rejeita_chave_desconhecida():
    with pytest.raises(Exception):
        RegraFiltro(campo="c", op="vazio", chave_errada=1)


def test_yaml_invalido_falha(tmp_path, monkeypatch):
    (tmp_path / "quebrado.yaml").write_text(
        "categoria: X\nitens:\n  - slug: a\n    nome: A\n    peso: 99\n", encoding="utf-8"
    )
    import app.services.seotec_checklist as mod

    monkeypatch.setattr(mod, "CHECKLIST_DIR", tmp_path)
    recarregar_checklist()
    with pytest.raises(Exception):
        carregar_checklist()
