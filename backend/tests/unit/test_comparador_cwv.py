from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.schemas.cwv import ProblemaComparado


def _make_mock_analise(**overrides):
    defaults = {
        "id": uuid4(),
        "cliente_id": str(uuid4()),
        "usuario_id": str(uuid4()),
        "url_canonica": "https://test.com/page",
        "criado_em": datetime.now(UTC),
        "score_performance": 80,
        "lcp_ms": 2000.0,
        "cls": 0.05,
        "inp_ms": 150.0,
        "fcp_ms": 1000.0,
        "ttfb_ms": 700.0,
        "tbt_ms": 120.0,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_mock_problema(kb_codigo: str | None, titulo: str, audit_id: str | None = None):
    p = MagicMock()
    p.kb_codigo = kb_codigo
    p.titulo = titulo
    p.audit_id = audit_id
    return p


@pytest.mark.asyncio
async def test_buscar_analise_anterior_encontrada():
    from app.services.cwv_persistencia import buscar_analise_anterior

    mock_analise = _make_mock_analise(
        id=uuid4(),
        criado_em=datetime.now(UTC) - timedelta(days=7),
        score_performance=75,
        lcp_ms=2500.0,
    )

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_analise
    mock_session.execute = AsyncMock(return_value=mock_result)

    resultado = await buscar_analise_anterior(
        mock_session,
        "https://test.com/page",
        str(uuid4()),
        datetime.now(UTC),
    )

    assert resultado is mock_analise
    assert resultado.score_performance == 75
    assert resultado.lcp_ms == 2500.0
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_buscar_analise_anterior_nao_encontrada():
    from app.services.cwv_persistencia import buscar_analise_anterior

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    resultado = await buscar_analise_anterior(
        mock_session,
        "https://test.com/page",
        str(uuid4()),
        datetime.now(UTC),
    )

    assert resultado is None


@pytest.mark.asyncio
async def test_comparar_com_anterior_sucesso():
    from app.routers.ferramentas_cwv import comparar_com_anterior

    analise_atual_id = str(uuid4())
    analise_anterior_id = str(uuid4())
    user_id = uuid4()

    mock_analise_atual = _make_mock_analise(
        id=UUID(analise_atual_id),
        usuario_id=str(user_id),
        criado_em=datetime(2026, 5, 27, 12, 0, 0, tzinfo=UTC),
        score_performance=80,
        lcp_ms=2000.0,
        cls=0.05,
        inp_ms=150.0,
    )

    mock_analise_anterior = _make_mock_analise(
        id=UUID(analise_anterior_id),
        usuario_id=str(user_id),
        criado_em=datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC),
        score_performance=75,
        lcp_ms=2500.0,
        cls=0.08,
        inp_ms=200.0,
    )

    mock_problema_anterior = _make_mock_problema("img-lcp-grande", "Imagem LCP grande")
    mock_problema_atual_1 = _make_mock_problema("js-bundle-grande", "Bundle JS grande")
    mock_problema_atual_2 = _make_mock_problema("img-lcp-grande", "Imagem LCP grande")

    mock_db = MagicMock()

    with (
        patch("app.services.cwv_persistencia.buscar_problemas_analise", new_callable=AsyncMock, side_effect=[
            [mock_problema_atual_1, mock_problema_atual_2],
            [mock_problema_anterior],
        ]),
        patch("app.services.cwv_persistencia.buscar_analise_anterior", new_callable=AsyncMock, return_value=mock_analise_anterior),
    ):
        response = await comparar_com_anterior(mock_analise_atual, mock_db)

    assert response.analise_atual_id == analise_atual_id
    assert response.analise_anterior_id == analise_anterior_id
    assert response.dias_decorridos == 7

    assert "score_performance" in response.metricas
    assert "lcp_ms" in response.metricas
    assert "cls" in response.metricas
    assert "inp_ms" in response.metricas

    score_comp = response.metricas["score_performance"]
    assert score_comp.antes == 75
    assert score_comp.depois == 80
    assert score_comp.delta == 5
    assert score_comp.melhorou is True

    lcp_comp = response.metricas["lcp_ms"]
    assert lcp_comp.antes == 2500.0
    assert lcp_comp.depois == 2000.0
    assert lcp_comp.delta == -500.0
    assert lcp_comp.melhorou is True

    assert len(response.problemas_resolvidos) == 0
    assert len(response.problemas_novos) == 1
    assert response.problemas_novos[0].kb_codigo == "js-bundle-grande"
    assert len(response.problemas_persistentes) == 1
    assert response.problemas_persistentes[0].kb_codigo == "img-lcp-grande"


