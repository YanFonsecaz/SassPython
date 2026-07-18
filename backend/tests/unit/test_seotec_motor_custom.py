from app.services.seotec_checklist import carregar_checklist, recarregar_checklist
from app.services.seotec_ingestao import ExportNormalizado, PacoteIngestao
from app.services.seotec_motor import avaliar_pacote
from app.services.seotec_motor_custom import (
    cadeias_redirecionamento,
    loops_redirecionamento,
    title_igual_h1,
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
