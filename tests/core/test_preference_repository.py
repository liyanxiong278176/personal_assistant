"""Tests for PreferenceRepository (TDD approach).

Tests for ChromaDB-backed storage of user preferences with
high-confidence override strategy.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.core.preferences.patterns import MatchedPreference, PreferenceType
from app.core.preferences.repository import PreferenceRepository


class TestPreferenceRepositoryInit:
    """Tests for PreferenceRepository initialization."""

    def test_init_without_semantic_repo(self):
        """Test initialization without semantic repo (uses in-memory only)."""
        repo = PreferenceRepository()
        assert repo._semantic_repo is None
        assert repo._collection_name == "preferences"
        assert repo._embedding_client is None

    def test_init_with_semantic_repo(self):
        """Test initialization with semantic repo."""
        mock_repo = MagicMock()
        repo = PreferenceRepository(semantic_repo=mock_repo, collection_name="my_prefs")
        assert repo._semantic_repo == mock_repo
        assert repo._collection_name == "my_prefs"

    def test_init_custom_collection_name(self):
        """Test custom collection name defaults."""
        repo = PreferenceRepository(collection_name="travel_prefs")
        assert repo._collection_name == "travel_prefs"


class TestPreferenceRepositoryUpsert:
    """Tests for upsert operations."""

    @pytest.mark.asyncio
    async def test_upsert_preference(self):
        """Test basic upsert of a preference."""
        repo = PreferenceRepository()
        pref = MatchedPreference(
            key=PreferenceType.DESTINATION,
            value="北京",
            confidence=0.9
        )

        result = await repo.upsert("user1", pref)

        assert result is True
        prefs = await repo.get_user_preferences("user1")
        assert PreferenceType.DESTINATION in prefs
        assert prefs[PreferenceType.DESTINATION].value == "北京"
        assert prefs[PreferenceType.DESTINATION].confidence == 0.9

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_key(self):
        """Test upsert updates existing preference with same key."""
        repo = PreferenceRepository()
        pref1 = MatchedPreference(
            key=PreferenceType.BUDGET,
            value="3000元",
            confidence=0.8
        )
        pref2 = MatchedPreference(
            key=PreferenceType.BUDGET,
            value="5000元",
            confidence=0.8
        )

        await repo.upsert("user1", pref1)
        await repo.upsert("user1", pref2)

        prefs = await repo.get_user_preferences("user1")
        assert prefs[PreferenceType.BUDGET].value == "5000元"

    @pytest.mark.asyncio
    async def test_high_confidence_overrides_low(self):
        """Test high confidence preference overrides low confidence."""
        repo = PreferenceRepository()

        # Low confidence first
        low_pref = MatchedPreference(
            key=PreferenceType.DURATION,
            value="3天",
            confidence=0.6
        )
        # High confidence second
        high_pref = MatchedPreference(
            key=PreferenceType.DURATION,
            value="7天",
            confidence=0.95
        )

        await repo.upsert("user1", low_pref)
        await repo.upsert("user1", high_pref)

        prefs = await repo.get_user_preferences("user1")
        # High confidence should win
        assert prefs[PreferenceType.DURATION].value == "7天"
        assert prefs[PreferenceType.DURATION].confidence == 0.95

    @pytest.mark.asyncio
    async def test_low_confidence_does_not_override_high(self):
        """Test low confidence preference does NOT override high confidence."""
        repo = PreferenceRepository()

        # High confidence first
        high_pref = MatchedPreference(
            key=PreferenceType.DESTINATION,
            value="北京",
            confidence=0.95
        )
        # Low confidence second
        low_pref = MatchedPreference(
            key=PreferenceType.DESTINATION,
            value="上海",
            confidence=0.5
        )

        await repo.upsert("user1", high_pref)
        await repo.upsert("user1", low_pref)

        prefs = await repo.get_user_preferences("user1")
        # High confidence should be kept
        assert prefs[PreferenceType.DESTINATION].value == "北京"
        assert prefs[PreferenceType.DESTINATION].confidence == 0.95

    @pytest.mark.asyncio
    async def test_equal_confidence_updates_to_latest(self):
        """Test equal confidence updates to latest (newest timestamp wins)."""
        repo = PreferenceRepository()

        pref1 = MatchedPreference(
            key=PreferenceType.BUDGET,
            value="5000元",
            confidence=0.8,
            extracted_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        )
        pref2 = MatchedPreference(
            key=PreferenceType.BUDGET,
            value="8000元",
            confidence=0.8,
            extracted_at=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        )

        await repo.upsert("user1", pref1)
        await repo.upsert("user1", pref2)

        prefs = await repo.get_user_preferences("user1")
        # Latest should win
        assert prefs[PreferenceType.BUDGET].value == "8000元"

    @pytest.mark.asyncio
    async def test_upsert_multiple_users_isolated(self):
        """Test upsert isolates preferences between users."""
        repo = PreferenceRepository()
        pref1 = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.9)
        pref2 = MatchedPreference(key=PreferenceType.DESTINATION, value="上海", confidence=0.9)

        await repo.upsert("user1", pref1)
        await repo.upsert("user2", pref2)

        prefs1 = await repo.get_user_preferences("user1")
        prefs2 = await repo.get_user_preferences("user2")

        assert prefs1[PreferenceType.DESTINATION].value == "北京"
        assert prefs2[PreferenceType.DESTINATION].value == "上海"

    @pytest.mark.asyncio
    async def test_upsert_multiple_different_keys(self):
        """Test upserting multiple different preference keys."""
        repo = PreferenceRepository()
        dest = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.9)
        budget = MatchedPreference(key=PreferenceType.BUDGET, value="5000元", confidence=0.85)
        duration = MatchedPreference(key=PreferenceType.DURATION, value="5天", confidence=0.8)

        await repo.upsert("user1", dest)
        await repo.upsert("user1", budget)
        await repo.upsert("user1", duration)

        prefs = await repo.get_user_preferences("user1")
        assert len(prefs) == 3
        assert prefs[PreferenceType.DESTINATION].value == "北京"
        assert prefs[PreferenceType.BUDGET].value == "5000元"
        assert prefs[PreferenceType.DURATION].value == "5天"


class TestPreferenceRepositoryGet:
    """Tests for get operations."""

    @pytest.mark.asyncio
    async def test_get_user_preferences_empty(self):
        """Test getting preferences for user with none stored."""
        repo = PreferenceRepository()

        prefs = await repo.get_user_preferences("user_with_no_prefs")

        assert prefs == {}

    @pytest.mark.asyncio
    async def test_get_user_preferences_filter_keys(self):
        """Test filtering preferences by specific keys."""
        repo = PreferenceRepository()
        dest = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.9)
        budget = MatchedPreference(key=PreferenceType.BUDGET, value="5000元", confidence=0.85)

        await repo.upsert("user1", dest)
        await repo.upsert("user1", budget)

        # Request only destination
        prefs = await repo.get_user_preferences("user1", keys=[PreferenceType.DESTINATION])
        assert PreferenceType.DESTINATION in prefs
        assert PreferenceType.BUDGET not in prefs

    @pytest.mark.asyncio
    async def test_get_user_preferences_min_confidence(self):
        """Test filtering preferences by minimum confidence."""
        repo = PreferenceRepository()
        low = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.6)
        high = MatchedPreference(key=PreferenceType.BUDGET, value="5000元", confidence=0.9)

        await repo.upsert("user1", low)
        await repo.upsert("user1", high)

        # Request only above 0.7 confidence
        prefs = await repo.get_user_preferences("user1", min_confidence=0.7)
        assert PreferenceType.DESTINATION not in prefs
        assert PreferenceType.BUDGET in prefs

    @pytest.mark.asyncio
    async def test_get_user_preferences_combined_filters(self):
        """Test combining key and confidence filters."""
        repo = PreferenceRepository()
        low_dest = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.6)
        high_dest = MatchedPreference(key=PreferenceType.DESTINATION, value="上海", confidence=0.95)

        await repo.upsert("user1", low_dest)
        await repo.upsert("user1", high_dest)

        prefs = await repo.get_user_preferences(
            "user1",
            keys=[PreferenceType.DESTINATION],
            min_confidence=0.7
        )
        assert PreferenceType.DESTINATION in prefs
        assert prefs[PreferenceType.DESTINATION].value == "上海"


class TestPreferenceRepositoryClear:
    """Tests for clear operations."""

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing all preferences for all users."""
        repo = PreferenceRepository()
        pref1 = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.9)
        pref2 = MatchedPreference(key=PreferenceType.BUDGET, value="5000元", confidence=0.9)

        await repo.upsert("user1", pref1)
        await repo.upsert("user2", pref2)

        await repo.clear()

        assert await repo.get_user_preferences("user1") == {}
        assert await repo.get_user_preferences("user2") == {}

    @pytest.mark.asyncio
    async def test_clear_then_upsert(self):
        """Test that upsert works after clear."""
        repo = PreferenceRepository()
        pref = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.9)

        await repo.upsert("user1", pref)
        await repo.clear()
        new_pref = MatchedPreference(key=PreferenceType.DESTINATION, value="上海", confidence=0.9)
        await repo.upsert("user1", new_pref)

        prefs = await repo.get_user_preferences("user1")
        assert prefs[PreferenceType.DESTINATION].value == "上海"


class TestPreferenceRepositoryEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self):
        """Test getting preferences for non-existent user returns empty dict."""
        repo = PreferenceRepository()

        prefs = await repo.get_user_preferences("never_existed_user_12345")

        assert prefs == {}

    @pytest.mark.asyncio
    async def test_get_specific_key_nonexistent(self):
        """Test getting a specific key that doesn't exist."""
        repo = PreferenceRepository()
        pref = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.9)
        await repo.upsert("user1", pref)

        prefs = await repo.get_user_preferences(
            "user1",
            keys=[PreferenceType.BUDGET]  # Not stored
        )
        assert prefs == {}

    @pytest.mark.asyncio
    async def test_confidence_boundary_equal(self):
        """Test confidence equality boundary (exactly equal)."""
        repo = PreferenceRepository()
        pref1 = MatchedPreference(key=PreferenceType.DURATION, value="3天", confidence=0.7)
        pref2 = MatchedPreference(key=PreferenceType.DURATION, value="5天", confidence=0.7)

        await repo.upsert("user1", pref1)
        await repo.upsert("user1", pref2)

        prefs = await repo.get_user_preferences("user1")
        # Equal confidence -> latest wins
        assert prefs[PreferenceType.DURATION].value == "5天"

    @pytest.mark.asyncio
    async def test_confidence_boundary_slightly_higher(self):
        """Test confidence just slightly higher wins."""
        repo = PreferenceRepository()
        pref1 = MatchedPreference(key=PreferenceType.DURATION, value="3天", confidence=0.699)
        pref2 = MatchedPreference(key=PreferenceType.DURATION, value="5天", confidence=0.700)

        await repo.upsert("user1", pref1)
        await repo.upsert("user1", pref2)

        prefs = await repo.get_user_preferences("user1")
        assert prefs[PreferenceType.DURATION].value == "5天"

    @pytest.mark.asyncio
    async def test_very_high_confidence_wins(self):
        """Test that near-1.0 confidence always wins."""
        repo = PreferenceRepository()
        pref1 = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.99)
        pref2 = MatchedPreference(key=PreferenceType.DESTINATION, value="上海", confidence=0.5)

        await repo.upsert("user1", pref1)
        await repo.upsert("user1", pref2)

        prefs = await repo.get_user_preferences("user1")
        assert prefs[PreferenceType.DESTINATION].value == "北京"

    @pytest.mark.asyncio
    async def test_min_confidence_boundary(self):
        """Test min_confidence boundary exactly at threshold."""
        repo = PreferenceRepository()
        pref = MatchedPreference(key=PreferenceType.DESTINATION, value="北京", confidence=0.7)
        await repo.upsert("user1", pref)

        # Exactly at threshold should be included
        prefs = await repo.get_user_preferences("user1", min_confidence=0.7)
        assert PreferenceType.DESTINATION in prefs

        # Just above threshold should be excluded
        prefs = await repo.get_user_preferences("user1", min_confidence=0.71)
        assert PreferenceType.DESTINATION not in prefs


