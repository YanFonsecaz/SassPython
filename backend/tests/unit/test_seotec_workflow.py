"""Testa o grafo SEOTEC com nós reais e persistência stubada (sem DB)."""
import pytest

from app.agents.seotec.workflow import construir_workflow
from tests.unit.helpers_seotec import montar_pacote_zip

TITLES = [{"address": "https://a/", "title": "", "title_length": 0, "ocorrencias": 1}]


@pytest.mark.asyncio
async def test_grafo_processa_pacote():
    zip_bytes = montar_pacote_zip({"page_titles": TITLES, "h1": [], "internal": []})
    grafo = construir_workflow()
    estado = await grafo.ainvoke({
        "zip_bytes": zip_bytes,
        "auditoria_id": "aud-1",
        "crawl_id": "crawl-1",
        "fase_destino": "before",
        "persistir": False,
    })
    assert estado["erro"] is None
    assert estado["resultados"]["title-tag-ausente-ou-vazia"].status == "reprovado"
    assert estado["score"].score < 100
    assert "response_codes" in estado["faltantes"]


@pytest.mark.asyncio
async def test_grafo_zip_invalido_seta_erro():
    grafo = construir_workflow()
    estado = await grafo.ainvoke({
        "zip_bytes": b"lixo",
        "auditoria_id": "aud-1",
        "crawl_id": "crawl-1",
        "fase_destino": "before",
        "persistir": False,
    })
    assert estado["erro"]
    assert estado.get("resultados") in (None, {})
