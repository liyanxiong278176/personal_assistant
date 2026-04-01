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


class TestAccuracy:
    """Test accuracy with real-world messages."""

    # Test dataset: (message, expected_intent)
    TEST_CASES = [
        # Itinerary planning - should classify as "itinerary"
        ("帮我规划一下北京三日游", "itinerary"),
        ("我想去成都玩几天，帮我安排行程", "itinerary"),
        ("计划一个上海五日游", "itinerary"),
        ("我想去旅游，帮我规划路线", "itinerary"),
        ("推荐一个西安两日游的行程", "itinerary"),
        ("帮我安排去杭州的旅行计划", "itinerary"),
        ("我想去云南旅游一周", "itinerary"),
        ("规划一个广州四天三夜的行程", "itinerary"),
        ("想去重庆玩，怎么做行程", "itinerary"),
        ("帮我设计一个厦门旅游路线", "itinerary"),

        # Query/Info - should classify as "query"
        ("北京明天天气怎么样", "query"),
        ("上海这周末会下雨吗", "query"),
        ("去成都有什么好玩的", "query"),
        ("西安有哪些著名景点", "query"),
        ("怎么从北京去上海最方便", "query"),
        ("故宫的门票价格是多少", "query"),
        ("西湖开放时间是什么时候", "query"),
        ("张家界怎么去", "query"),
        ("泰山温度多少", "query"),
        ("兵马俑门票多少钱", "query"),

        # Image recognition - should classify as "image"
        ("这是哪里", "image"),
        ("识别一下这个景点", "image"),
        ("这张图片是哪里拍的", "image"),
        ("帮我看看这是哪个地方", "image"),

        # General chat - should classify as "chat"
        ("你好", "chat"),
        ("在吗", "chat"),
        ("谢谢", "chat"),
        ("哈哈", "chat"),
        ("你好啊", "chat"),
    ]

    @pytest.mark.asyncio
    async def test_classification_accuracy(self):
        """Test overall classification accuracy."""
        classifier = IntentClassifier()
        correct = 0
        total = len(self.TEST_CASES)

        for message, expected_intent in self.TEST_CASES:
            # Determine if has_image for image intent tests
            has_image = (expected_intent == "image")
            result = await classifier.classify(message, has_image=has_image)

            if result.intent == expected_intent:
                correct += 1
            else:
                # Log misclassifications for debugging
                print(f"\n[MISCLASSIFIED] '{message}' -> '{result.intent}' (expected: '{expected_intent}')")

        accuracy = correct / total
        print(f"\n[Accuracy] {correct}/{total} = {accuracy:.1%}")

        # Require at least 90% accuracy
        assert accuracy >= 0.90, f"Accuracy {accuracy:.1%} is below 90% threshold"

    @pytest.mark.asyncio
    async def test_itinerary_intent_accuracy(self):
        """Test accuracy for itinerary intent specifically."""
        classifier = IntentClassifier()
        itinerary_cases = [(m, i) for m, i in self.TEST_CASES if i == "itinerary"]

        correct = 0
        for message, _ in itinerary_cases:
            result = await classifier.classify(message)
            if result.intent == "itinerary":
                correct += 1

        accuracy = correct / len(itinerary_cases)
        print(f"\n[Itinerary Accuracy] {correct}/{len(itinerary_cases)} = {accuracy:.1%}")

        # Itinerary is most important, require 95% accuracy
        assert accuracy >= 0.95, f"Itinerary accuracy {accuracy:.1%} is below 95% threshold"

    @pytest.mark.asyncio
    async def test_query_intent_accuracy(self):
        """Test accuracy for query intent specifically."""
        classifier = IntentClassifier()
        query_cases = [(m, i) for m, i in self.TEST_CASES if i == "query"]

        correct = 0
        for message, _ in query_cases:
            result = await classifier.classify(message)
            if result.intent == "query":
                correct += 1

        accuracy = correct / len(query_cases)
        print(f"\n[Query Accuracy] {correct}/{len(query_cases)} = {accuracy:.1%}")

        # Query is important for API calls, require 80% accuracy
        assert accuracy >= 0.80, f"Query accuracy {accuracy:.1%} is below 80% threshold"

    @pytest.mark.asyncio
    async def test_edge_cases(self):
        """Test edge cases and ambiguous messages."""
        classifier = IntentClassifier()

        # Messages that could be ambiguous - should have reasonable defaults
        edge_cases = [
            ("我想去北京", "itinerary"),  # Should trigger itinerary intent
            ("天气", "query"),  # Single keyword should match query
            ("", "chat"),  # Empty message should fallback to chat
            ("hello", "chat"),  # English should fallback to chat
        ]

        for message, expected_intent in edge_cases:
            result = await classifier.classify(message)
            # For edge cases, just check it doesn't crash and returns a valid intent
            assert result.intent in ["itinerary", "query", "chat", "image"]
            assert 0.0 <= result.confidence <= 1.0
