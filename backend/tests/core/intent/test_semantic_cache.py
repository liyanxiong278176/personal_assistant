"""Tests for SemanticCache - L2 vector similarity cache for intent classification."""

import pytest
from app.core.intent.strategies.semantic_cache import SemanticCache, cosine_similarity
from app.core.context import IntentResult


class MockEmbedding:
    """Mock embedding function for testing.

    Returns embeddings that match what tests put into the cache:
    - "北京" texts: [0.1, 0.2, 0.3, 0.4] (similar to what's cached)
    - "上海" texts: [1.0, 0.0, 0.0, 0.0] (orthogonal to Beijing)
    - "msg1": returns 2D [0.1, 0.2] to match eviction/clear tests
    - "msg2": returns 2D [0.3, 0.4]
    - "msg3": returns 2D [0.5, 0.6]
    - "msg4": returns 2D [0.7, 0.8]
    - "entry1": [0.1, 0.2, 0.3, 0.4]
    - "entry2": [0.5, 0.6, 0.7, 0.8]
    - "nonexistent": [0.0, 0.0] (2D zero vector)
    """

    def __call__(self, text: str) -> list[float]:
        # Beijing texts - return the same embedding that tests use
        if "北京" in text:
            return [0.1, 0.2, 0.3, 0.4]
        # Shanghai texts - return orthogonal embedding
        elif "上海" in text:
            return [1.0, 0.0, 0.0, 0.0]
        # Test messages with 4D embeddings
        elif "entry1" in text:
            return [0.1, 0.2, 0.3, 0.4]
        elif "entry2" in text:
            return [0.5, 0.6, 0.7, 0.8]
        elif "msg1" in text:
            return [0.1, 0.2]
        elif "msg2" in text:
            return [0.3, 0.4]
        elif "msg3" in text:
            return [0.5, 0.6]
        elif "msg4" in text:
            return [0.7, 0.8]
        # Zero vector for unmatched text
        else:
            return [0.0, 0.0]


@pytest.fixture
def semantic_cache():
    return SemanticCache(
        embedding_func=MockEmbedding(),
        similarity_threshold=0.85,
        max_entries=100
    )


@pytest.fixture
def sample_result():
    return IntentResult(intent="itinerary", confidence=0.9, method="llm")


class TestCosineSimilarity:
    """Test cosine_similarity function."""

    def test_cosine_similarity_identical_vectors(self):
        """Test: Identical vectors return 1.0."""
        vec1 = [0.1, 0.2, 0.3, 0.4]
        vec2 = [0.1, 0.2, 0.3, 0.4]
        result = cosine_similarity(vec1, vec2)
        assert result == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal_vectors(self):
        """Test: Orthogonal vectors return 0.0."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        result = cosine_similarity(vec1, vec2)
        assert result == pytest.approx(0.0)

    def test_cosine_similarity_opposite_vectors(self):
        """Test: Opposite vectors return -1.0."""
        vec1 = [1.0, 1.0]
        vec2 = [-1.0, -1.0]
        result = cosine_similarity(vec1, vec2)
        assert result == pytest.approx(-1.0)

    def test_cosine_similarity_zero_norm(self):
        """Test: Zero norm vectors return 0.0."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [0.1, 0.2, 0.3]
        result = cosine_similarity(vec1, vec2)
        assert result == 0.0

    def test_cosine_similarity_different_lengths(self):
        """Test: Different length vectors return 0.0."""
        vec1 = [0.1, 0.2]
        vec2 = [0.1, 0.2, 0.3]
        result = cosine_similarity(vec1, vec2)
        assert result == 0.0


class TestSemanticCacheGet:
    """Test SemanticCache.get() method."""

    @pytest.mark.asyncio
    async def test_semantic_cache_returns_best_match(self, semantic_cache, sample_result):
        """Test: Returns highest similarity match, not first match."""
        # Add two similar entries
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], sample_result)
        semantic_cache.put("北京五日游", [0.11, 0.21, 0.31, 0.41], sample_result)

        # Query with similar embedding - should return best match
        result = await semantic_cache.get("北京三日游推荐")
        assert result is not None
        assert result.intent == "itinerary"

    @pytest.mark.asyncio
    async def test_semantic_cache_exact_match(self, semantic_cache, sample_result):
        """Test: Exact text match returns cached result."""
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], sample_result)
        result = await semantic_cache.get("北京三日游")
        assert result is not None
        assert result.intent == "itinerary"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_semantic_cache_miss_below_threshold(self, semantic_cache, sample_result):
        """Test: Returns None when similarity below threshold."""
        # Add Shanghai entry with orthogonal embedding
        semantic_cache.put("上海三日游", [1.0, 0.0, 0.0, 0.0], sample_result)

        # Query with Beijing (orthogonal embedding = 0 similarity)
        result = await semantic_cache.get("北京三日游")
        assert result is None

    @pytest.mark.asyncio
    async def test_semantic_cache_empty_returns_none(self, semantic_cache):
        """Test: Empty cache returns None."""
        result = await semantic_cache.get("北京三日游")
        assert result is None

    @pytest.mark.asyncio
    async def test_semantic_cache_tracks_best_similarity(self, semantic_cache, sample_result):
        """Test: Iterates all entries to find best match."""
        # Add multiple entries with different similarities
        semantic_cache.put("entry1", [0.1, 0.2, 0.3, 0.4], sample_result)
        semantic_cache.put("entry2", [0.5, 0.6, 0.7, 0.8], sample_result)

        # Query should find best match
        result = await semantic_cache.get("北京旅游")
        assert result is not None


