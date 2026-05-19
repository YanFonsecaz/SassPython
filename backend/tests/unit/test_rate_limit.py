import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.rate_limit import SLIDING_WINDOW_SCRIPT, check_rate_limit_redis


@pytest.mark.asyncio
async def test_rate_limit_passes_under_limit(mock_redis):
    with patch("app.core.rate_limit.get_redis_commands", return_value=mock_redis):
        result = await check_rate_limit_redis("rl:test:user1", max_requests=5, window_seconds=60)
    assert result is True
    mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limit_blocks_at_limit(mock_redis):
    mock_redis.eval = AsyncMock(return_value=0)
    with patch("app.core.rate_limit.get_redis_commands", return_value=mock_redis):
        result = await check_rate_limit_redis("rl:test:user1", max_requests=1, window_seconds=60)
    assert result is False


@pytest.mark.asyncio
async def test_rate_limit_fail_open_on_redis_error(mock_redis):
    mock_redis.eval = AsyncMock(side_effect=ConnectionError("Redis down"))
    with patch("app.core.rate_limit.get_redis_commands", return_value=mock_redis):
        result = await check_rate_limit_redis("rl:test:user1", max_requests=1, window_seconds=60)
    assert result is True


def test_lua_script_structure():
    assert "ZREMRANGEBYSCORE" in SLIDING_WINDOW_SCRIPT
    assert "ZCARD" in SLIDING_WINDOW_SCRIPT
    assert "ZADD" in SLIDING_WINDOW_SCRIPT
    assert "EXPIRE" in SLIDING_WINDOW_SCRIPT
