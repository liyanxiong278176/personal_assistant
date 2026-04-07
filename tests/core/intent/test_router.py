"""Tests for IntentRouter

Tests the strategy chain orchestration, confidence-based routing,
and clarification flow.
"""

import pytest

from app.core.context import RequestContext
from app.core.intent.classifier import IntentResult
from app.core.intent.config import IntentRouterConfig
from app.core.intent.router import ClarificationResult, IntentRouter, RouterStatistics
from app.core.intent.strategies.base import IIntentStrategy


class MockHighConfidenceStrategy(IIntentStrategy):
    """Mock strategy that always returns high confidence."""

    def __init__(self, intent: str = "itinerary", confidence: float = 0.95, priority: int = 1):
        self._intent = intent
        self._confidence = confidence
        self._priority = priority
        self.classify_called = False

    @property
    def priority(self) -> int:
        return self._priority

    async def can_handle(self, context: RequestContext) -> bool:
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        self.classify_called = True
        return IntentResult(
            intent=self._intent,
            confidence=self._confidence,
            method="keyword",  # Use valid MethodType value
            reasoning="Mock high confidence result",
        )

    def estimated_cost(self) -> float:
        return 0.0


class MockMediumConfidenceStrategy(IIntentStrategy):
    """Mock strategy that returns medium confidence."""

    def __init__(self, intent: str = "query", confidence: float = 0.75, priority: int = 10):
        self._intent = intent
        self._confidence = confidence
        self._priority = priority
        self.classify_called = False

    @property
    def priority(self) -> int:
        return self._priority

    async def can_handle(self, context: RequestContext) -> bool:
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        self.classify_called = True
        return IntentResult(
            intent=self._intent,
            confidence=self._confidence,
            method="llm",  # Use valid MethodType value
            reasoning="Mock medium confidence result",
        )

    def estimated_cost(self) -> float:
        return 10.0


class MockLowConfidenceStrategy(IIntentStrategy):
    """Mock strategy that returns low confidence."""

    def __init__(self, intent: str = "chat", confidence: float = 0.5, priority: int = 20):
        self._intent = intent
        self._confidence = confidence
        self._priority = priority
        self.classify_called = False

    @property
    def priority(self) -> int:
        return self._priority

    async def can_handle(self, context: RequestContext) -> bool:
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        self.classify_called = True
        return IntentResult(
            intent=self._intent,
            confidence=self._confidence,
            method="default",  # Use valid MethodType value
            reasoning="Mock low confidence result",
        )

    def estimated_cost(self) -> float:
        return 20.0


class MockCannotHandleStrategy(IIntentStrategy):
    """Mock strategy that never handles requests."""

    @property
    def priority(self) -> int:
        return 5

    async def can_handle(self, context: RequestContext) -> bool:
        return False

    async def classify(self, context: RequestContext) -> IntentResult:
        raise AssertionError("classify should not be called when can_handle returns False")

    def estimated_cost(self) -> float:
        return 0.0


class MockFailingStrategy(IIntentStrategy):
    """Mock strategy that always fails during classification."""

    def __init__(self, priority: int = 5):
        self._priority = priority

    @property
    def priority(self) -> int:
        return self._priority

    async def can_handle(self, context: RequestContext) -> bool:
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        raise RuntimeError("Strategy failed intentionally")

    def estimated_cost(self) -> float:
        return 0.0


@pytest.fixture
def router_config():
    """Create a test router configuration."""
    return IntentRouterConfig(
        high_confidence_threshold=0.9,
        mid_confidence_threshold=0.7,
        max_clarification_rounds=2,
        enable_clarification=True,
    )


@pytest.fixture
def context():
    """Create a test request context."""
    return RequestContext(
        message="Plan a 3-day trip to Beijing",
        user_id="test_user",
        conversation_id="test_conv",
    )


