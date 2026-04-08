"""Tests for CacheManager."""
import pytest
from unittest.mock import AsyncMock, Mock

from app.core.cache.manager import CacheManager
from app.core.cache.circuit_breaker import CircuitState


@pytest.fixture
def mock_primary():
    """Mock primary store."""
    store = Mock()
    store.get_session = AsyncMock()
    store.set_session = AsyncMock()
    store.delete_session = AsyncMock()
    store.get_slots = AsyncMock()
    store.set_slots = AsyncMock()
    store.delete_slots = AsyncMock()
    store.get_user_prefs = AsyncMock()
    store.set_user_prefs = AsyncMock()
    store.delete_user_prefs = AsyncMock()
    store.health_check = AsyncMock(return_value=True)
    return store


@pytest.fixture
def mock_fallback():
    """Mock fallback store."""
    store = Mock()
    store.get_session = AsyncMock(return_value=None)
    store.set_session = AsyncMock()
    store.delete_session = AsyncMock(return_value=False)
    store.get_slots = AsyncMock(return_value=None)
    store.set_slots = AsyncMock()
    store.delete_slots = AsyncMock(return_value=False)
    store.get_user_prefs = AsyncMock(return_value=None)
    store.set_user_prefs = AsyncMock()
    store.delete_user_prefs = AsyncMock(return_value=False)
    store.health_check = AsyncMock(return_value=True)
    return store


@pytest.fixture
def manager(mock_primary, mock_fallback):
    """Create CacheManager with mocked stores."""
    return CacheManager(mock_primary, mock_fallback)


@pytest.mark.asyncio
async def test_get_session_hit_primary(manager, mock_primary):
    """Test get_session hits primary store."""
    mock_primary.get_session.return_value = {"messages": []}

    result = await manager.get_session("conv-123")

    assert result is not None
    mock_primary.get_session.assert_called_once()
    assert manager.get_circuit_state() == CircuitState.CLOSED.value


@pytest.mark.asyncio
async def test_get_session_miss_then_fallback(manager, mock_primary, mock_fallback):
    """Test get_session uses fallback on miss."""
    mock_primary.get_session.return_value = None
    mock_fallback.get_session.return_value = {"messages": []}

    result = await manager.get_session("conv-123")

    assert result is not None
    mock_primary.get_session.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_primary_failure_triggers_fallback(manager, mock_primary, mock_fallback):
    """Test get_session falls back on primary failure."""
    mock_primary.get_session.side_effect = Exception("Connection error")
    mock_fallback.get_session.return_value = {"messages": []}

    result = await manager.get_session("conv-123")

    assert result is not None
    mock_fallback.get_session.assert_called_once()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold(manager, mock_primary):
    """Test circuit breaker opens after threshold."""
    mock_primary.get_session.side_effect = Exception("Connection error")

    # Trigger 5 failures (default threshold)
    for _ in range(5):
        await manager.get_session("conv-123")

    assert manager.get_circuit_state() == CircuitState.OPEN.value

    # Next call should use fallback, not primary
    mock_primary.get_session.reset_mock()
    await manager.get_session("conv-123")
    assert not mock_primary.get_session.called


@pytest.mark.asyncio
async def test_set_session_with_ttl(manager, mock_primary):
    """Test set_session with TTL."""
    await manager.set_session("conv-123", {"messages": []}, 3600)

    mock_primary.set_session.assert_called_once()


@pytest.mark.asyncio
async def test_health_check(manager, mock_primary, mock_fallback):
    """Test health check returns both stores' health."""
    result = await manager.health_check()

    assert result["primary"] is True
    assert result["fallback"] is True
    assert "circuit_state" in result
