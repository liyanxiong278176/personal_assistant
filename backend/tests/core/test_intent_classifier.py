"""Tests for three-layer intent classifier."""

import pytest
from app.core.intent.classifier import IntentClassifier, IntentResult, KEYWORD_RULES


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
