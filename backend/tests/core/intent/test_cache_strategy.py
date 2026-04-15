"""Tests for CacheStrategy with dual-layer caching (L1 exact + L2 semantic)."""

import pytest

from app.core.context import RequestContext, IntentResult


class TestCacheStrategyDualLayer:
    """Test dual-layer cache integration in CacheStrategy."""

    @pytest.fixture
    def dual_cache_strategy(self):
        """Create a CacheStrategy with both L1 and L2 cache layers."""
        from app.core.intent.strategies.semantic_cache import SemanticCache
        from app.core.intent.strategies.cache import CacheStrategy, ClassificationCache

        # Mock embedding function - similar embeddings for similar messages
        def mock_embedding(text: str) -> list[float]:
            if "北京" in text:
                return [0.1, 0.2]
            return [0.5, 0.6]

        semantic_cache = SemanticCache(
            embedding_func=mock_embedding,
            similarity_threshold=0.85
        )
        exact_cache = ClassificationCache(max_size=100)

        return CacheStrategy(
            cache=exact_cache,
            semantic_cache=semantic_cache
        )

    @pytest.mark.asyncio
    async def test_l1_hit_skips_l2(self, dual_cache_strategy):
        """L1 cache hit should skip L2 lookup."""
        # Pre-populate L1 cache
        result = IntentResult(
            intent="itinerary",
            confidence=0.9,
            method="rule"
        )
        dual_cache_strategy.cache.put("北京三日游", False, result)

        # Create request context
        context = RequestContext(message="北京三日游")

        # Classify - should hit L1
        classified_result = await dual_cache_strategy.classify(context)

        assert classified_result is not None
        assert classified_result.strategy == "CacheStrategy.L1"
        assert classified_result.intent == "itinerary"

    @pytest.mark.asyncio
    async def test_l1_miss_l2_hit(self, dual_cache_strategy):
        """L1 miss with L2 hit should return L2 result."""
        # Pre-populate L2 cache (semantic cache)
        result = IntentResult(
            intent="itinerary",
            confidence=0.9,
            method="llm"
        )
        embedding = [0.1, 0.2]  # Beijing-related embedding
        dual_cache_strategy._semantic_cache.put("北京玩三天", embedding, result)

        # Create request with semantically similar but different text
        context = RequestContext(message="北京三日游推荐")

        # Classify - should miss L1 but hit L2
        classified_result = await dual_cache_strategy.classify(context)

        assert classified_result is not None
        assert classified_result.strategy == "CacheStrategy.L2"
        assert classified_result.intent == "itinerary"

    @pytest.mark.asyncio
    async def test_both_layers_miss(self, dual_cache_strategy):
        """Both cache layers miss should return None."""
        # Empty caches
        context = RequestContext(message="上海美食推荐")

        result = await dual_cache_strategy.classify(context)

        assert result is None

    @pytest.mark.asyncio
    async def test_put_semantic_high_confidence_only(self, dual_cache_strategy):
        """put_semantic should only cache high-confidence results."""
        high_conf = IntentResult(
            intent="itinerary",
            confidence=0.9,
            method="llm"
        )
        low_conf = IntentResult(
            intent="chat",
            confidence=0.5,
            method="rule"
        )

        await dual_cache_strategy.put_semantic("北京三日游", high_conf)
        await dual_cache_strategy.put_semantic("随便聊聊", low_conf)

        stats = dual_cache_strategy._semantic_cache.get_stats()
        assert stats["size"] == 1  # Only high_conf cached

    @pytest.mark.asyncio
    async def test_put_semantic_exact_threshold(self, dual_cache_strategy):
        """put_semantic should cache results with confidence exactly 0.9."""
        threshold_conf = IntentResult(
            intent="itinerary",
            confidence=0.9,
            method="llm"
        )

        await dual_cache_strategy.put_semantic("北京旅游", threshold_conf)

        stats = dual_cache_strategy._semantic_cache.get_stats()
        assert stats["size"] == 1

    @pytest.mark.asyncio
    async def test_put_semantic_below_threshold(self, dual_cache_strategy):
        """put_semantic should skip results with confidence below 0.9."""
        just_below = IntentResult(
            intent="chat",
            confidence=0.89,
            method="rule"
        )

        await dual_cache_strategy.put_semantic("你好", just_below)

        stats = dual_cache_strategy._semantic_cache.get_stats()
        assert stats["size"] == 0

    @pytest.mark.asyncio
    async def test_put_semantic_no_semantic_cache(self):
        """put_semantic should be safe when semantic_cache is None."""
        from app.core.intent.strategies.cache import CacheStrategy, ClassificationCache

        # Strategy with only L1 cache
        strategy = CacheStrategy(cache=ClassificationCache())
        assert strategy._semantic_cache is None

        result = IntentResult(
            intent="itinerary",
            confidence=0.95,
            method="llm"
        )

        # Should not raise error
        await strategy.put_semantic("北京三日游", result)

    @pytest.mark.asyncio
    async def test_dual_layer_priority_order(self, dual_cache_strategy):
        """Verify L1 is checked before L2."""
        # Put same intent in both layers with different results
        l1_result = IntentResult(
            intent="itinerary",
            confidence=0.9,
            method="rule"
        )
        l2_result = IntentResult(
            intent="query",
            confidence=0.8,
            method="llm"
        )

        # Same message text
        message = "北京三日游"
        dual_cache_strategy.cache.put(message, False, l1_result)
        dual_cache_strategy._semantic_cache.put(message, [0.1, 0.2], l2_result)

        context = RequestContext(message=message)
        result = await dual_cache_strategy.classify(context)

        # Should return L1 result (priority)
        assert result.strategy == "CacheStrategy.L1"
        assert result.intent == "itinerary"

    @pytest.mark.asyncio
    async def test_l2_different_message_semantic_match(self, dual_cache_strategy):
        """L2 should match semantically similar but different messages."""
        result = IntentResult(
            intent="itinerary",
            confidence=0.9,
            method="llm"
        )

        # Store with one message
        dual_cache_strategy._semantic_cache.put("北京去哪玩", [0.1, 0.2], result)

        # Query with similar message
        context = RequestContext(message="北京有什么好玩的")
        classified_result = await dual_cache_strategy.classify(context)

        assert classified_result is not None
        assert classified_result.strategy == "CacheStrategy.L2"
        assert classified_result.intent == "itinerary"

    @pytest.mark.asyncio
    async def test_l2_no_semantic_match_below_threshold(self, dual_cache_strategy):
        """L2 should return None when similarity is below threshold."""
        # Result for Beijing - use orthogonal embedding
        result = IntentResult(
            intent="itinerary",
            confidence=0.9,
            method="llm"
        )
        # [1.0, 0.0] is orthogonal to [0.0, 1.0] (similarity = 0.0)
        dual_cache_strategy._semantic_cache.put("北京旅游", [1.0, 0.0], result)

        # Query for Shanghai - gets different embedding from fixture
        # Shanghai gets [0.5, 0.6] which has low similarity to [1.0, 0.0]
        context = RequestContext(message="上海旅游攻略")
        classified_result = await dual_cache_strategy.classify(context)

        # Should miss both layers
        assert classified_result is None
