import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.parecer import (
    AchadoImagem,
    ParecerEstruturado,
)

MOCK_EXEC_ID = str(uuid.uuid4())
MOCK_USER_ID = str(uuid.uuid4())
MOCK_CLIENT_ID = str(uuid.uuid4())
MOCK_PARECER_ID = str(uuid.uuid4())

FIXED_ACHADO = AchadoImagem(
    indice_global=0,
    o_que_mostra="Print do LCP",
    problema="LCP alto",
    impacto=["LCP"],
    onde_ocorre="Home",
    confianca=0.9,
)

FIXED_ESTRUTURA = ParecerEstruturado(
    titulo="PARECER TÉCNICO — SEO / PERFORMANCE",
    subtitulo="Otimização de Core Web Vitals",
    escopo_linha="LCP e CLS — test.com (Cliente Teste)",
    secoes=[],
    recomendacoes_globais=[],
)


class TestWorkflowCompleto:
    @pytest.mark.asyncio
    async def test_workflow_concluido_com_2_blocos(self):
        from app.agents.parecer.workflow import executar_workflow_parecer

        mock_parecer = MagicMock()
        mock_parecer.id = uuid.UUID(MOCK_PARECER_ID)

        mock_ex = MagicMock()
        mock_ex.entrada_json = {
            "cliente_nome": "Cliente Teste",
            "blocos": [
                {"texto": "Problema na home", "imagens": []},
                {"texto": "LCP alto", "imagens": []},
            ],
        }
        mock_ex.usuario_id = uuid.UUID(MOCK_USER_ID)
        mock_ex.cliente_id = uuid.UUID(MOCK_CLIENT_ID)
        mock_ex.creditos_cobrados = 10

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        async def _criar_parecer(s, **kw):
            return mock_parecer

        mock_confirmar_debito = AsyncMock()

        with patch("app.agents.parecer.workflow.async_session_factory", return_value=mock_session), \
             patch("app.services.ferramenta_service.buscar_execucao", new_callable=AsyncMock, return_value=mock_ex), \
             patch("app.services.ferramenta_service.atualizar_execucao", new_callable=AsyncMock), \
             patch("app.services.ferramenta_service.finalizar_falha", new_callable=AsyncMock), \
             patch("app.config.settings") as mock_settings, \
             patch("app.services.credito_service.confirmar_debito", mock_confirmar_debito), \
             patch("app.agents.parecer.analisador.analisar_imagem", new_callable=AsyncMock, return_value=FIXED_ACHADO), \
             patch("app.agents.parecer.documentador.gerar_parecer_estruturado", new_callable=AsyncMock, return_value=FIXED_ESTRUTURA) as mock_doc, \
             patch("app.services.parecer_service.estrutura_para_html", return_value="<h1>Parecer</h1>"), \
             patch("app.services.parecer_persistencia.criar_parecer", _criar_parecer):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.parecer_analisador_model = "gpt-4o"
            mock_settings.parecer_documentador_model = "gpt-4.1"

            await executar_workflow_parecer(MOCK_EXEC_ID)

        mock_confirmar_debito.assert_called_once()
        call_args = mock_confirmar_debito.call_args[0]
        call_kwargs = mock_confirmar_debito.call_args[1]
        assert call_args[2] == 10
        assert call_kwargs["ferramenta"] == "parecer_tecnico"
        assert call_kwargs["execucao_id"] == MOCK_EXEC_ID
        mock_doc.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_execucao_inexistente(self):
        from app.agents.parecer.workflow import executar_workflow_parecer

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.agents.parecer.workflow.async_session_factory", return_value=mock_session), \
             patch("app.services.ferramenta_service.buscar_execucao", new_callable=AsyncMock, return_value=None):
            result = await executar_workflow_parecer("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_workflow_falha_libera_reserva(self):
        from app.agents.parecer.workflow import executar_workflow_parecer

        mock_ex = MagicMock()
        mock_ex.entrada_json = {
            "cliente_nome": "C",
            "blocos": [{"texto": "t", "imagens": []}],
        }
        mock_ex.usuario_id = uuid.UUID(MOCK_USER_ID)
        mock_ex.cliente_id = uuid.UUID(MOCK_CLIENT_ID)
        mock_ex.creditos_cobrados = 10

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()

        mock_finalizar_falha = AsyncMock()
        mock_liberar_reserva = AsyncMock()

        with patch("app.agents.parecer.workflow.async_session_factory", return_value=mock_session), \
             patch("app.services.ferramenta_service.buscar_execucao", new_callable=AsyncMock, return_value=mock_ex), \
             patch("app.services.ferramenta_service.atualizar_execucao", new_callable=AsyncMock), \
             patch("app.services.ferramenta_service.finalizar_falha", mock_finalizar_falha), \
             patch("app.config.settings") as mock_settings, \
             patch("app.services.credito_service.liberar_reserva", mock_liberar_reserva), \
             patch("app.agents.parecer.documentador.gerar_parecer_estruturado", new_callable=AsyncMock, side_effect=Exception("LLM error")):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.parecer_analisador_model = "gpt-4o"
            mock_settings.parecer_documentador_model = "gpt-4.1"

            with pytest.raises(Exception):
                await executar_workflow_parecer(MOCK_EXEC_ID)

            # _falhar delega a liberacao ao finalizar_falha (com a ferramenta),
            # que libera o reservado real; NAO ha mais liberar_reserva direto (sem dupla liberacao).
            mock_finalizar_falha.assert_called_once()
            assert mock_finalizar_falha.call_args.kwargs.get("ferramenta") == "parecer_tecnico"
            mock_liberar_reserva.assert_not_called()

    def test_construir_nota_map(self):
        from app.agents.parecer.workflow import _construir_nota_map

        entrada = {
            "blocos": [
                {"texto": "Nota A", "imagens": ["img1", "img2"]},
                {"texto": "Nota B", "imagens": ["img3"]},
            ],
        }
        result = _construir_nota_map(entrada)
        assert result == {0: "Nota A", 1: "Nota A", 2: "Nota B"}

    def test_data_ptbr_format(self):
        from app.agents.parecer.workflow import _data_ptbr

        result = _data_ptbr()
        assert "/" in result
        parts = result.split("/")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()
