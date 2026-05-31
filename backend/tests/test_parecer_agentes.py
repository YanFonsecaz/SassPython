import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image as PILImage

from app.schemas.parecer import AchadoImagem
from app.agents.parecer.analisador import analisar_imagem, _achado_degradado


def _make_data_uri(width=100, height=100, fmt="PNG") -> str:
    buf = io.BytesIO()
    img = PILImage.new("RGB", (width, height), color="red")
    img.save(buf, format=fmt)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    mime = "image/png" if fmt == "PNG" else "image/webp"
    return f"data:{mime};base64,{b64}"


FIXED_ACHADO = AchadoImagem(
    indice_global=0,
    o_que_mostra="Chrome DevTools mostrando LCP alto",
    problema="LCP acima de 4s no hero",
    impacto=["LCP"],
    onde_ocorre="Home - hero image",
    confianca=0.9,
)


class TestAnalisarImagem:
    @pytest.mark.asyncio
    async def test_envia_mensagem_multimodal(self):
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = AsyncMock(return_value=FIXED_ACHADO)

        with patch("app.agents.parecer.analisador.get_modelo_visao", return_value=mock_model), \
             patch("app.agents.parecer.analisador.chamada_llm_mensagem_com_retry", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = FIXED_ACHADO
            result = await analisar_imagem("user-1", 0, _make_data_uri(), "Print do LCP")

        assert result.indice_global == 0
        assert result.confianca == 0.9
        mock_llm.assert_called_once()
        msgs = mock_llm.call_args[0][1]
        human_msg = msgs[1]
        assert len(human_msg.content) == 2
        assert human_msg.content[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_degrada_em_falha_parcial(self):
        with patch("app.agents.parecer.analisador.get_modelo_visao", return_value=MagicMock()), \
             patch("app.agents.parecer.analisador.chamada_llm_mensagem_com_retry", new_callable=AsyncMock, side_effect=Exception("LLM timeout")):
            result = await analisar_imagem("user-1", 5, _make_data_uri(), "")

        assert result.indice_global == 5
        assert result.confianca == 0.0
        assert result.o_que_mostra == "Evidencia nao analisada automaticamente"
        assert result.impacto == ["Outro"]

    def test_achado_degradado(self):
        d = _achado_degradado(3, "test error")
        assert d.indice_global == 3
        assert d.confianca == 0.0
        assert d.impacto == ["Outro"]
        assert d.o_que_mostra == "Evidencia nao analisada automaticamente"


class TestGerarParecerEstruturado:
    @pytest.mark.asyncio
    async def test_meta_cliente_do_argumento(self):
        from app.agents.parecer.documentador import gerar_parecer_estruturado
        from app.schemas.parecer import ParecerEstruturado

        fake = ParecerEstruturado(
            titulo="PARECER TÉCNICO — SEO / PERFORMANCE",
            subtitulo="Otimização de Core Web Vitals",
            escopo_linha="LCP e CLS — test.com (Cliente Correto)",
            secoes=[],
            recomendacoes_globais=[],
        )

        with patch("app.agents.parecer.documentador.get_modelo_redacao", return_value=MagicMock()), \
             patch("app.agents.parecer.documentador.chamada_llm_mensagem_com_retry", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = fake
            result = await gerar_parecer_estruturado(
                "user-1",
                cliente_nome="Cliente Correto",
                blocos=[{"texto": "test", "imagens": []}],
                achados=[],
            )

        # o nome do cliente vem do argumento e e injetado no contexto enviado ao LLM
        assert result.escopo_linha == "LCP e CLS — test.com (Cliente Correto)"
        msgs = mock_llm.call_args[0][1]
        context = msgs[1].content
        assert "Cliente Correto" in context


class TestSemOpenaiKey:
    @pytest.mark.asyncio
    async def test_falha_com_erro_permanente_e_libera(self):
        from app.agents.parecer.workflow import executar_workflow_parecer

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()

        mock_ex = MagicMock()
        mock_ex.entrada_json = {"blocos": [{"texto": "t", "imagens": []}], "cliente_nome": "C"}
        mock_ex.usuario_id = "u1"
        mock_ex.cliente_id = "c1"
        mock_ex.creditos_cobrados = 15

        with patch("app.agents.parecer.workflow.async_session_factory", return_value=mock_session), \
             patch("app.services.ferramenta_service.buscar_execucao", new_callable=AsyncMock, return_value=mock_ex), \
             patch("app.services.ferramenta_service.atualizar_execucao", new_callable=AsyncMock), \
             patch("app.services.ferramenta_service.finalizar_falha", new_callable=AsyncMock) as mock_ff, \
             patch("app.config.settings") as mock_settings, \
             patch("app.services.credito_service.liberar_reserva", new_callable=AsyncMock) as mock_lr:
            mock_settings.openai_api_key = None

            with pytest.raises(Exception):
                await executar_workflow_parecer("exec-1")

            mock_ff.assert_called_once()
            mock_lr.assert_called_once()
