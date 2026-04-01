"""Tests for intent classifier."""

import pytest
import asyncio
from app.services.intent_classifier import (
    IntentClassifier,
    IntentResult,
    _match_by_keywords,
    INTENT_KEYWORDS
)


class TestKeywordMatching:
    """Test keyword-based intent matching."""

    def test_match_itinerary_keyword(self):
        """Test itinerary keyword matching."""
        intent, confidence = _match_by_keywords("帮我规划一下北京行程")
        assert intent == "itinerary"
        assert confidence >= 0.8

    def test_match_query_keyword(self):
        """Test query keyword matching."""
        intent, confidence = _match_by_keywords("北京明天天气怎么样")
        assert intent == "query"

    def test_match_chat_keyword(self):
        """Test chat keyword matching."""
        intent, confidence = _match_by_keywords("你好，在吗")
        assert intent == "chat"

    def test_no_keyword_match(self):
        """Test message with no matching keywords."""
        intent, confidence = _match_by_keywords("xyz123")
        assert intent is None
        assert confidence == 0.0

    def test_multiple_keywords_selects_highest_weight(self):
        """Test that highest weight is selected when multiple keywords match."""
        # "行程" in itinerary (weight 1.0)
        # "怎么去" in query (weight 0.8)
        intent, confidence = _match_by_keywords("行程怎么去")
        assert intent == "itinerary"  # Should select higher weight
        assert confidence == 1.0


class TestIntentClassifier:
    """Test IntentClassifier class."""

    @pytest.mark.asyncio
    async def test_classify_with_image(self):
        """Test classification when message has image."""
        classifier = IntentClassifier()
        result = await classifier.classify("test message", has_image=True)
        assert result.intent == "image"
        assert result.method == "attachment"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_classify_itinerary_by_keyword(self):
        """Test itinerary classification by keyword."""
        classifier = IntentClassifier()
        result = await classifier.classify("帮我规划行程")
        assert result.intent == "itinerary"
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_classify_query_by_keyword(self):
        """Test query classification by keyword."""
        classifier = IntentClassifier()
        result = await classifier.classify("明天天气怎么样")
        assert result.intent == "query"
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_classify_chat_fallback(self):
        """Test chat intent fallback for unrecognized messages."""
        classifier = IntentClassifier()
        result = await classifier.classify("xyz123")
        assert result.intent == "chat"
        assert result.method == "llm"  # Currently uses LLM placeholder

    @pytest.mark.asyncio
    async def test_cache_works(self):
        """Test that classification results are cached."""
        classifier = IntentClassifier()
        message = "帮我规划行程"

        # First call
        result1 = await classifier.classify(message)
        # Second call should hit cache
        result2 = await classifier.classify(message)

        assert result1.intent == result2.intent
        assert result1.method == result2.method