class TestPreferenceRepositoryWithMockSemantic:
    """Tests with a mock semantic repository for integration."""

    @pytest.mark.asyncio
    async def test_upsert_with_mock_semantic_repo(self):
        """Test upsert with a mock semantic repository."""
        mock_semantic = AsyncMock()
        mock_semantic.add = AsyncMock(return_value="mock_id_123")

        repo = PreferenceRepository(semantic_repo=mock_semantic)
        pref = MatchedPreference(
            key=PreferenceType.DESTINATION,
            value="北京",
            confidence=0.9
        )

        result = await repo.upsert("user1", pref)

        assert result is True
        mock_semantic.add.assert_called_once()

        # Verify the call arguments
        call_args = mock_semantic.add.call_args
        content = call_args.kwargs.get("content") or call_args[1].get("content")
        assert "北京" in content
        metadata = call_args.kwargs.get("metadata") or call_args[1].get("metadata")
        assert metadata["user_id"] == "user1"
        assert metadata["preference_key"] == PreferenceType.DESTINATION

    @pytest.mark.asyncio
    async def test_get_from_memory_before_semantic(self):
        """Test that in-memory preferences are returned before hitting semantic repo."""
        mock_semantic = AsyncMock()
        mock_semantic.search_similar = AsyncMock(return_value=[])

        repo = PreferenceRepository(semantic_repo=mock_semantic)
        pref = MatchedPreference(
            key=PreferenceType.DESTINATION,
            value="北京",
            confidence=0.9
        )
        await repo.upsert("user1", pref)

        # Get preferences - should use in-memory
        prefs = await repo.get_user_preferences("user1")

        assert PreferenceType.DESTINATION in prefs
        assert prefs[PreferenceType.DESTINATION].value == "北京"
        # Semantic repo should NOT be called for direct key lookup
        mock_semantic.search_similar.assert_not_called()