class TestIntentRouter:
    """Test IntentRouter strategy chain orchestration."""

    @pytest.mark.asyncio
    async def test_router_classifies_with_rule_strategy(self, router_config, context):
        """Test high confidence classification stops the strategy chain."""
        # Setup: High confidence strategy + low confidence fallback
        high_strategy = MockHighConfidenceStrategy(intent="itinerary", confidence=0.95)
        low_strategy = MockLowConfidenceStrategy()

        router = IntentRouter([high_strategy, low_strategy], router_config)

        # Execute
        result = await router.classify(context)

        # Assert: High confidence strategy should win
        assert result.intent == "itinerary"
        assert result.confidence == 0.95
        assert result.method == "keyword"
        assert high_strategy.classify_called
        assert not low_strategy.classify_called  # Chain stopped early

        # Verify statistics
        stats = router.get_statistics()
        assert stats["total_classifications"] == 1
        assert stats["confidence_distribution"]["high"] == 1
        assert stats["clarification_count"] == 0

    @pytest.mark.asyncio
    async def test_router_fallback_to_llm(self, router_config, context):
        """Test low confidence triggers fallback to next strategy."""
        # Setup: Low confidence strategy + high confidence fallback
        low_strategy = MockLowConfidenceStrategy(confidence=0.5)
        high_strategy = MockHighConfidenceStrategy(priority=100, confidence=0.92)

        router = IntentRouter([low_strategy, high_strategy], router_config)

        # Execute
        result = await router.classify(context)

        # Assert: Should fall through to high confidence strategy
        assert result.intent == "itinerary"
        assert result.confidence == 0.92
        assert result.method == "keyword"
        assert low_strategy.classify_called
        assert high_strategy.classify_called

        # Verify statistics
        stats = router.get_statistics()
        assert stats["confidence_distribution"]["low"] == 1
        assert stats["confidence_distribution"]["high"] == 1

    @pytest.mark.asyncio
    async def test_router_clarification_flow(self, router_config, context):
        """Test medium confidence triggers clarification."""
        # Setup: Medium confidence strategy
        medium_strategy = MockMediumConfidenceStrategy(confidence=0.75)
        router = IntentRouter([medium_strategy], router_config)

        # Execute
        result = await router.classify(context)

        # Assert: Should accept medium confidence with clarification
        assert result.intent == "query"
        assert result.confidence == 0.75
        assert "clarification:" in result.reasoning

        # Verify statistics
        stats = router.get_statistics()
        assert stats["confidence_distribution"]["mid"] == 1
        assert stats["clarification_count"] == 1

    @pytest.mark.asyncio
    async def test_router_clarification_limit(self, router_config, context):
        """Test clarification stops when max rounds reached."""
        # Setup: Medium confidence strategy, context at clarification limit
        medium_strategy = MockMediumConfidenceStrategy(confidence=0.75)
        router = IntentRouter([medium_strategy], router_config)

        # Set clarification count to max
        context.clarification_count = 2

        # Execute
        result = await router.classify(context)

        # Assert: Should accept medium confidence without new clarification
        assert result.intent == "query"
        assert result.confidence == 0.75
        # No new clarification triggered
        stats = router.get_statistics()
        assert stats["clarification_count"] == 0

    @pytest.mark.asyncio
    async def test_router_can_handle_filter(self, router_config, context):
        """Test strategies that can't handle are skipped."""
        # Setup: Strategy that can't handle + one that can
        cannot_handle = MockCannotHandleStrategy()
        can_handle = MockHighConfidenceStrategy(priority=10)

        router = IntentRouter([cannot_handle, can_handle], router_config)

        # Execute
        result = await router.classify(context)

        # Assert: Should skip to the handling strategy
        assert result.intent == "itinerary"
        assert can_handle.classify_called

    @pytest.mark.asyncio
    async def test_router_strategies_sorted_by_priority(self, context):
        """Test strategies are executed in priority order."""
        # Setup: Strategies in reverse priority order - use valid intent values
        low_priority = MockHighConfidenceStrategy(priority=100, intent="query")
        high_priority = MockHighConfidenceStrategy(priority=1, intent="itinerary")

        router = IntentRouter([low_priority, high_priority])

        # Execute
        result = await router.classify(context)

        # Assert: High priority (lower number) should execute first
        assert result.intent == "itinerary"
        assert high_priority.classify_called
        assert not low_priority.classify_called

    @pytest.mark.asyncio
    async def test_router_fallback_when_all_fail(self, router_config, context):
        """Test fallback result when all strategies fail with exceptions."""
        # Setup: All strategies raise exceptions (true failure)
        failing1 = MockFailingStrategy(priority=1)
        failing2 = MockFailingStrategy(priority=10)

        router = IntentRouter([failing1, failing2], router_config)

        # Execute
        result = await router.classify(context)

        # Assert: Should return fallback result (0.5 from router's fallback)
        assert result.intent == "chat"
        assert result.method == "default"
        assert result.confidence == 0.5
        assert "fallback" in result.reasoning.lower()

        stats = router.get_statistics()
        assert stats["fallback_count"] == 1

    @pytest.mark.asyncio
    async def test_router_returns_best_effort(self, router_config, context):
        """Test best effort result when all strategies have low confidence."""
        # Setup: Multiple low confidence strategies
        low1 = MockLowConfidenceStrategy(confidence=0.3)
        low2 = MockLowConfidenceStrategy(confidence=0.5)
        low3 = MockLowConfidenceStrategy(confidence=0.4)

        router = IntentRouter([low1, low2, low3], router_config)

        # Execute
        result = await router.classify(context)

        # Assert: Should return best (0.5) from low2
        assert result.confidence == 0.5
        assert result.method == "default"

        stats = router.get_statistics()
        assert stats["fallback_count"] == 0  # Not a true fallback

    def test_get_statistics(self, router_config):
        """Test statistics collection."""
        router = IntentRouter([], router_config)

        stats = router.get_statistics()

        assert "total_classifications" in stats
        assert "strategy_counts" in stats
        assert "confidence_distribution" in stats
        assert "clarification_count" in stats
        assert "fallback_count" in stats
        assert "strategies" in stats
        assert "config" in stats

    def test_reset_statistics(self, router_config):
        """Test statistics reset."""
        router = IntentRouter([], router_config)
        # Manually increment some stats
        router._stats.total_classifications = 10
        router._stats.clarification_count = 3

        router.reset_statistics()

        stats = router.get_statistics()
        assert stats["total_classifications"] == 0
        assert stats["clarification_count"] == 0


