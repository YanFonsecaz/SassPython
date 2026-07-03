"""Funil transparente: contadores mesclados no estado e decisões do juiz contadas."""
import app.agents.workflow_inlinks as wf


async def test_node_inserir_conta_decisoes_no_funil(monkeypatch):
    from app.agents.inlinks.inseridor import InlinkInserido

    async def fake_inserir(pilar_md, candidatos, usuario_id, **kwargs):
        return pilar_md, [
            InlinkInserido(url_destino="https://ex.com/a", anchor_text="a", paragrafo_idx=0,
                           offset_chars=0, score_total=0.9, score_semantico=0.9, score_contexto=0.9,
                           status="aplicado"),
            InlinkInserido(url_destino="https://ex.com/b", anchor_text="", paragrafo_idx=0,
                           offset_chars=0, score_total=0.5, score_semantico=0.5, score_contexto=0.5,
                           status="sugestao_manual", motivo_sugestao="sem âncora natural"),
            InlinkInserido(url_destino="https://ex.com/c", anchor_text="", paragrafo_idx=-1,
                           offset_chars=0, score_total=0.4, score_semantico=0.4, score_contexto=0.4,
                           status="rejeitado", motivo_rejeicao="tema desconectado"),
        ]

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
        "pilar_resultado": {"conteudo_md": "um texto qualquer com palavras suficientes para contar"},
        "candidatos_reranked": [{"url": u, "score_total": 0.9} for u in ("a", "b", "c")],
        "max_inlinks": 8,
        "funil": {"n_scrape_ok": 3},
    }
    saida = await wf.node_inserir(estado)

    funil = saida["funil"]
    assert funil["n_scrape_ok"] == 3  # mescla preserva contadores anteriores
    assert funil["n_decisao_aplicar"] == 1
    assert funil["n_decisao_sugerir"] == 1
    assert funil["n_decisao_descartar"] == 1
    # pilar curto → max_inlinks dinâmico = 2; n_enviadas_juiz = min(3 candidatos, 2)
    assert funil["n_enviadas_juiz"] == 2

    # sinais/confianca fluem para os dicts do resultado
    assert all("confianca" in d and "sinal_cos_contexto" in d for d in saida["inlinks_aplicados"])


async def test_gravar_etapa_engole_erros(monkeypatch):
    """Telemetria de etapa nunca derruba o workflow."""

    class _SessaoQuebrada:
        async def __aenter__(self):
            raise RuntimeError("db fora do ar")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(wf, "async_session_factory", lambda: _SessaoQuebrada())
    await wf._gravar_etapa("e1", "inserir")  # não deve levantar
