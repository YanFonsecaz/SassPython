"""Fixtures dos testes unit.

``client``: harness de integração leve usado por ``test_auth.py`` — sobe o app
FastAPI real contra o Postgres de teste (serviço ``postgres_test`` do
docker-compose, porta 5433, o mesmo de ``tests/cwv``) com o rate limit
neutralizado (os endpoints de auth usam ``fail_mode="closed"``, que exigiria
Redis real). Sem o banco disponível, os testes que dependem dele são pulados
com instrução de como subir — nunca erram por fixture ausente.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/seo_saas_test"


@pytest_asyncio.fixture
async def client(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.base import Base

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            # O postgres_test usa tmpfs — a extensão some a cada restart do container.
            from sqlalchemy import text

            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        await engine.dispose()
        pytest.skip(
            "Postgres de teste (localhost:5433) indisponível — "
            "suba com 'docker compose up -d postgres_test'"
        )

    # Rate limit sempre permite (fail_mode=closed rejeitaria sem Redis).
    async def _sempre_ok(*args, **kwargs):
        return True

    import app.core.rate_limit as rate_limit_mod

    monkeypatch.setattr(rate_limit_mod, "check_rate_limit_redis", _sempre_ok)

    from app.dependencies import get_db
    from app.main import app as asgi_app  # app real, com middlewares (security headers/CSRF)
    from app.main import application

    async def override_get_db():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            # Espelha app.dependencies.get_db: commit no sucesso, rollback no erro.
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=asgi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        application.dependency_overrides.pop(get_db, None)
        # Isolamento entre testes: recria o schema do zero (padrão de tests/cwv).
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def usuario_teste(client: AsyncClient) -> dict:
    """Usuário cadastrado via API real, com headers autenticados e refresh token."""
    import uuid

    email = f"usuario-{uuid.uuid4().hex[:8]}@example.com"
    senha = "SenhaForte123!@#"
    resp = await client.post(
        "/api/auth/cadastro",
        json={"nome": "Usuario Teste", "email": email, "senha": senha, "senha_confirmacao": senha},
    )
    assert resp.status_code == 201, f"cadastro do fixture falhou: {resp.status_code} {resp.text[:200]}"
    data = resp.json()
    return {
        "email": email,
        "senha": senha,
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "refresh_token": data.get("refresh_token"),
    }