class TestClarificationResult:
    """Test ClarificationResult dataclass."""

    def test_clarification_result_to_dict(self):
        """Test ClarificationResult serialization."""
        result = ClarificationResult(
            needs_clarification=True,
            question="What is your destination?",
            original_intent="itinerary",
            suggested_followup=["Where?", "When?"],
        )

        data = result.to_dict()

        assert data["needs_clarification"] is True
        assert data["question"] == "What is your destination?"
        assert data["original_intent"] == "itinerary"
        assert data["suggested_followup"] == ["Where?", "When?"]


class TestRouterConfig:
    """Test IntentRouterConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = IntentRouterConfig()

        assert config.high_confidence_threshold == 0.9
        assert config.mid_confidence_threshold == 0.7
        assert config.max_clarification_rounds == 2
        assert config.enable_clarification is True

    def test_confidence_checkers(self):
        """Test confidence threshold checking methods."""
        config = IntentRouterConfig(
            high_confidence_threshold=0.9,
            mid_confidence_threshold=0.7,
        )

        assert config.is_high_confidence(0.95) is True
        assert config.is_high_confidence(0.9) is True
        assert config.is_high_confidence(0.89) is False

        assert config.is_mid_confidence(0.75) is True
        assert config.is_mid_confidence(0.7) is True
        assert config.is_mid_confidence(0.69) is False
        assert config.is_mid_confidence(0.91) is False

        assert config.is_low_confidence(0.5) is True
        assert config.is_low_confidence(0.69) is True
        assert config.is_low_confidence(0.7) is False

    def test_can_clarify(self):
        """Test clarification availability check."""
        config = IntentRouterConfig(
            enable_clarification=True,
            max_clarification_rounds=2,
        )

        assert config.can_clarify(0) is True
        assert config.can_clarify(1) is True
        assert config.can_clarify(2) is False

        config.enable_clarification = False
        assert config.can_clarify(0) is False
