from app.services.seotec_ingestao import EXPORTS_CONHECIDOS, validar_pacote
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
    assert EXPORTS_CONHECIDOS  # sanity