class TestSemanticCachePut:
    """Test SemanticCache.put() method."""

    def test_semantic_cache_deduplicate(self, semantic_cache, sample_result):
        """Test: Deduplicates identical messages."""
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], sample_result)
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], sample_result)
        assert len(semantic_cache._cache) == 1

    def test_semantic_cache_deduplicate_with_whitespace(self, semantic_cache, sample_result):
        """Test: Deduplicates messages with same stripped content."""
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], sample_result)
        semantic_cache.put("  北京三日游  ", [0.1, 0.2, 0.3, 0.4], sample_result)
        assert len(semantic_cache._cache) == 1

    def test_semantic_cache_eviction(self, sample_result):
        """Test: FIFO eviction when over capacity."""
        small_cache = SemanticCache(
            embedding_func=MockEmbedding(),
            max_entries=3
        )
        result1 = IntentResult(intent="itinerary", confidence=0.9, method="llm")
        result2 = IntentResult(intent="query", confidence=0.8, method="rule")
        result3 = IntentResult(intent="chat", confidence=0.7, method="llm")
        result4 = IntentResult(intent="itinerary", confidence=0.95, method="llm")

        small_cache.put("msg1", [0.1, 0.2], result1)
        small_cache.put("msg2", [0.3, 0.4], result2)
        small_cache.put("msg3", [0.5, 0.6], result3)
        small_cache.put("msg4", [0.7, 0.8], result4)

        # Should have 3 entries, oldest (msg1) evicted
        assert len(small_cache._cache) == 3
        # First entry should now be msg2
        assert small_cache._cache[0]["message"] == "msg2"

    def test_semantic_cache_put_updates_existing(self, semantic_cache, sample_result):
        """Test: Putting same message updates the entry."""
        result1 = IntentResult(intent="itinerary", confidence=0.9, method="llm")
        result2 = IntentResult(intent="query", confidence=0.8, method="rule")

        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], result1)
        assert semantic_cache._cache[0]["result"].intent == "itinerary"

        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], result2)
        assert semantic_cache._cache[0]["result"].intent == "query"
        assert len(semantic_cache._cache) == 1


class TestSemanticCacheClear:
    """Test SemanticCache.clear() method."""

    def test_semantic_cache_clear(self, semantic_cache, sample_result):
        """Test: Clear removes all entries."""
        semantic_cache.put("msg1", [0.1, 0.2], sample_result)
        semantic_cache.put("msg2", [0.3, 0.4], sample_result)
        assert len(semantic_cache._cache) == 2

        semantic_cache.clear()
        assert len(semantic_cache._cache) == 0

    @pytest.mark.asyncio
    async def test_semantic_cache_clear_resets_stats(self, semantic_cache, sample_result):
        """Test: Clear resets hit/miss statistics."""
        semantic_cache.put("msg1", [0.1, 0.2], sample_result)

        # Generate some stats
        await semantic_cache.get("msg1")  # hit
        await semantic_cache.get("nonexistent")  # miss

        stats_before = semantic_cache.get_stats()
        assert stats_before["hits"] == 1
        assert stats_before["misses"] == 1

        semantic_cache.clear()
        stats_after = semantic_cache.get_stats()
        assert stats_after["hits"] == 0
        assert stats_after["misses"] == 0


class TestSemanticCacheStats:
    """Test SemanticCache.get_stats() method."""

    @pytest.mark.asyncio
    async def test_semantic_cache_stats_empty(self, semantic_cache):
        """Test: Stats for empty cache."""
        stats = semantic_cache.get_stats()
        assert stats["size"] == 0
        assert stats["max_entries"] == 100
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_semantic_cache_stats_with_entries(self, semantic_cache, sample_result):
        """Test: Stats reflect cache entries."""
        semantic_cache.put("msg1", [0.1, 0.2], sample_result)
        semantic_cache.put("msg2", [0.3, 0.4], sample_result)

        stats = semantic_cache.get_stats()
        assert stats["size"] == 2

    @pytest.mark.asyncio
    async def test_semantic_cache_stats_hit_rate(self, semantic_cache, sample_result):
        """Test: Hit rate calculation."""
        # Use a key that returns 4D embedding to match what we put
        semantic_cache.put("北京消息", [0.1, 0.2, 0.3, 0.4], sample_result)

        await semantic_cache.get("北京消息")  # hit
        await semantic_cache.get("北京消息")  # hit
        await semantic_cache.get("nonexistent")  # miss

        stats = semantic_cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(0.666, rel=0.01)


class TestSemanticCacheIntegration:
    """Integration tests for SemanticCache."""

    @pytest.mark.asyncio
    async def test_semantic_cache_full_workflow(self, semantic_cache):
        """Test: Full workflow of put, get, stats, clear."""
        result1 = IntentResult(intent="itinerary", confidence=0.9, method="llm")

        # Cache miss initially
        result = await semantic_cache.get("北京三日游")
        assert result is None

        # Add to cache
        semantic_cache.put("北京三日游", [0.1, 0.2, 0.3, 0.4], result1)

        # Cache hit
        result = await semantic_cache.get("北京三日游")
        assert result is not None
        assert result.intent == "itinerary"

        # Check stats
        stats = semantic_cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

        # Clear and verify
        semantic_cache.clear()
        result = await semantic_cache.get("北京三日游")
        assert result is None
