"""Invariantes do seed do checklist SEOTEC (SPEC_SEOTEC_Checklist_Motor_Regras)."""
from pathlib import Path

import yaml

SEED_DIR = Path(__file__).parents[2] / "app" / "data" / "seotec_checklist"

FONTES_VALIDAS = {"sf", "manual", "gsc", "cwv-link"}
PRIORIDADES_VALIDAS = {"low", "medium", "high", "very-high"}


def _carregar_tudo() -> list[dict]:
    arquivos = sorted(SEED_DIR.glob("*.yaml"))
    assert len(arquivos) == 22, f"esperado 22 categorias, achou {len(arquivos)}"
    return [yaml.safe_load(a.read_text(encoding="utf-8")) for a in arquivos]


def test_total_itens_e_pesos():
    cats = _carregar_tudo()
    itens = [i for c in cats for i in c["itens"]]
    assert len(itens) == 124
    assert sum(i["peso"] for i in itens) == 940


def test_slugs_unicos_e_campos_obrigatorios():
    cats = _carregar_tudo()
    slugs = []
    for c in cats:
        assert c["categoria"]
        for i in c["itens"]:
            slugs.append(i["slug"])
            assert i["fonte"] in FONTES_VALIDAS
            assert i["prioridade"] in PRIORIDADES_VALIDAS
            assert 1 <= i["peso"] <= 10
    assert len(slugs) == len(set(slugs)), "slugs duplicados"


def test_regras_da_fatia_presentes():
    cats = _carregar_tudo()
    por_slug = {i["slug"]: i for c in cats for i in c["itens"]}
    fatia = [
        "title-tag-ausente-ou-vazia", "title-duplicado",
        "tag-meta-description-ausente-ou-vazia", "tag-h1-ausente-ou-vazia",
        "erros-no-lado-do-cliente-40x", "cadeias-de-redirecionamento",
        "tamanho-do-arquivo-de-imagem-100-kb",
    ]
    for slug in fatia:
        assert por_slug[slug].get("regra"), f"{slug} sem regra"
        assert por_slug[slug]["fonte"] == "sf"


def test_itens_gsc_e_cwv_link():
    cats = _carregar_tudo()
    itens = [i for c in cats for i in c["itens"]]
    assert sum(1 for i in itens if i["fonte"] == "gsc") == 7
    assert sum(1 for i in itens if i["fonte"] == "cwv-link") == 2
