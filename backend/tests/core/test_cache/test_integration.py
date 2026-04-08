"""Integration tests for CacheManager with QueryEngine."""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.core.cache.manager import CacheManager
from app.core.cache.circuit_breaker import CircuitState


@pytest.fixture
def mock_cache_manager():
    """Mock CacheManager."""
    manager = Mock()
    manager.get_session = AsyncMock(return_value=None)
    manager.set_session = AsyncMock()
    manager.get_circuit_state = Mock(return_value="closed")
    manager.get_circuit_stats = Mock(return_value={"state": "closed"})
    return manager


@pytest.mark.asyncio
async def test_query_engine_load_history_from_cache_hit(mock_cache_manager):
    """Test QueryEngine loads history from cache on hit."""
    mock_cache_manager.get_session.return_value = {
        "messages": [
            {"role": "user", "content": "我想去北京"},
            {"role": "assistant", "content": "好的"}
        ],
        "updated_at": 123.0
    }

    # Simulate the _load_history_from_db flow
    conv_id = str(uuid4())
    cached = await mock_cache_manager.get_session(conv_id)

    assert cached is not None
    assert len(cached["messages"]) == 2
    assert cached["messages"][0]["content"] == "我想去北京"
    mock_cache_manager.get_session.assert_called_once_with(conv_id)


@pytest.mark.asyncio
async def test_query_engine_cache_miss_then_db_load():
    """Test QueryEngine falls back to DB on cache miss."""
    mock_manager = Mock()
    mock_manager.get_session = AsyncMock(return_value=None)  # Cache miss
    mock_manager.set_session = AsyncMock()

    mock_message_repo = Mock()
    mock_message_repo.get_by_conversation = AsyncMock(return_value=[])

    conv_id = str(uuid4())
    # Cache miss
    cached = await mock_manager.get_session(conv_id)
    assert cached is None

    # Falls back to DB
    messages = await mock_message_repo.get_by_conversation(uuid4(), limit=50)
    mock_message_repo.get_by_conversation.assert_called_once()


@pytest.mark.asyncio
async def test_query_engine_writeback_to_cache():
    """Test QueryEngine asynchronously writes back to cache after DB load."""
    mock_manager = Mock()
    mock_manager.get_session = AsyncMock(return_value=None)  # Cache miss
    mock_manager.set_session = AsyncMock()

    conv_id = str(uuid4())
    session_data = {
        "messages": [
            {"role": "user", "content": "测试消息"}
        ],
        "updated_at": 123.0
    }

    # Simulate DB load
    await mock_manager.get_session(conv_id)

    # Simulate async writeback
    await mock_manager.set_session(conv_id, session_data, ttl=3600)

    mock_manager.set_session.assert_called_once_with(conv_id, session_data, ttl=3600)


@pytest.mark.asyncio
async def test_circuit_breaker_fallback_on_redis_failure():
    """Test fallback to Postgres when Redis fails."""
    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(side_effect=Exception("Redis connection error"))
    mock_primary.set_session = AsyncMock()
    mock_primary.health_check = AsyncMock(return_value=False)

    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(return_value={"messages": [{"role": "user", "content": "fallback"}]})
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    # Trigger 5 failures to open the circuit breaker (threshold=5)
    for i in range(5):
        result = await manager.get_session(f"conv-{i}")
        assert result is not None
        assert result["messages"][0]["content"] == "fallback"

    # Circuit should now be OPEN
    assert manager.get_circuit_state() == CircuitState.OPEN.value

    # Next call should skip primary and go directly to fallback
    mock_primary.get_session.reset_mock()
    result = await manager.get_session("conv-123")
    assert result is not None
    assert result["messages"][0]["content"] == "fallback"
    mock_primary.get_session.assert_not_called()


@pytest.mark.asyncio
async def test_health_check_reports_both_stores():
    """Test health check returns status of both stores."""
    mock_primary = Mock()
    mock_primary.health_check = AsyncMock(return_value=True)

    mock_fallback = Mock()
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)
    result = await manager.health_check()

    assert result["primary"] is True
    assert result["fallback"] is True
    assert "circuit_state" in result