@pytest.mark.asyncio
async def test_comparar_com_anterior_sem_anterior():
    from app.routers.ferramentas_cwv import comparar_com_anterior

    analise_atual_id = str(uuid4())

    user_id = uuid4()
    mock_db = MagicMock()

    mock_analise_atual = _make_mock_analise(
        id=UUID(analise_atual_id),
        usuario_id=str(user_id),
        score_performance=80,
    )

    with (
        patch("app.services.cwv_persistencia.buscar_problemas_analise", new_callable=AsyncMock, return_value=[]),
        patch("app.services.cwv_persistencia.buscar_analise_anterior", new_callable=AsyncMock, return_value=None),
    ):
        response = await comparar_com_anterior(mock_analise_atual, mock_db)

    assert response.analise_atual_id == analise_atual_id
    assert response.analise_anterior_id is None
    assert response.dias_decorridos is None
    assert len(response.metricas) == 0
    assert len(response.problemas_resolvidos) == 0
    assert len(response.problemas_novos) == 0
    assert len(response.problemas_persistentes) == 0


def test_problema_comparado_aceita_kb_codigo_nulo():
    pc = ProblemaComparado(kb_codigo=None, titulo="Algum problema")
    assert pc.kb_codigo is None
    assert pc.titulo == "Algum problema"


def test_problema_comparado_com_kb_codigo_str():
    pc = ProblemaComparado(kb_codigo="img-lcp-grande", titulo="Imagem LCP")
    assert pc.kb_codigo == "img-lcp-grande"


@pytest.mark.asyncio
async def test_diff_distingue_problemas_kb_nulo_com_audit_ids_diferentes():
    from app.routers.ferramentas_cwv import comparar_com_anterior

    analise_atual_id = str(uuid4())
    analise_anterior_id = str(uuid4())
    user_id = uuid4()

    mock_analise_atual = _make_mock_analise(
        id=UUID(analise_atual_id),
        usuario_id=str(user_id),
        criado_em=datetime(2026, 5, 27, 12, 0, 0, tzinfo=UTC),
        score_performance=60,
    )
    mock_analise_anterior = _make_mock_analise(
        id=UUID(analise_anterior_id),
        usuario_id=str(user_id),
        criado_em=datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC),
        score_performance=55,
    )

    problema_a1 = _make_mock_problema(None, "Unknown Audit A", audit_id="audit-aaa")
    problema_a2 = _make_mock_problema(None, "Unknown Audit B", audit_id="audit-bbb")
    problema_p1 = _make_mock_problema(None, "Unknown Audit A", audit_id="audit-aaa")
    problema_p2 = _make_mock_problema(None, "Unknown Audit C", audit_id="audit-ccc")

    mock_db = MagicMock()

    with (
        patch("app.services.cwv_persistencia.buscar_problemas_analise", new_callable=AsyncMock, side_effect=[
            [problema_a1, problema_a2],
            [problema_p1, problema_p2],
        ]),
        patch("app.services.cwv_persistencia.buscar_analise_anterior", new_callable=AsyncMock, return_value=mock_analise_anterior),
    ):
        response = await comparar_com_anterior(mock_analise_atual, mock_db)

    assert len(response.problemas_resolvidos) == 1
    assert response.problemas_resolvidos[0].titulo == "Unknown Audit C"
    assert len(response.problemas_novos) == 1
    assert response.problemas_novos[0].titulo == "Unknown Audit B"
    assert len(response.problemas_persistentes) == 1
    assert response.problemas_persistentes[0].titulo == "Unknown Audit A"
