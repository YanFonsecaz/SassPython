"""Paridade Receber ↔ Distribuir: âncoras preferidas/objetivo/CTA no Receber.

Cobre: schema InlinksRequest com os campos novos e node_inserir repassando-os
ao inseridor compartilhado (antes eram código morto no Receber).
"""
import pytest

import app.agents.workflow_inlinks as wf
from app.schemas.inlinks import InlinksRequest


def test_schema_aceita_campos_de_paridade():
    req = InlinksRequest(
        pilar_url="https://ex.com/pilar",
        candidatas_urls=["https://ex.com/a"],
        ancoras_preferidas=["  reposição de cálcio ", "reposição de cálcio", ""],
        objetivo_linkagem="  foco em conversão  ",
        permitir_cta_fallback=True,
    )
    # normaliza, deduplica e ignora vazios
    assert req.ancoras_preferidas == ["reposição de cálcio"]
    assert req.objetivo_linkagem == "foco em conversão"
    assert req.permitir_cta_fallback is True


def test_schema_defaults_preservam_comportamento_atual():
    req = InlinksRequest(pilar_url="https://ex.com/p", candidatas_urls=["https://ex.com/a"])
    assert req.ancoras_preferidas == []
    assert req.permitir_cta_fallback is False
    assert req.objetivo_linkagem is None


def test_schema_valida_tamanho_de_ancora():
    with pytest.raises(ValueError):
        InlinksRequest(
            pilar_url="https://ex.com/p",
            candidatas_urls=["https://ex.com/a"],
            ancoras_preferidas=["x"],  # < 2 chars
        )


async def test_node_inserir_repassa_parametros(monkeypatch):
    capturado: dict = {}

    async def fake_inserir(pilar_md, candidatos, usuario_id, **kwargs):
        capturado.update(kwargs)
        return pilar_md, []

    async def fake_publish(*args, **kwargs):
        return None

    async def fake_etapa(*args, **kwargs):
        return None

    import app.agents.inlinks.inseridor as ins
    import app.core.workflow_events as ev

    monkeypatch.setattr(ins, "inserir_inlinks", fake_inserir)
    monkeypatch.setattr(ev, "publish_event", fake_publish)
    monkeypatch.setattr(wf, "_gravar_etapa", fake_etapa)

    estado = {
        "execucao_id": "e1",
        "usuario_id": "u1",
        "pilar_resultado": {"conteudo_md": "conteudo do pilar com varias palavras aqui"},
        "candidatos_reranked": [{"url": "https://ex.com/a", "score_total": 0.9}],
        "max_inlinks": 8,
        "ancoras_preferidas": ["minha âncora"],
        "permitir_cta_fallback": True,
        "objetivo_linkagem": "foco em conversão",
    }
    await wf.node_inserir(estado)

    assert capturado["ancoras_preferidas"] == ["minha âncora"]
    assert capturado["permitir_cta_fallback"] is True
    assert capturado["objetivo_linkagem"] == "foco em conversão"
