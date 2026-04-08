"""Cache layer E2E tests - full workflow testing."""
import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from datetime import datetime

from app.db.message_repo import Message


@pytest.mark.asyncio
async def test_cache_manager_basic_operations():
    """Test CacheManager basic operations workflow."""
    from app.core.cache import CacheManager

    # Mock primary store
    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(return_value={"messages": [{"role": "user", "content": "test"}]})
    mock_primary.set_session = AsyncMock()
    mock_primary.delete_session = AsyncMock(return_value=True)
    mock_primary.health_check = AsyncMock(return_value=True)

    # Mock fallback store
    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(return_value=None)
    mock_fallback.set_session = AsyncMock()
    mock_fallback.delete_session = AsyncMock(return_value=False)
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    # Test read
    result = await manager.get_session("test-conv")
    assert result is not None
    assert result["messages"][0]["content"] == "test"

    # Test write
    await manager.set_session("test-conv", {"messages": []}, 3600)
    mock_primary.set_session.assert_called_once()

    # Test health check
    health = await manager.health_check()
    assert health["primary"] is True
    assert health["fallback"] is True
    assert "circuit_state" in health


@pytest.mark.asyncio
async def test_circuit_breaker_e2e():
    """Test circuit breaker full workflow."""
    from app.core.cache import CacheManager
    from app.core.cache.circuit_breaker import CircuitState

    # Mock failing primary store
    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(side_effect=Exception("Connection failed"))
    mock_primary.health_check = AsyncMock(return_value=False)

    # Mock fallback store
    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(return_value={"messages": []})
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    # Initial state should be CLOSED
    assert manager.get_circuit_state() == CircuitState.CLOSED.value

    # Trigger 5 failures (default threshold)
    for _ in range(5):
        await manager.get_session(str(uuid4()))

    # Verify circuit is OPEN
    assert manager.get_circuit_state() == CircuitState.OPEN.value

    # 6th call should use fallback directly, not try primary
    mock_primary.get_session.reset_mock()
    await manager.get_session(str(uuid4()))
    assert not mock_primary.get_session.called


@pytest.mark.asyncio
async def test_cache_fallback_on_primary_failure():
    """Test automatic fallback when primary fails."""
    from app.core.cache import CacheManager

    call_count = {"primary": 0, "fallback": 0}

    async def failing_get_session(conv_id):
        call_count["primary"] += 1
        raise Exception("Primary failed")

    async def fallback_get_session(conv_id):
        call_count["fallback"] += 1
        return {"messages": [{"role": "user", "content": "fallback data"}]}

    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(side_effect=failing_get_session)
    mock_primary.health_check = AsyncMock(return_value=False)

    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(side_effect=fallback_get_session)
    mock_fallback.set_session = AsyncMock()
    mock_fallback.delete_session = AsyncMock(return_value=False)
    mock_fallback.get_slots = AsyncMock(return_value=None)
    mock_fallback.set_slots = AsyncMock()
    mock_fallback.delete_slots = AsyncMock(return_value=False)
    mock_fallback.get_user_prefs = AsyncMock(return_value=None)
    mock_fallback.set_user_prefs = AsyncMock()
    mock_fallback.delete_user_prefs = AsyncMock(return_value=False)
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    # Call should trigger fallback
    result = await manager.get_session("test-conv")

    assert call_count["primary"] == 1
    assert call_count["fallback"] == 1
    assert result is not None
    assert result["messages"][0]["content"] == "fallback data"


@pytest.mark.asyncio
async def test_cache_miss_returns_none():
    """Test that cache miss returns None (fallback only on exceptions)."""
    from app.core.cache import CacheManager

    # Mock cache miss
    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(return_value=None)
    mock_primary.health_check = AsyncMock(return_value=True)

    # Mock fallback
    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(return_value=None)
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    # Call should return None on cache miss
    result = await manager.get_session("test-conv")

    mock_primary.get_session.assert_called_once()
    # Fallback should NOT be called on simple miss (None return)
    # Fallback is only used when primary throws exception
    assert result is None
