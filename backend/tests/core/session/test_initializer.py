"""Tests for SessionInitializer (Step 0)."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.core.session.initializer import SessionInitializer
from app.core.session.state import SessionState


@pytest.mark.asyncio
async def test_initialize_session():
    """Test basic session initialization."""
    initializer = SessionInitializer()

    conv_id = str(uuid4())
    user_id = str(uuid4())

    # Mock session_repo at the source module where it's imported
    mock_repo = AsyncMock()
    with patch("app.db.session_repo.session_repo", mock_repo), \
         patch.object(initializer._recovery, "recover_safe", new_callable=AsyncMock, return_value=None):
        state = await initializer.initialize(conv_id, user_id)

    assert isinstance(state, SessionState)
    assert str(state.user_id) == user_id
    assert str(state.conversation_id) == conv_id
    assert state.context_window_size == 128000
    assert state.soft_trim_ratio == 0.3
    assert state.hard_clear_ratio == 0.5
    assert state.max_spawn_depth == 2
    assert state.max_concurrent == 8
    assert state.max_children == 5
    # save_state should have been called
    mock_repo.save_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_state():
    """Test retrieving session state by session_id."""
    initializer = SessionInitializer()

    conv_id = str(uuid4())
    user_id = str(uuid4())

    mock_repo = AsyncMock()
    with patch("app.db.session_repo.session_repo", mock_repo), \
         patch.object(initializer._recovery, "recover_safe", new_callable=AsyncMock, return_value=None):
        state = await initializer.initialize(conv_id, user_id)

    session_id = str(state.session_id)
    retrieved = initializer.get_state(session_id)

    assert retrieved is state  # Same object from in-memory cache


@pytest.mark.asyncio
async def test_get_state_not_found():
    """Test get_state returns None for unknown session_id."""
    initializer = SessionInitializer()

    result = initializer.get_state("non-existent-session-id")

    assert result is None


@pytest.mark.asyncio
async def test_initialize_multiple_sessions():
    """Test initializing multiple sessions creates distinct states."""
    initializer = SessionInitializer()

    conv_id_1 = str(uuid4())
    user_id_1 = str(uuid4())
    conv_id_2 = str(uuid4())
    user_id_2 = str(uuid4())

    mock_repo = AsyncMock()
    with patch("app.db.session_repo.session_repo", mock_repo), \
         patch.object(initializer._recovery, "recover_safe", new_callable=AsyncMock, return_value=None):
        state1 = await initializer.initialize(conv_id_1, user_id_1)
        state2 = await initializer.initialize(conv_id_2, user_id_2)

    assert state1.session_id != state2.session_id
    assert str(state1.conversation_id) == conv_id_1
    assert str(state2.conversation_id) == conv_id_2


@pytest.mark.asyncio
async def test_initialize_with_recovery():
    """Test that recovered state is merged into session state."""
    initializer = SessionInitializer()

    conv_id = str(uuid4())
    user_id = str(uuid4())

    recovered_config = {
        "context_window_size": 64000,
        "soft_trim_ratio": 0.4,
        "hard_clear_ratio": 0.3,
        "max_spawn_depth": 1,
    }

    mock_repo = AsyncMock()
    with patch("app.db.session_repo.session_repo", mock_repo), \
         patch.object(initializer._recovery, "recover_safe", new_callable=AsyncMock, return_value=recovered_config):
        state = await initializer.initialize(conv_id, user_id)

    # Recovered config should override defaults
    assert state.context_window_size == 64000
    assert state.soft_trim_ratio == 0.4
    assert state.hard_clear_ratio == 0.3
    assert state.max_spawn_depth == 1


def test_properties():
    """Test that component properties are accessible."""
    initializer = SessionInitializer()

    assert initializer.error_classifier is not None
    assert initializer.retry_manager is not None
    assert initializer.fallback_handler is not None


def test_default_config():
    """Test default configuration values."""
    initializer = SessionInitializer()

    assert initializer._config["context_window_size"] == 128000
    assert initializer._config["soft_trim_ratio"] == 0.3
    assert initializer._config["hard_clear_ratio"] == 0.5
    assert initializer._config["max_spawn_depth"] == 2
    assert initializer._config["max_concurrent"] == 8
    assert initializer._config["max_children"] == 5
