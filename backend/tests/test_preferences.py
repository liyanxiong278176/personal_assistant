"""Tests for user preferences and simplified user system.

References:
- PERS-01: Store user preferences (budget, interests, style, travelers)
- PERS-04: Preferences persist across sessions
- D-01, D-02, D-03: Simplified user system (UUID, no password, localStorage)
"""

import pytest
from unittest.mock import AsyncMock, patch
from app.db.postgres import create_user, get_user, update_preferences, get_preferences
from app.services.preference_service import PreferenceService


class TestUserPreferences:
    """Test user preference CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_user_with_preferences(self):
        """Test creating a new user with default preferences."""
        # Act
        user_id = await create_user()

        # Assert
        assert user_id is not None
        # Verify user exists
        user = await get_user(user_id)
        assert user is not None
        assert user["id"] == user_id

        # Verify default preferences
        prefs = await get_preferences(user_id)
        assert prefs is not None
        assert prefs["interests"] == []
        assert prefs["travelers"] == 1

    @pytest.mark.asyncio
    async def test_store_preferences(self):
        """Test storing user preferences."""
        # Arrange
        user_id = await create_user()
        preferences = {
            "budget": "medium",
            "interests": ["历史", "美食", "自然"],
            "style": "放松",
            "travelers": 2
        }

        # Act
        result = await update_preferences(user_id, preferences)

        # Assert
        assert result is True

        # Verify preferences were stored
        stored = await get_preferences(user_id)
        assert stored["budget"] == "medium"
        assert "历史" in stored["interests"]
        assert stored["style"] == "放松"
        assert stored["travelers"] == 2

    @pytest.mark.asyncio
    async def test_partial_preference_update(self):
        """Test partial update of preferences (merge behavior)."""
        # Arrange
        user_id = await create_user()
        await update_preferences(user_id, {
            "budget": "low",
            "interests": ["博物馆"],
            "style": "紧凑",
            "travelers": 1
        })

        # Act - Update only budget
        await update_preferences(user_id, {"budget": "high"})

        # Assert - Other preferences should remain
        stored = await get_preferences(user_id)
        assert stored["budget"] == "high"
        assert stored["interests"] == ["博物馆"]  # Unchanged
        assert stored["style"] == "紧凑"  # Unchanged
        assert stored["travelers"] == 1  # Unchanged

    @pytest.mark.asyncio
    async def test_cross_session_persistence(self):
        """Test that preferences persist across different sessions."""
        # Arrange - Simulate session 1
        user_id = await create_user()
        await update_preferences(user_id, {
            "budget": "high",
            "interests": ["豪华"],
            "style": "冒险",
            "travelers": 4
        })

        # Act - Simulate session 2 (new database connection)
        # In real scenario, user_id comes from localStorage
        retrieved_prefs = await get_preferences(user_id)

        # Assert - Preferences should be available
        assert retrieved_prefs is not None
        assert retrieved_prefs["budget"] == "high"
        assert retrieved_prefs["interests"] == ["豪华"]
        assert retrieved_prefs["travelers"] == 4


class TestPreferenceService:
    """Test preference extraction and sync service."""

    @pytest.mark.asyncio
    async def test_extract_preferences_from_conversation(self):
        """Test extracting preferences from conversation text."""
        # Arrange
        service = PreferenceService()
        conversation = "我计划去北京旅行，喜欢历史古迹，预算中等，两个人出行"

        # Act
        extracted = await service.extract_preferences(conversation)

        # Assert
        assert extracted is not None
        # Should contain related preferences
        assert "budget" in extracted or "interests" in extracted

    @pytest.mark.asyncio
    async def test_sync_preferences_to_database(self):
        """Test syncing extracted preferences to database."""
        # Arrange
        service = PreferenceService()
        user_id = await create_user()
        extracted = {
            "budget": "low",
            "interests": ["自然"],
            "style": "放松",
            "travelers": 2
        }

        # Act
        result = await service.sync_preferences(user_id, extracted)

        # Assert
        assert result["status"] in ["updated", "needs_confirmation"]

        # Verify database was updated
        stored = await get_preferences(user_id)
        assert stored["budget"] == "low"
