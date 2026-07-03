"""Testes das correções de inlinks (SPEC_Billing/Pilar/Inseridor).

Cobre os fixes de maior risco:
- reserva pelo custo real (SPEC_Billing_Inlinks)
- roteamento de pilar falho (SPEC_Pilar_Falho_Curto_Circuito)
- alinhamento de trecho_contexto/offset_chars (SPEC_Inseridor_Trecho_Contexto)
"""
from types import SimpleNamespace

from app.agents.inlinks.inseridor import _aplicar_insercoes
from app.agents.workflow_inlinks import _pilar_ok
from app.services import ferramenta_service as fs


def _exec(urls):
    return SimpleNamespace(entrada_json={"candidatas_urls": urls}, creditos_cobrados=0)


# --- SPEC_Billing_Inlinks: reserva pelo custo real ---

def test_reserva_inlinks_por_n_urls():
    assert fs._obter_reserva_estimada("inlinks_automaticos", _exec(["u"] * 10)) == fs.calcular_custo_inlinks(10)
    # acima do teto satura no maximo
    assert fs._obter_reserva_estimada("inlinks_automaticos", _exec(["u"] * 100)) == fs.CUSTO_MAX_INLINKS


def test_reserva_distribuir_por_n_urls():
    assert fs._obter_reserva_estimada("distribuir_inlinks", _exec(["u"] * 50)) == fs.calcular_custo_distribuir_inlinks(50)


def test_reserva_outras_ferramentas_inalterada():
    # CWV/parecer nao mudam de comportamento (fora de escopo da SPEC)
    assert fs._obter_reserva_estimada("core_web_vitals", _exec([])) == fs.CUSTO_BASE_CWV


def test_reserva_entrada_sem_urls_cai_na_base():
    assert fs._obter_reserva_estimada("inlinks_automaticos", SimpleNamespace(entrada_json=None, creditos_cobrados=0)) == fs.calcular_custo_inlinks(0)


# --- SPEC_Pilar_Falho_Curto_Circuito: roteamento ---

def test_pilar_falho_roteia_para_falha():
    assert _pilar_ok({"pilar_resultado": {"falhou": True}}) == "falha_pilar"
    assert _pilar_ok({"pilar_resultado": {"conteudo_md": "   "}}) == "falha_pilar"
    assert _pilar_ok({"pilar_resultado": {}}) == "falha_pilar"


def test_pilar_ok_segue_fluxo():
    assert _pilar_ok({"pilar_resultado": {"conteudo_md": "conteudo real do pilar"}}) == "extrair_candidatos"


# --- SPEC_Inseridor_Trecho_Contexto: offset final acumulado ---

def test_trecho_contexto_alinhado_com_multiplos_links():
    """Com 2+ links, o contexto de cada inlink deve conter o link real
    (antes do fix, o 2o+ usava offset original no texto modificado → desalinhado)."""
    pilar = (
        "O primeiro paragrafo fala sobre python para iniciantes no blog.\n\n"
        "O segundo paragrafo fala sobre java em projetos corporativos."
    )
    paragrafos = pilar.split("\n\n")
    candidatos = [
        {"url": "https://ex.com/python", "titulo": "Python", "score_total": 0.9, "score_semantico": 0.9, "score_contexto": 0.9},
        {"url": "https://ex.com/java", "titulo": "Java", "score_total": 0.8, "score_semantico": 0.8, "score_contexto": 0.8},
    ]
    insercoes_raw = [
        {"url_destino": "https://ex.com/python", "paragrafo_idx": 0, "trecho_original": "python", "anchor_text": "python"},
        {"url_destino": "https://ex.com/java", "paragrafo_idx": 1, "trecho_original": "java", "anchor_text": "java"},
    ]
    # min_distance_words=1 para nao rejeitar por proximidade
    texto, inseridos, _colisoes = _aplicar_insercoes(pilar, paragrafos, candidatos, insercoes_raw, min_distance_words=1)

    aplicados = [i for i in inseridos if i.status == "aplicado"]
    assert len(aplicados) == 2, [i.status for i in inseridos]

    # ambos os links existem no texto final
    assert "[python](https://ex.com/python)" in texto
    assert "[java](https://ex.com/java)" in texto

    # o trecho_contexto de CADA inlink contem o proprio link (alinhamento correto)
    for il in aplicados:
        link_md = f"[{il.anchor_text}]({il.url_destino})"
        assert link_md in (il.trecho_contexto or ""), (
            f"contexto desalinhado para {il.url_destino}: {il.trecho_contexto!r}"
        )
        # offset_chars aponta para o inicio do link no texto FINAL
        assert texto[il.offset_chars: il.offset_chars + len(link_md)] == link_md
