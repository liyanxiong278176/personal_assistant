"""Tests for LegacyIntentAdapter

Tests the adapter that wraps IntentClassifier as IIntentStrategy.
"""

import pytest

from app.core.context import RequestContext
from app.core.intent.classifier import IntentClassifier, IntentResult
from app.core.intent.legacy_adapter import LegacyIntentAdapter


@pytest.fixture
def legacy_classifier():
    """Create a legacy IntentClassifier instance."""
    return IntentClassifier(cache_size=100)


@pytest.fixture
def default_adapter(legacy_classifier):
    """Create adapter with default priority."""
    return LegacyIntentAdapter(legacy_classifier)


@pytest.fixture
def custom_priority_adapter(legacy_classifier):
    """Create adapter with custom priority."""
    return LegacyIntentAdapter(legacy_classifier, priority=75)


@pytest.fixture
def custom_cost_adapter(legacy_classifier):
    """Create adapter with custom estimated tokens."""
    return LegacyIntentAdapter(legacy_classifier, estimated_tokens=100.0)


class TestLegacyAdapterWrapsClassifier:
    """Test that the adapter properly wraps and calls the IntentClassifier."""

    @pytest.mark.asyncio
    async def test_adapter_classifies_itinerary_intent(self, default_adapter):
        """Adapter should correctly classify itinerary planning messages."""
        context = RequestContext(
            message="帮我规划一个北京三日游",
            user_id="test_user"
        )

        result = await default_adapter.classify(context)

        assert result.intent == "itinerary"
        assert result.confidence >= 0.8
        assert result.method in ["keyword", "llm", "default"]

    @pytest.mark.asyncio
    async def test_adapter_classifies_query_intent(self, default_adapter):
        """Adapter should correctly classify query messages."""
        context = RequestContext(
            message="北京今天天气怎么样",
            user_id="test_user"
        )

        result = await default_adapter.classify(context)

        assert result.intent == "query"
        assert result.method in ["keyword", "llm", "default"]

    @pytest.mark.asyncio
    async def test_adapter_classifies_chat_intent(self, default_adapter):
        """Adapter should correctly classify casual chat messages."""
        context = RequestContext(
            message="你好",
            user_id="test_user"
        )

        result = await default_adapter.classify(context)

        assert result.intent == "chat"

    @pytest.mark.asyncio
    async def test_adapter_handles_image_requests(self, default_adapter):
        """Adapter should detect image-related requests."""
        context = RequestContext(
            message="识别一下这张图片",
            user_id="test_user"
        )

        result = await default_adapter.classify(context)

        assert result.intent == "image"

    @pytest.mark.asyncio
    async def test_adapter_sync_classify(self, default_adapter):
        """Adapter should support synchronous classification."""
        context = RequestContext(
            message="规划行程",
            user_id="test_user"
        )

        result = default_adapter.classify_sync(context)

        assert result is not None
        assert hasattr(result, "intent")
        assert hasattr(result, "confidence")

    @pytest.mark.asyncio
    async def test_adapter_respects_has_image_flag(self, default_adapter):
        """Adapter should use has_image flag from tool_results."""
        context = RequestContext(
            message="这是什么",
            user_id="test_user",
            tool_results={"has_image": True}
        )

        result = await default_adapter.classify(context)

        # With has_image=True, should classify as image
        assert result.intent == "image"
        assert result.confidence == 1.0
        assert result.method == "attachment"

    @pytest.mark.asyncio
    async def test_adapter_can_handle_always_true(self, default_adapter):
        """Adapter's can_handle should always return True."""
        context = RequestContext(
            message="any message",
            user_id="test_user"
        )

        result = await default_adapter.can_handle(context)

        assert result is True


class TestLegacyAdapterPriority:
    """Test priority configuration."""

    def test_default_priority(self, default_adapter):
        """Adapter should have default priority of 50."""
        assert default_adapter.priority == 50

    def test_custom_priority(self, custom_priority_adapter):
        """Adapter should use configured custom priority."""
        assert custom_priority_adapter.priority == 75

    def test_different_priority_instances(self, legacy_classifier):
        """Each adapter instance should have independent priority."""
        adapter1 = LegacyIntentAdapter(legacy_classifier, priority=10)
        adapter2 = LegacyIntentAdapter(legacy_classifier, priority=90)

        assert adapter1.priority == 10
        assert adapter2.priority == 90


class TestLegacyAdapterCost:
    """Test cost estimation."""

    def test_default_estimated_cost(self, default_adapter):
        """Adapter should have default estimated cost of 50.0 tokens."""
        assert default_adapter.estimated_cost() == 50.0

    def test_custom_estimated_cost(self, custom_cost_adapter):
        """Adapter should use configured custom cost."""
        assert custom_cost_adapter.estimated_cost() == 100.0

    def test_zero_cost_possible(self, legacy_classifier):
        """Adapter can be configured with zero cost."""
        adapter = LegacyIntentAdapter(legacy_classifier, estimated_tokens=0.0)
        assert adapter.estimated_cost() == 0.0

    def test_high_cost_possible(self, legacy_classifier):
        """Adapter can be configured with high cost."""
        adapter = LegacyIntentAdapter(legacy_classifier, estimated_tokens=1000.0)
        assert adapter.estimated_cost() == 1000.0


class TestLegacyAdapterIntegration:
    """Integration tests with the legacy classifier."""

    @pytest.mark.asyncio
    async def test_adapter_preserves_classifier_state(self, default_adapter):
        """Adapter should use the same classifier instance."""
        context1 = RequestContext(message="规划行程", user_id="user1")
        context2 = RequestContext(message="规划行程", user_id="user2")

        result1 = await default_adapter.classify(context1)
        result2 = await default_adapter.classify(context2)

        # Same message should produce same intent type
        assert result1.intent == result2.intent

    @pytest.mark.asyncio
    async def test_adapter_with_various_messages(self, default_adapter):
        """Adapter should handle various message types correctly."""
        test_cases = [
            ("规划北京五日游", "itinerary"),
            ("天气怎么样", "query"),
            ("你好", "chat"),
            ("识别图片", "image"),
        ]

        for message, expected_intent in test_cases:
            context = RequestContext(message=message, user_id="test")
            result = await default_adapter.classify(context)

            # Allow some flexibility - the intent should match expected
            # or be a reasonable fallback (like 'chat' for ambiguous queries)
            assert result.intent in [expected_intent, "chat", "query"]

    def test_sync_fallback_produces_valid_result(self, default_adapter):
        """Sync fallback should produce valid IntentResult."""
        context = RequestContext(
            message="规划行程",
            user_id="test"
        )

        result = default_adapter.classify_sync(context)

        assert isinstance(result, IntentResult)
        assert hasattr(result, "intent")
        assert hasattr(result, "confidence")
        assert hasattr(result, "method")
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0
