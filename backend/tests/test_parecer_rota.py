import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.parecer import GerarParecerRequest
from app.services import ferramenta_service


def _make_data_uri(width=100, height=100) -> str:
    from PIL import Image as PILImage
    buf = io.BytesIO()
    img = PILImage.new("RGB", (width, height), color="blue")
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    return f"data:image/png;base64,{b64}"


class TestCustoParecer:
    def test_custo_base(self):
        req = GerarParecerRequest(cliente_id="00000000-0000-0000-0000-000000000001", blocos=[
            {"texto": "test", "imagens": []},
        ])
        assert ferramenta_service.calcular_custo_parecer(req.total_imagens) == ferramenta_service.CUSTO_BASE_PARECER

    def test_custo_com_imagens(self):
        uri = _make_data_uri()
        req = GerarParecerRequest(cliente_id="00000000-0000-0000-0000-000000000001", blocos=[
            {"texto": "test", "imagens": [uri]},
            {"texto": "test2", "imagens": [uri]},
        ])
        esperado = ferramenta_service.CUSTO_BASE_PARECER + 2 * ferramenta_service.CUSTO_POR_IMAGEM_PARECER
        assert ferramenta_service.calcular_custo_parecer(req.total_imagens) == esperado

    def test_custo_maximo(self):
        n = 100
        esperado = ferramenta_service.CUSTO_BASE_PARECER + n * ferramenta_service.CUSTO_POR_IMAGEM_PARECER
        assert ferramenta_service.calcular_custo_parecer(n) == ferramenta_service.CUSTO_MAX_PARECER


class TestValidacaoBlocos:
    def test_bloco_vazio_sem_texto_sem_imagem(self):
        from app.routers.ferramentas_parecer import _validar_blocos
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validar_blocos([{"texto": "   ", "imagens": []}])
        assert exc_info.value.status_code == 422

    def test_data_uri_invalida(self):
        from app.routers.ferramentas_parecer import _validar_blocos
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validar_blocos([{"texto": "t", "imagens": ["data:text/html;base64,PHNjcmlwdD4="]}])
        assert exc_info.value.status_code == 422

    def test_bloco_com_texto_ok(self):
        from app.routers.ferramentas_parecer import _validar_blocos
        n, b = _validar_blocos([{"texto": "problema na home", "imagens": []}])
        assert n == 0
        assert b > 0

    def test_bloco_com_imagem_valida(self):
        from app.routers.ferramentas_parecer import _validar_blocos
        uri = _make_data_uri()
        n, b = _validar_blocos([{"texto": "t", "imagens": [uri]}])
        assert n == 1
        assert b > 0

    def test_imagem_acima_de_4mb(self):
        from app.routers.ferramentas_parecer import _validar_blocos
        from fastapi import HTTPException

        fake_b64 = "A" * (5 * 1024 * 1024)
        with pytest.raises(HTTPException) as exc_info:
            _validar_blocos([{"texto": "t", "imagens": [f"data:image/png;base64,{fake_b64}"]}])
        assert exc_info.value.status_code == 413
