import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.logging import setup_logging

setup_logging("WARNING")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def llm_mock():
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=MagicMock(content="{}"))
    mock.with_structured_output = MagicMock(return_value=AsyncMock(return_value=MagicMock()))
    return mock


@pytest.fixture
def mock_redis():
    mock = AsyncMock()
    mock.eval = AsyncMock(return_value=1)
    mock.get = AsyncMock(return_value=b"ok")
    mock.ping = AsyncMock()
    mock.zadd = AsyncMock()
    mock.expire = AsyncMock()
    mock.zremrangebyscore = AsyncMock()
    mock.zcard = AsyncMock(return_value=0)
    return mock


@pytest.fixture
def mock_settings(monkeypatch):
    from app import config

    overrides = {
        "database_url": "postgresql+asyncpg://test:test@localhost:5432/test_db",
        "secret_key": "a" * 64,
        "jwt_secret_key": "b" * 64,
        "encryption_key": "c" * 32,
        "redis_url": "redis://localhost:6379/15",
        "openai_api_key": "sk-test-key",
        "langsmith_api_key": "",
        "sentry_dsn": "",
        "ambiente": "teste",
    }
    for k, v in overrides.items():
        monkeypatch.setattr(settings, k, v) if hasattr(config, "settings") else None
    return config.settings
