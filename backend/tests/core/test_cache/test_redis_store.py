"""Tests for RedisCacheStore."""
import pytest
import json
from unittest.mock import AsyncMock, Mock, patch

from app.core.cache.redis_store import RedisCacheStore
from app.core.cache.errors import CacheConnectionError


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = Mock()
    redis.get = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def store(mock_redis):
    """Create test store with mocked Redis."""
    store = RedisCacheStore("redis://localhost:6379/0")
    store._redis = mock_redis
    return store


@pytest.mark.asyncio
async def test_get_session_hit(store, mock_redis):
    """Test cache hit returns session data."""
    conv_id = "test-conv-123"
    data = {"messages": [{"role": "user", "content": "hello"}], "updated_at": 123.0}
    mock_redis.get.return_value = json.dumps(data)

    result = await store.get_session(conv_id)

    assert result is not None
    assert result["messages"][0]["content"] == "hello"
    mock_redis.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_miss(store, mock_redis):
    """Test cache miss returns None."""
    mock_redis.get.return_value = None

    result = await store.get_session("test-conv")

    assert result is None


@pytest.mark.asyncio
async def test_set_session_with_pii_redaction(store, mock_redis):
    """Test PII redaction before storing."""
    messages = [
        {"role": "user", "content": "预约时间: 13812345678"}
    ]

    await store.set_session("conv-123", {"messages": messages}, 3600)

    # Verify PII was redacted (setex args: key, ttl, value)
    saved_data = json.loads(mock_redis.setex.call_args[0][2])
    assert "已屏蔽" in saved_data["messages"][0]["content"]


@pytest.mark.asyncio
async def test_delete_session(store, mock_redis):
    """Test delete session."""
    mock_redis.delete.return_value = 1

    result = await store.delete_session("conv-123")

    assert result is True


@pytest.mark.asyncio
async def test_health_check_success(store, mock_redis):
    """Test health check success."""
    result = await store.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_health_check_failure():
    """Test health check failure when Redis unavailable."""
    store = RedisCacheStore("redis://invalid:9999/0")

    with patch.object(store, '_ensure_connection', side_effect=Exception("Connection failed")):
        result = await store.health_check()
        assert result is False


@pytest.mark.asyncio
async def test_get_slots(store, mock_redis):
    """Test get slots."""
    mock_redis.get.return_value = json.dumps({"destination": "Beijing"})

    result = await store.get_slots("conv-123")

    assert result is not None
    assert result["destination"] == "Beijing"


@pytest.mark.asyncio
async def test_set_slots(store, mock_redis):
    """Test set slots."""
    await store.set_slots("conv-123", {"destination": "Shanghai"}, 600)

    assert mock_redis.setex.called


@pytest.mark.asyncio
async def test_get_user_prefs(store, mock_redis):
    """Test get user preferences."""
    mock_redis.get.return_value = json.dumps({"language": "zh"})

    result = await store.get_user_prefs("user-123")

    assert result is not None
    assert result["language"] == "zh"


@pytest.mark.asyncio
async def test_set_user_prefs(store, mock_redis):
    """Test set user preferences."""
    await store.set_user_prefs("user-123", {"language": "en"}, 3600)

    assert mock_redis.setex.called
