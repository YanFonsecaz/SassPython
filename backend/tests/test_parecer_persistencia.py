import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.parecer import Parecer
from app.services.parecer_persistencia import (
    atualizar_html,
    buscar_parecer,
    criar_parecer,
    listar_pareceres,
    parecer_resumo_dict,
    parecer_to_dict,
)

MOCK_EXEC_ID = uuid.uuid4()
MOCK_USER_ID = uuid.uuid4()
MOCK_CLIENT_ID = uuid.uuid4()
MOCK_PARECER_ID = uuid.uuid4()
NOW = datetime.now(UTC)

ESTRUTURA = {
    "titulo": "Parecer Teste",
    "subtitulo": "Otimização de Core Web Vitals",
    "escopo_linha": "LCP e CLS — test.com (CT)",
    "secoes": [],
    "recomendacoes_globais": [],
}


def _make_mock_parecer(**overrides) -> MagicMock:
    defaults = {
        "id": MOCK_PARECER_ID,
        "execucao_id": MOCK_EXEC_ID,
        "cliente_id": MOCK_CLIENT_ID,
        "usuario_id": MOCK_USER_ID,
        "titulo": "Parecer Teste",
        "subtitulo": None,
        "site": "https://test.com",
        "plataforma": "Desktop",
        "cliente_nome": "CT",
        "meta_json": {"escopo_linha": ESTRUTURA["escopo_linha"]},
        "estrutura_json": ESTRUTURA,
        "parecer_html": "<h1>Test</h1>",
        "n_imagens": 0,
        "modelo": "gpt-4.1",
        "status": "concluido",
        "criado_em": NOW,
        "atualizado_em": NOW,
    }
    defaults.update(overrides)
    p = MagicMock(spec=Parecer)
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


class TestCriarParecer:
    @pytest.mark.asyncio
    async def test_cria_com_dados_corretos(self):
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        result = await criar_parecer(
            mock_session,
            execucao_id=str(MOCK_EXEC_ID),
            cliente_id=str(MOCK_CLIENT_ID),
            usuario_id=str(MOCK_USER_ID),
            cliente_nome="CT",
            estrutura=ESTRUTURA,
            parecer_html="<h1>Parecer</h1>",
            n_imagens=2,
            modelo="gpt-4.1",
        )

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.titulo == "Parecer Teste"
        assert added.cliente_nome == "CT"
        assert added.n_imagens == 2
        assert added.modelo == "gpt-4.1"
        assert added.status == "concluido"


class TestBuscarParecer:
    @pytest.mark.asyncio
    async def test_retorna_parecer_do_usuario(self):
        mock_session = MagicMock()
        mock_parecer = _make_mock_parecer()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_parecer
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await buscar_parecer(mock_session, str(MOCK_PARECER_ID), str(MOCK_USER_ID))
        assert result is mock_parecer
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_retorna_none_para_outro_usuario(self):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await buscar_parecer(mock_session, str(MOCK_PARECER_ID), str(uuid.uuid4()))
        assert result is None


class TestAtualizarHtml:
    @pytest.mark.asyncio
    async def test_atualiza_html_existente(self):
        mock_session = MagicMock()
        mock_parecer = _make_mock_parecer()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_parecer
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await atualizar_html(mock_session, str(MOCK_PARECER_ID), str(MOCK_USER_ID), "<h1>Editado</h1>")
        assert result.parecer_html == "<h1>Editado</h1>"

    @pytest.mark.asyncio
    async def test_nao_atualiza_parecer_de_outro_usuario(self):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await atualizar_html(mock_session, str(MOCK_PARECER_ID), str(uuid.uuid4()), "<h1>Hack</h1>")
        assert result is None


class TestListarPareceres:
    @pytest.mark.asyncio
    async def test_lista_sem_filtro_cliente(self):
        mock_session = MagicMock()
        mock_parecer1 = _make_mock_parecer(id=uuid.uuid4())
        mock_parecer2 = _make_mock_parecer(id=uuid.uuid4())
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_parecer1, mock_parecer2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await listar_pareceres(mock_session, str(MOCK_USER_ID))
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_lista_com_filtro_cliente(self):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await listar_pareceres(mock_session, str(MOCK_USER_ID), cliente_id=str(MOCK_CLIENT_ID))
        assert len(result) == 0


class TestParecerToDict:
    def test_converte_campos_principais(self):
        p = _make_mock_parecer()
        d = parecer_to_dict(p)
        assert d["id"] == str(MOCK_PARECER_ID)
        assert d["titulo"] == "Parecer Teste"
        assert d["cliente_nome"] == "CT"
        assert d["n_imagens"] == 0
        assert d["status"] == "concluido"
        assert "criado_em" in d

    def test_resumo_sem_html(self):
        p = _make_mock_parecer()
        d = parecer_resumo_dict(p)
        assert "parecer_html" not in d
        assert "estrutura" not in d
        assert d["titulo"] == "Parecer Teste"
        assert d["cliente_nome"] == "CT"
