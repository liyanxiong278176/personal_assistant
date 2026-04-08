"""Tests for PostgresCacheStore."""

import pytest
from datetime import datetime
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock

from app.core.cache.postgres_store import PostgresCacheStore
from app.core.cache.base import ICacheStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_message():
    """Create a mock message object with to_dict method."""
    msg = MagicMock()
    msg.id = uuid4()
    msg.conversation_id = uuid4()
    msg.user_id = "user_123"
    msg.role = "user"
    msg.content = "Hello, I want to travel to Shanghai"
    msg.tokens = 42
    msg.created_at = datetime(2026, 4, 7, 10, 0, 0)
    msg.to_dict.return_value = {
        "id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "user_id": msg.user_id,
        "role": msg.role,
        "content": msg.content,
        "tokens": msg.tokens,
        "created_at": msg.created_at.isoformat(),
    }
    return msg


@pytest.fixture
def mock_repo(mock_message):
    """Create a mock PostgresMessageRepository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def store(mock_repo):
    """Create a PostgresCacheStore instance with a mock repository."""
    return PostgresCacheStore(message_repo=mock_repo)


# ---------------------------------------------------------------------------
# Interface compliance
# ---------------------------------------------------------------------------

def test_store_implements_icache_store(store):
    """Test that PostgresCacheStore implements ICacheStore."""
    assert isinstance(store, ICacheStore)


# ---------------------------------------------------------------------------
# get_session tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_session_returns_messages(store, mock_repo, mock_message):
    """Test that get_session returns assembled messages from repository."""
    conv_id = str(uuid4())
    mock_repo.get_by_conversation.return_value = [mock_message]

    result = await store.get_session(conv_id)

    assert result is not None
    assert "messages" in result
    assert len(result["messages"]) == 1
    assert result["messages"][0]["content"] == "Hello, I want to travel to Shanghai"
    mock_repo.get_by_conversation.assert_called_once()
    call_args = mock_repo.get_by_conversation.call_args
    # First positional arg should be the UUID
    assert call_args[0][0] == UUID(conv_id)
    # Second arg is keyword: limit=50
    assert call_args[1].get("limit") == 50


@pytest.mark.asyncio
async def test_get_session_empty_conversation(store, mock_repo):
    """Test that get_session returns None when conversation has no messages."""
    conv_id = str(uuid4())
    mock_repo.get_by_conversation.return_value = []

    result = await store.get_session(conv_id)

    assert result is None


@pytest.mark.asyncio
async def test_get_session_handles_errors(store, mock_repo):
    """Test that get_session returns None on repository errors."""
    conv_id = str(uuid4())
    mock_repo.get_by_conversation.side_effect = Exception("Database connection error")

    result = await store.get_session(conv_id)

    assert result is None


@pytest.mark.asyncio
async def test_get_session_invalid_uuid(store, mock_repo):
    """Test that get_session returns None for invalid conversation_id format."""
    result = await store.get_session("not-a-valid-uuid")

    assert result is None
    # Repository should not be called
    mock_repo.get_by_conversation.assert_not_called()


@pytest.mark.asyncio
async def test_get_session_multiple_messages(store, mock_repo):
    """Test that get_session assembles multiple messages correctly."""
    conv_id = str(uuid4())

    msg1 = MagicMock()
    msg1.to_dict.return_value = {"id": "1", "role": "user", "content": "Hello"}
    msg2 = MagicMock()
    msg2.to_dict.return_value = {"id": "2", "role": "assistant", "content": "Hi there"}
    msg3 = MagicMock()
    msg3.to_dict.return_value = {"id": "3", "role": "user", "content": "Thanks"}

    mock_repo.get_by_conversation.return_value = [msg1, msg2, msg3]

    result = await store.get_session(conv_id)

    assert result is not None
    assert len(result["messages"]) == 3
    assert result["messages"][0]["content"] == "Hello"
    assert result["messages"][1]["content"] == "Hi there"
    assert result["messages"][2]["content"] == "Thanks"


# ---------------------------------------------------------------------------
# set_session is no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_session_is_noop(store, mock_repo):
    """Test that set_session is a no-op and does not call the repository."""
    conv_id = str(uuid4())
    data = {"messages": [{"role": "user", "content": "test"}]}
    ttl = 3600

    await store.set_session(conv_id, data, ttl)

    # No exception should be raised and repo should not be called
    mock_repo.get_by_conversation.assert_not_called()


# ---------------------------------------------------------------------------
# delete_session is no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_session_returns_false(store):
    """Test that delete_session returns False (no-op)."""
    conv_id = str(uuid4())

    result = await store.delete_session(conv_id)

    assert result is False


# ---------------------------------------------------------------------------
# get_slots is no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_slots_returns_none(store):
    """Test that get_slots returns None (not supported in fallback)."""
    conv_id = str(uuid4())

    result = await store.get_slots(conv_id)

    assert result is None


# ---------------------------------------------------------------------------
# set_slots is no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_slots_is_noop(store):
    """Test that set_slots is a no-op."""
    conv_id = str(uuid4())
    slots = {"origin": "Beijing", "destination": "Shanghai"}
    ttl = 600

    await store.set_slots(conv_id, slots, ttl)

    # No exception should be raised


# ---------------------------------------------------------------------------
# delete_slots is no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_slots_returns_false(store):
    """Test that delete_slots returns False (no-op)."""
    conv_id = str(uuid4())

    result = await store.delete_slots(conv_id)

    assert result is False


# ---------------------------------------------------------------------------
# get_user_prefs is no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_user_prefs_returns_none(store):
    """Test that get_user_prefs returns None (not supported in fallback)."""
    user_id = "user_123"

    result = await store.get_user_prefs(user_id)

    assert result is None


# ---------------------------------------------------------------------------
# set_user_prefs is no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_user_prefs_is_noop(store):
    """Test that set_user_prefs is a no-op."""
    user_id = "user_123"
    prefs = {"language": "zh", "currency": "CNY"}
    ttl = 604800

    await store.set_user_prefs(user_id, prefs, ttl)

    # No exception should be raised


# ---------------------------------------------------------------------------
# delete_user_prefs is no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_user_prefs_returns_false(store):
    """Test that delete_user_prefs returns False (no-op)."""
    user_id = "user_123"

    result = await store.delete_user_prefs(user_id)

    assert result is False


# ---------------------------------------------------------------------------
# health_check tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_check_returns_true_when_healthy(store, mock_repo):
    """Test that health_check returns True when database is accessible."""
    mock_repo.get_by_conversation.return_value = []

    result = await store.health_check()

    assert result is True


@pytest.mark.asyncio
async def test_health_check_returns_false_on_error(store, mock_repo):
    """Test that health_check returns False when database is not accessible."""
    mock_repo.get_by_conversation.side_effect = Exception("Connection refused")

    result = await store.health_check()

    assert result is False
