"""Tests for PostgresCacheStore."""
import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from datetime import datetime

from app.core.cache.postgres_store import PostgresCacheStore
from app.db.message_repo import Message


@pytest.fixture
def mock_message_repo():
    """Mock MessageRepository."""
    repo = Mock()
    repo.get_by_conversation = AsyncMock()
    return repo


@pytest.fixture
def sample_messages():
    """Sample messages for testing."""
    conv_id = uuid4()
    return [
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            user_id="test_user",
            role="user",
            content="我想去北京旅游",
            tokens=10,
            created_at=datetime.utcnow()
        ),
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            user_id="test_user",
            role="assistant",
            content="好的，我来帮您规划行程",
            tokens=12,
            created_at=datetime.utcnow()
        ),
    ]


@pytest.mark.asyncio
async def test_get_session_returns_messages(mock_message_repo, sample_messages):
    """Test get_session returns messages from repository."""
    mock_message_repo.get_by_conversation.return_value = sample_messages

    store = PostgresCacheStore(mock_message_repo)
    result = await store.get_session(str(sample_messages[0].conversation_id))

    assert result is not None
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][1]["role"] == "assistant"
    assert "messages" in result


@pytest.mark.asyncio
async def test_get_session_empty_conversation(mock_message_repo):
    """Test get_session returns None for empty conversation."""
    mock_message_repo.get_by_conversation.return_value = []

    store = PostgresCacheStore(mock_message_repo)
    result = await store.get_session(str(uuid4()))

    assert result is None


@pytest.mark.asyncio
async def test_get_session_handles_errors(mock_message_repo):
    """Test get_session returns None on errors."""
    mock_message_repo.get_by_conversation.side_effect = Exception("DB error")

    store = PostgresCacheStore(mock_message_repo)
    result = await store.get_session(str(uuid4()))

    assert result is None


@pytest.mark.asyncio
async def test_set_session_is_noop(mock_message_repo):
    """Test set_session is a no-op (read-only fallback)."""
    store = PostgresCacheStore(mock_message_repo)
    await store.set_session("conv_id", {"messages": []}, 3600)

    # Should not call repo's write methods
    assert not mock_message_repo.get_by_conversation.called


@pytest.mark.asyncio
async def test_health_check(mock_message_repo):
    """Test health_check returns True."""
    mock_message_repo.get_by_conversation.return_value = []

    store = PostgresCacheStore(mock_message_repo)
    assert await store.health_check() is True
