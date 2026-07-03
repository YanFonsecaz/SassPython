import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/seo_saas_test"


@pytest.fixture
def psi_payload_sucesso():
    return json.loads((FIXTURES_DIR / "psi_payload_sucesso.json").read_text())


@pytest.fixture
def psi_payload_lcp_alto():
    return json.loads((FIXTURES_DIR / "psi_payload_lcp_alto.json").read_text())


@pytest.fixture
def psi_payload_wordpress():
    return json.loads((FIXTURES_DIR / "psi_payload_wordpress.json").read_text())


@pytest.fixture
def psi_payload_nextjs():
    return json.loads((FIXTURES_DIR / "psi_payload_nextjs.json").read_text())


@pytest.fixture
def psi_payload_vtex():
    return json.loads((FIXTURES_DIR / "psi_payload_vtex.json").read_text())


@pytest.fixture
def psi_payload_quota_429():
    return json.loads((FIXTURES_DIR / "psi_payload_quota_429.json").read_text())


@pytest.fixture
def mock_redis_pool():
    import uuid as _uuid

    mock_pool = AsyncMock()
    fake_job = MagicMock()
    fake_job.job_id = f"mock-job-{_uuid.uuid4()}"
    mock_pool.enqueue_job = AsyncMock(return_value=fake_job)
    mock_pool.ping = AsyncMock()
    mock_pool.close = AsyncMock()
    return mock_pool


@pytest.fixture
def mock_credito_service():
    mock = AsyncMock()
    mock.reservar_creditos = AsyncMock()
    mock.liberar_reserva = AsyncMock()
    mock.confirmar_debito = AsyncMock()
    return mock


@pytest_asyncio.fixture
async def db_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.base import Base

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def usuario_teste(db_session):
    from app.core.seguranca import hash_senha

    uid = uuid.uuid4()
    from sqlalchemy import text

    await db_session.execute(
        text("""
            INSERT INTO usuarios (id, email, nome, senha_hash, mfa_ativo, email_verificado, ativo, criado_em, atualizado_em)
            VALUES (:id, :email, :nome, :senha, false, true, true, now(), now())
        """),
        {"id": uid, "email": f"cwv-test-{uid}@test.com", "nome": "Teste CWV", "senha": hash_senha("Test123!")},
    )
    await db_session.commit()
    return uid


@pytest_asyncio.fixture
async def cliente_teste(db_session, usuario_teste):
    from sqlalchemy import text

    cid = uuid.uuid4()
    await db_session.execute(
        text("""
            INSERT INTO clientes (id, usuario_id, nome, site_url, config_json, ativo)
            VALUES (:id, :uid, :nome, NULL, '{}', true)
        """),
        {"id": cid, "uid": usuario_teste, "nome": "Cliente CWV Teste"},
    )
    await db_session.commit()
    return cid


@pytest_asyncio.fixture
async def cliente_outro_usuario(db_session):
    from sqlalchemy import text

    from app.core.seguranca import hash_senha

    uid = uuid.uuid4()
    await db_session.execute(
        text("""
            INSERT INTO usuarios (id, email, nome, senha_hash, mfa_ativo, email_verificado, ativo, criado_em, atualizado_em)
            VALUES (:id, :email, :nome, :senha, false, true, true, now(), now())
        """),
        {"id": uid, "email": f"cwv-other-{uid}@test.com", "nome": "Outro Usuario", "senha": hash_senha("Test123!")},
    )

    cid = uuid.uuid4()
    await db_session.execute(
        text("""
            INSERT INTO clientes (id, usuario_id, nome, site_url, config_json, ativo)
            VALUES (:id, :uid, :nome, NULL, '{}', true)
        """),
        {"id": cid, "uid": uid, "nome": "Cliente Outro"},
    )
    await db_session.commit()
    return cid


@pytest.fixture
def auth_token(usuario_teste):
    from app.core.seguranca import gerar_jwt_access_token
    return gerar_jwt_access_token(str(usuario_teste), "cwv-test@test.com", False)


@pytest_asyncio.fixture
async def client_autenticado(db_engine, auth_token, mock_redis_pool):

    from app.main import application

    async def override_get_db():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            yield session

    application.dependency_overrides.clear()
    application.dependency_overrides[type(application.dependency_overrides)] = {}

    from app.dependencies import get_db

    application.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {auth_token}"}) as client:
        yield client

    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def execucao_teste(db_session, usuario_teste, cliente_teste):
    from app.models.execucao_ferramenta import ExecucaoFerramenta

    eid = uuid.uuid4()
    entrada = {
        "cliente_id": str(cliente_teste),
        "urls_por_template": {"home": ["https://example.com/"]},
        "estrategia": "mobile",
    }
    execucao = ExecucaoFerramenta(
        id=eid,
        usuario_id=usuario_teste,
        cliente_id=cliente_teste,
        ferramenta="core_web_vitals",
        creditos_cobrados=0,
        status="executando",
        entrada_json=entrada,
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(execucao)
    await db_session.commit()
    await db_session.refresh(execucao)
    return execucao


@pytest_asyncio.fixture
async def analise_teste(db_session, usuario_teste, cliente_teste, execucao_teste):
    from app.models.cwv_analise import CwvAnalise

    aid = uuid.uuid4()
    analise = CwvAnalise(
        id=aid,
        execucao_id=execucao_teste.id,
        cliente_id=cliente_teste,
        usuario_id=usuario_teste,
        url="https://example.com/",
        url_canonica="https://example.com/",
        template_tipo="home",
        estrategia="mobile",
        plataforma_detectada="wordpress",
        score_performance=72,
        lcp_ms=3200.0,
        cls=0.15,
        inp_ms=200.0,
        fcp_ms=1800.0,
        ttfb_ms=300.0,
        tbt_ms=450.0,
        raw_psi_json={},
        status="sucesso",
    )
    db_session.add(analise)
    await db_session.commit()
    await db_session.refresh(analise)
    return analise
