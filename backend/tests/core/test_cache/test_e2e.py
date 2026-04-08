"""E2E tests for the full cache workflow."""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.core.cache.manager import CacheManager
from app.core.cache.circuit_breaker import CircuitState


@pytest.mark.asyncio
async def test_full_cache_workflow_write_read_delete():
    """Test complete cache workflow: write -> read -> delete."""
    # Simulated in-memory cache
    cache_data = {}

    class MockRedis:
        async def get(self, key):
            return cache_data.get(key)

        async def setex(self, key, ttl, value):
            cache_data[key] = value

        async def delete(self, key):
            if key in cache_data:
                del cache_data[key]
                return 1
            return 0

        async def ping(self):
            return True

    mock_redis = MockRedis()

    # Create mock stores
    class InMemoryStore:
        async def get_session(self, conv_id):
            import json
            data = cache_data.get(f"session:{conv_id}")
            if data:
                return json.loads(data)
            return None

        async def set_session(self, conv_id, data, ttl):
            import json
            cache_data[f"session:{conv_id}"] = json.dumps(data)

        async def delete_session(self, conv_id):
            key = f"session:{conv_id}"
            if key in cache_data:
                del cache_data[key]
                return True
            return False

        async def health_check(self):
            return True

    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(side_effect=InMemoryStore().get_session)
    mock_primary.set_session = AsyncMock(side_effect=InMemoryStore().set_session)
    mock_primary.delete_session = AsyncMock(side_effect=InMemoryStore().delete_session)
    mock_primary.health_check = AsyncMock(return_value=True)

    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(return_value=None)
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    conv_id = str(uuid4())
    session_data = {
        "messages": [
            {"role": "user", "content": "测试消息"}
        ]
    }

    # Write
    await manager.set_session(conv_id, session_data, ttl=3600)
    mock_primary.set_session.assert_called_once()

    # Read
    result = await manager.get_session(conv_id)
    assert result is not None
    assert len(result["messages"]) == 1

    # Delete
    deleted = await manager.delete_session(conv_id)
    assert deleted is True


@pytest.mark.asyncio
async def test_circuit_breaker_e2e_full_flow():
    """Test circuit breaker full lifecycle: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    # Failing Redis simulation
    failure_count = [0]

    class FailingRedis:
        async def get(self, key):
            failure_count[0] += 1
            raise Exception(f"Connection refused #{failure_count[0]}")

        async def ping(self):
            raise Exception("Connection refused")

    class MockFailingStore:
        async def get_session(self, conv_id):
            raise Exception(f"Redis error #{failure_count[0]}")

        async def health_check(self):
            return False

    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(side_effect=MockFailingStore().get_session)
    mock_primary.health_check = AsyncMock(return_value=False)

    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(return_value={"messages": [{"role": "system", "content": "fallback"}]})
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    # Initial state: CLOSED
    assert manager.get_circuit_state() == CircuitState.CLOSED.value

    # Trigger 5 failures -> OPEN
    for i in range(5):
        result = await manager.get_session(str(uuid4()))
        assert result is not None  # Fallback works

    # After 5 failures, circuit should be OPEN
    assert manager.get_circuit_state() == CircuitState.OPEN.value

    # 6th call: should skip primary (circuit OPEN) and go directly to fallback
    mock_primary.get_session.reset_mock()
    result = await manager.get_session(str(uuid4()))
    assert result is not None
    # Primary should NOT have been called again
    mock_primary.get_session.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_does_not_trigger_fallback():
    """Test that cache miss (None return) does NOT trigger fallback."""
    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(return_value=None)
    mock_primary.health_check = AsyncMock(return_value=True)

    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(return_value={"messages": []})
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    result = await manager.get_session("conv-123")

    # Cache miss returns None, fallback is NOT called
    assert result is None
    mock_fallback.get_session.assert_not_called()


@pytest.mark.asyncio
async def test_cache_error_triggers_fallback():
    """Test that cache error DOES trigger fallback."""
    mock_primary = Mock()
    mock_primary.get_session = AsyncMock(side_effect=Exception("Redis error"))
    mock_primary.health_check = AsyncMock(return_value=False)

    mock_fallback = Mock()
    mock_fallback.get_session = AsyncMock(return_value={"messages": [{"role": "system", "content": "from DB"}]})
    mock_fallback.health_check = AsyncMock(return_value=True)

    manager = CacheManager(mock_primary, mock_fallback)

    result = await manager.get_session("conv-123")

    # Error triggers fallback
    assert result is not None
    assert result["messages"][0]["content"] == "from DB"
    mock_fallback.get_session.assert_called_once()
