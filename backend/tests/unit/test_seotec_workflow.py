"""Testa o grafo SEOTEC com nós reais e persistência stubada (sem DB)."""
import uuid

import pytest

from app.agents.seotec import workflow as wf
from app.agents.seotec.workflow import construir_workflow
from app.config import settings
from app.services import credito_service
from tests.unit.helpers_seotec import montar_pacote_zip

TITLES = [{"address": "https://a/", "title": "", "title_length": 0, "ocorrencias": 1}]


@pytest.fixture(autouse=True)
def _desabilitar_ia(monkeypatch):
    """Testes do grafo rodam determinísticos por padrão (sem chamada LLM).

    O fluxo com IA habilitada é coberto em ``test_grafo_com_ia_habilitada``.
    """
    monkeypatch.setattr(settings, "seotec_ia_habilitada", False)


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
    # Kill-switch: IA desligada => mapas vazios.
    assert estado["diagnosticos"] == {}
    assert estado["recomendacoes"] == {}
    assert estado["sugestoes_ia"] == {}


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


class _FakeSessionSempreNone:
    """Sessão fake cujo get() sempre retorna None (crawl/execução inexistentes)."""

    def __init__(self):
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, model, id_):
        return None

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_executar_auditoria_tolera_crawl_e_execucao_inexistentes(monkeypatch, tmp_path):
    """Reproduz o finding: db.get() retorna None para os dois -> sem AttributeError,
    sem reembolso (não há execução para saber usuário/custo), zip é removido."""
    sessao = _FakeSessionSempreNone()
    monkeypatch.setattr("app.db.session.async_session_factory", lambda: sessao)

    chamadas_liberar = []

    async def fake_liberar_reserva(db, usuario_id, quantidade):
        chamadas_liberar.append((usuario_id, quantidade))

    monkeypatch.setattr(credito_service, "liberar_reserva", fake_liberar_reserva)

    from app.config import settings
    monkeypatch.setattr(settings, "seotec_upload_dir", str(tmp_path))

    await wf.executar_auditoria_seotec(str(uuid.uuid4()), str(uuid.uuid4()))

    assert sessao.commits == 1
    assert chamadas_liberar == []


class _FakeExecucaoOrfa:
    def __init__(self):
        self.usuario_id = uuid.uuid4()
        self.entrada_json = {"fase_destino": "after"}
        self.status = None
        self.erro_msg = None


class _FakeSessionSoExecucao:
    """Sessão fake em que só a execução existe (crawl sumiu/id inválido)."""

    def __init__(self, execucao):
        self.execucao = execucao
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, model, id_):
        from app.models.execucao_ferramenta import ExecucaoFerramenta

        if model is ExecucaoFerramenta:
            return self.execucao
        return None

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_executar_auditoria_reembolsa_quando_so_execucao_existe(monkeypatch, tmp_path):
    """Quando o crawl sumiu mas a execução existe, o fase_destino vem de
    execucao.entrada_json e a reserva é liberada antes do commit."""
    execucao = _FakeExecucaoOrfa()
    sessao = _FakeSessionSoExecucao(execucao)
    monkeypatch.setattr("app.db.session.async_session_factory", lambda: sessao)

    chamadas_liberar = []

    async def fake_liberar_reserva(db, usuario_id, quantidade):
        chamadas_liberar.append((usuario_id, quantidade))

    monkeypatch.setattr(credito_service, "liberar_reserva", fake_liberar_reserva)

    from app.config import settings
    monkeypatch.setattr(settings, "seotec_upload_dir", str(tmp_path))

    await wf.executar_auditoria_seotec(str(uuid.uuid4()), str(uuid.uuid4()))

    assert execucao.status == "falhou"
    assert execucao.erro_msg
    assert chamadas_liberar == [(str(execucao.usuario_id), 15)]  # after -> custo 15
    assert sessao.commits == 1


@pytest.mark.asyncio
async def test_grafo_com_ia_habilitada(monkeypatch):
    """IA ligada: agentes mockados populam diagnosticos/recomendacoes que fluem
    pelo estado. Sobrescreve a autouse fixture (último setattr vence)."""
    monkeypatch.setattr(settings, "seotec_ia_habilitada", True)

    diag_fixo = {"title-tag-ausente-ou-vazia": "3 de 10 páginas sem title."}
    rec_fixo = {"title-tag-ausente-ou-vazia": "Escreva titles únicos por página."}

    class FakeAnalisador:
        def __init__(self, usuario_id):
            pass

        async def diagnosticar(self, itens_ctx, site):
            return diag_fixo, []

    class FakeRecomendador:
        def __init__(self, usuario_id):
            pass

        async def recomendar(self, itens_ctx, plataforma):
            return rec_fixo, []

        async def sugerir_amostra(self, itens_ri, plataforma):
            return {}

    from app.agents.seotec import analisador, recomendador
    monkeypatch.setattr(analisador, "SeotecAnalisadorAgent", FakeAnalisador)
    monkeypatch.setattr(recomendador, "SeotecRecomendadorAgent", FakeRecomendador)

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
    assert estado["diagnosticos"] == diag_fixo
    assert estado["recomendacoes"] == rec_fixo
    assert estado["sugestoes_ia"] == {}
