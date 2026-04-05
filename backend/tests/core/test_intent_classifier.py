"""Tests for three-layer intent classifier."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.intent.classifier import IntentClassifier, IntentResult, KEYWORD_RULES
from app.core.llm import LLMClient


def test_classify_cache_hit():
    """Test: Cache hit for repeated messages."""
    classifier = IntentClassifier()

    # First call - cache miss
    result1 = classifier.classify_sync("你好在吗")
    assert result1.intent == "chat"

    # Second call - cache hit
    result2 = classifier.classify_sync("你好在吗")
    assert result2.intent == "chat"
    assert result2.method == "cache"


def test_classify_keyword_match():
    """Test: Keyword matching for itinerary intent."""
    classifier = IntentClassifier()

    result = classifier.classify_sync("帮我规划北京三日游")
    assert result.intent == "itinerary"
    assert result.method == "keyword"
    assert result.confidence >= 0.8


def test_classify_query():
    """Test: Query intent detection."""
    classifier = IntentClassifier()

    result = classifier.classify_sync("北京今天天气怎么样")
    assert result.intent == "query"
    assert result.method == "keyword"


def test_classify_image():
    """Test: Image intent detection."""
    classifier = IntentClassifier()

    result = classifier.classify_sync("识别这张图片", has_image=True)
    assert result.intent == "image"
    assert result.method == "attachment"
    assert result.confidence == 1.0


def test_keyword_rules_completeness():
    """Test: Keyword rules completeness."""
    # Verify all intent types are defined
    assert "itinerary" in KEYWORD_RULES
    assert "query" in KEYWORD_RULES
    assert "chat" in KEYWORD_RULES
    assert "image" in KEYWORD_RULES

    # Verify rule structure
    for intent, config in KEYWORD_RULES.items():
        assert "keywords" in config
        assert "weight" in config
        assert isinstance(config["keywords"], list)


def test_classify_pattern_matching():
    """Test: Pattern matching for complex phrases."""
    classifier = IntentClassifier()

    # Test pattern: "去.{2,6}?玩"
    result = classifier.classify_sync("我想去成都玩几天")
    assert result.intent == "itinerary"

    # Test pattern: "规划.*行程"
    result = classifier.classify_sync("帮我规划一下上海五日行程")
    assert result.intent == "itinerary"


def test_lru_cache_eviction():
    """Test: LRU cache eviction when size limit is reached."""
    # Create classifier with small cache size
    classifier = IntentClassifier(cache_size=2)

    # Fill cache
    classifier.classify_sync("message1")
    classifier.classify_sync("message2")

    # Access message1 to make it recently used
    classifier.classify_sync("message1")

    # Add message3 - should evict message2 (LRU)
    classifier.classify_sync("message3")

    # message1 should still be cached
    result1 = classifier.classify_sync("message1")
    assert result1.method == "cache"

    # message2 should have been evicted
    result2 = classifier.classify_sync("message2")
    assert result2.method != "cache"


def test_low_confidence_fallback():
    """Test: Low confidence messages fall back to chat."""
    classifier = IntentClassifier()

    # Ambiguous message with low keyword score
    result = classifier.classify_sync("嗯好的")
    assert result.intent == "chat"
    assert result.confidence < 0.8


# =============================================================================
# Hybrid Mode Tests (Rule + LLM)
# =============================================================================


@pytest.mark.asyncio
async def test_hybrid_mode_simple_query_uses_rule():
    """Test: Simple query uses keyword rule, not LLM."""
    classifier = IntentClassifier()

    result = await classifier.classify("你好")
    assert result.method == "keyword"
    assert result.intent == "chat"


@pytest.mark.asyncio
async def test_hybrid_mode_complex_query_uses_llm():
    """Test: Complex query with is_complex=True uses LLM classifier."""
    # Create mock LLM client
    mock_client = AsyncMock(spec=LLMClient)
    mock_client.chat.return_value = '{"intent": "itinerary", "need_tool": true, "confidence": 0.9}'

    classifier = IntentClassifier(llm_client=mock_client)
    result = await classifier.classify("规划云南7天自驾游预算5000元", is_complex=True)

    assert result.method == "llm"
    assert result.intent == "itinerary"
    assert result.need_tool is True


@pytest.mark.asyncio
async def test_hybrid_mode_image_returns_image_intent():
    """Test: Image attachment returns image intent with highest priority."""
    classifier = IntentClassifier()

    result = await classifier.classify("看看这个", has_image=True)
    assert result.intent == "image"
    assert result.need_tool is True
    assert result.confidence == 1.0
    assert result.method == "attachment"


@pytest.mark.asyncio
async def test_hybrid_mode_complex_by_keywords():
    """Test: Query with complex keywords triggers LLM even without is_complex flag."""
    # Create mock LLM client
    mock_client = AsyncMock(spec=LLMClient)
    mock_client.chat.return_value = '{"intent": "itinerary", "need_tool": true, "confidence": 0.95}'

    classifier = IntentClassifier(llm_client=mock_client)
    result = await classifier.classify("帮我定制一个完美的云南深度游")

    # Should trigger LLM due to "定制" keyword
    assert result.method == "llm"


@pytest.mark.asyncio
async def test_hybrid_mode_keyword_high_confidence_skip_llm():
    """Test: High confidence keyword match skips LLM."""
    # Create mock LLM client - should NOT be called
    mock_client = AsyncMock(spec=LLMClient)

    classifier = IntentClassifier(llm_client=mock_client)
    result = await classifier.classify("北京今天天气怎么样")

    # Should use keyword match, not LLM
    assert result.method == "keyword"
    assert result.intent == "query"
    assert result.confidence >= 0.8
    # LLM should not have been called
    mock_client.chat.assert_not_called()


@pytest.mark.asyncio
async def test_hybrid_mode_llm_fallback_for_low_confidence():
    """Test: Low confidence keyword match falls back to LLM."""
    # Create mock LLM client
    mock_client = AsyncMock(spec=LLMClient)
    mock_client.chat.return_value = '{"intent": "chat", "need_tool": false, "confidence": 0.6}'

    classifier = IntentClassifier(llm_client=mock_client)
    # Message that doesn't match keywords strongly
    result = await classifier.classify("那个地方怎么样", is_complex=False)

    # Should fall back to LLM
    assert result.method == "llm"


@pytest.mark.asyncio
async def test_hybrid_mode_no_llm_client_defaults_to_keyword():
    """Test: Without LLM client, classifier falls back to default."""
    classifier = IntentClassifier(llm_client=None)

    result = await classifier.classify("这是一个复杂的查询请求")

    # Should use default/chat intent when no LLM available
    assert result.intent == "chat"
    assert result.method == "default"


@pytest.mark.asyncio
async def test_hybrid_mode_cache_works_with_llm():
    """Test: Cache works correctly for LLM-classified results."""
    # Create mock LLM client
    mock_client = AsyncMock(spec=LLMClient)
    mock_client.chat.return_value = '{"intent": "itinerary", "need_tool": true, "confidence": 0.9}'

    classifier = IntentClassifier(llm_client=mock_client)

    # First call - should use LLM
    result1 = await classifier.classify("规划云南7天自驾游", is_complex=True)
    assert result1.method == "llm"
    assert mock_client.chat.call_count == 1

    # Second call - should use cache
    result2 = await classifier.classify("规划云南7天自驾游", is_complex=True)
    assert result2.method == "cache"
    assert result2.intent == result1.intent
    # LLM should not be called again
    assert mock_client.chat.call_count == 1


@pytest.mark.asyncio
async def test_hybrid_mode_long_message_triggers_complex_check():
    """Test: Messages longer than 20 chars trigger complexity check."""
    # Create mock LLM client
    mock_client = AsyncMock(spec=LLMClient)
    mock_client.chat.return_value = '{"intent": "itinerary", "need_tool": true, "confidence": 0.9}'

    classifier = IntentClassifier(llm_client=mock_client)

    # Message longer than 20 characters WITHOUT strong keyword matches
    # (avoiding keywords like "旅游", "规划", etc.)
    long_message = "我想去一个非常美丽的地方玩大概七天左右"
    result = await classifier.classify(long_message)

    # Should trigger LLM due to length (>20 chars)
    assert result.method == "llm"
