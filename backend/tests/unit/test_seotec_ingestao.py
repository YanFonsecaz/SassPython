import json

import app.services.seotec_ingestao as ingestao_mod
from app.services.seotec_ingestao import EXPORTS_CONHECIDOS, MAX_LINHAS_POR_EXPORT, validar_pacote
from tests.unit.helpers_seotec import montar_pacote_zip

TITLES = [{"address": "https://exemplo.com.br/", "title": "Home", "title_length": 4, "ocorrencias": 1}]


def test_pacote_valido_completo():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "h1": []})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1"})
    assert r.erros == []
    assert r.faltantes == []
    assert not r.parcial
    assert r.pacote.schema_version == 1
    assert r.pacote.dominio == "https://exemplo.com.br"
    assert r.pacote.exports["page_titles"].linhas == TITLES


def test_pacote_incompleto_vira_parcial():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1", "redirects"})
    assert r.erros == []
    assert sorted(r.faltantes) == ["h1", "redirects"]
    assert r.parcial


def test_schema_version_desconhecida_rejeita():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES}, schema_version=99)
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.pacote is None
    assert any("schema_version" in e for e in r.erros)


def test_hash_corrompido_rejeita_export():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "h1": []}, corromper_hash="page_titles")
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1"})
    assert "page_titles" in r.faltantes
    assert any("hash" in e for e in r.erros)


def test_sem_manifest_rejeita():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES}, sem_manifest=True)
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.pacote is None


def test_zip_invalido_rejeita():
    r = validar_pacote(b"nao sou zip", exports_requeridos={"page_titles"})
    assert r.pacote is None


def test_export_desconhecido_ignorado():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "inventado": []})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.erros == []
    assert "inventado" not in r.pacote.exports
    assert EXPORTS_CONHECIDOS == {
        "robots", "sitemaps", "response_codes", "internal", "page_titles",
        "meta_description", "h1", "images", "redirects",
        "directives", "pagina_404", "orfas", "sitemap_response_codes",
        "extracoes", "structured_data", "hreflang", "amp",
        "canonicals", "content", "security", "seguranca_site",
    }


def test_export_json_nao_objeto_vira_faltante():
    # JSON válido mas não é um objeto: string, lista, número, null.
    for corpo_valor in ["apenas uma string", [], 42, None]:
        corpo = json.dumps(corpo_valor).encode("utf-8")
        zip_bytes = montar_pacote_zip(
            {"page_titles": TITLES, "h1": []}, corpo_bruto={"h1": corpo}
        )
        r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1"})
        assert r.pacote is not None
        assert "h1" in r.faltantes
        assert any("h1" in e and "JSON inválido" in e for e in r.erros), r.erros
        assert "h1" not in r.pacote.exports
        # o export bem-formado continua íntegro
        assert r.pacote.exports["page_titles"].linhas == TITLES


def test_manifest_exports_nao_dict_e_fatal():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES}, manifest_exports_override=["page_titles"])
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.pacote is None
    assert any("manifest.json inválido" in e for e in r.erros)


def test_manifest_meta_nao_dict_vira_faltante():
    zip_bytes = montar_pacote_zip(
        {"page_titles": TITLES, "h1": []}, meta_override={"h1": "nao-e-um-dict"}
    )
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1"})
    assert r.pacote is not None
    assert "h1" in r.faltantes
    assert any("h1" in e and "entrada do manifest inválida" in e for e in r.erros), r.erros
    assert "h1" not in r.pacote.exports
    assert r.pacote.exports["page_titles"].linhas == TITLES


def test_export_corrompido_fora_dos_requeridos_nao_conta_parcial():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "h1": []}, corromper_hash="h1")
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.pacote is not None
    assert r.faltantes == []
    assert not r.parcial
    assert any("h1" in e and "hash" in e for e in r.erros)
    assert "h1" not in r.pacote.exports


def test_truncamento_maximo_linhas():
    linhas = [{"i": i} for i in range(600)]
    zip_bytes = montar_pacote_zip({"h1": linhas})
    r = validar_pacote(zip_bytes, exports_requeridos={"h1"})
    assert len(r.pacote.exports["h1"].linhas) == MAX_LINHAS_POR_EXPORT
    assert r.pacote.exports["h1"].total_antes_corte == 600


# --- Hardening contra zip bomb (SPEC final-review) ---

def test_export_acima_do_limite_por_entrada_vira_faltante(monkeypatch):
    # Baixa o teto por entrada: o manifest.json (só metadados) fica abaixo,
    # mas o corpo do export "page_titles" (linhas repetidas) passa disso —
    # deve virar faltante sem crash, e "h1" (pequeno) continua íntegro.
    monkeypatch.setattr(ingestao_mod, "MAX_BYTES_POR_ENTRADA", 1000)
    linhas_grandes = TITLES * 50
    zip_bytes = montar_pacote_zip({"page_titles": linhas_grandes, "h1": []})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1"})
    assert r.pacote is not None
    assert "page_titles" in r.faltantes
    assert "h1" not in r.faltantes
    assert any("page_titles" in e and "excede limite de tamanho" in e for e in r.erros), r.erros
    assert "page_titles" not in r.pacote.exports
    assert r.pacote.exports["h1"].linhas == []


def test_manifest_acima_do_limite_e_fatal(monkeypatch):
    monkeypatch.setattr(ingestao_mod, "MAX_BYTES_POR_ENTRADA", 10)
    zip_bytes = montar_pacote_zip({"page_titles": TITLES})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles"})
    assert r.pacote is None
    assert any("manifest.json inválido" in e for e in r.erros)


def test_orcamento_total_excedido_marca_restantes_faltantes(monkeypatch):
    # Cada export real cabe no teto por entrada, mas o orçamento total é
    # estourado já no primeiro: os seguintes viram faltantes sem serem lidos.
    monkeypatch.setattr(ingestao_mod, "MAX_BYTES_DESCOMPRIMIDO_TOTAL", 1)
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "h1": [], "images": []})
    r = validar_pacote(zip_bytes, exports_requeridos={"page_titles", "h1", "images"})
    assert r.pacote is not None
    assert set(r.faltantes) == {"page_titles", "h1", "images"}
    assert any("orçamento" in e for e in r.erros)


def test_exports_novos_aceitos():
    zip_bytes = montar_pacote_zip({
        "hreflang": [{"address": "https://a/", "problema": "retorno_ausente"}],
        "seguranca_site": [{"ssl_valido": True, "hsts": False}],
    })
    r = validar_pacote(zip_bytes, exports_requeridos={"hreflang"})
    assert r.erros == [] and "hreflang" in r.pacote.exports and "seguranca_site" in r.pacote.exports
