"""Tests for IIntentStrategy base interface

Tests the contract that all intent strategies must implement.
"""

import pytest

from app.core.context import RequestContext
from app.core.intent.classifier import IntentResult
from app.core.intent.strategies.base import IIntentStrategy


class DummyStrategy(IIntentStrategy):
    """Minimal concrete implementation for testing"""

    def __init__(self, priority: int = 10, cost: float = 0.0):
        self._priority = priority
        self._cost = cost

    @property
    def priority(self) -> int:
        return self._priority

    async def can_handle(self, context: RequestContext) -> bool:
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        return IntentResult(
            intent="chat",
            confidence=0.8,
            method="keyword"  # Use valid MethodType literal value
        )

    def estimated_cost(self) -> float:
        return self._cost


class TestStrategyInterfacePriority:
    """Test priority property of IIntentStrategy"""

    @pytest.mark.asyncio
    async def test_strategy_interface_priority_default(self):
        """Test that strategy returns configured priority"""
        strategy = DummyStrategy(priority=42)
        assert strategy.priority == 42

    @pytest.mark.asyncio
    async def test_strategy_interface_priority_low(self):
        """Test low priority (rule-based range 0-9)"""
        strategy = DummyStrategy(priority=5)
        assert strategy.priority == 5
        assert 0 <= strategy.priority < 10

    @pytest.mark.asyncio
    async def test_strategy_interface_priority_model(self):
        """Test model priority range (10-49)"""
        strategy = DummyStrategy(priority=25)
        assert strategy.priority == 25
        assert 10 <= strategy.priority < 50

    @pytest.mark.asyncio
    async def test_strategy_interface_priority_llm(self):
        """Test LLM priority range (50-99)"""
        strategy = DummyStrategy(priority=75)
        assert strategy.priority == 75
        assert 50 <= strategy.priority < 100

    @pytest.mark.asyncio
    async def test_strategy_interface_priority_fallback(self):
        """Test fallback priority (100)"""
        strategy = DummyStrategy(priority=100)
        assert strategy.priority == 100

    @pytest.mark.asyncio
    async def test_strategies_orderable_by_priority(self):
        """Test that strategies can be ordered by priority"""
        strategies = [
            DummyStrategy(priority=50),
            DummyStrategy(priority=5),
            DummyStrategy(priority=100),
            DummyStrategy(priority=25),
        ]
        sorted_strategies = sorted(strategies, key=lambda s: s.priority)
        priorities = [s.priority for s in sorted_strategies]
        assert priorities == [5, 25, 50, 100]


class TestStrategyInterfaceCost:
    """Test estimated_cost method of IIntentStrategy"""

    @pytest.mark.asyncio
    async def test_strategy_interface_cost_zero(self):
        """Test zero cost for rule-based strategies"""
        strategy = DummyStrategy(priority=5, cost=0.0)
        assert strategy.estimated_cost() == 0.0

    @pytest.mark.asyncio
    async def test_strategy_interface_cost_model(self):
        """Test low cost for model-based strategies"""
        strategy = DummyStrategy(priority=25, cost=50.0)
        assert strategy.estimated_cost() == 50.0

    @pytest.mark.asyncio
    async def test_strategy_interface_cost_llm(self):
        """Test higher cost for LLM-based strategies"""
        strategy = DummyStrategy(priority=75, cost=1000.0)
        assert strategy.estimated_cost() == 1000.0


class TestStrategyInterfaceAbstractMethods:
    """Test that abstract methods must be implemented"""

    def test_cannot_instantiate_abstract_strategy(self):
        """Test that IIntentStrategy cannot be instantiated directly"""
        with pytest.raises(TypeError):
            IIntentStrategy()


class TestStrategyInterfaceCanHandle:
    """Test can_handle method"""

    @pytest.mark.asyncio
    async def test_can_handle_returns_bool(self):
        """Test that can_handle returns a boolean"""
        context = RequestContext(message="test")
        strategy = DummyStrategy()

        result = await strategy.can_handle(context)
        assert isinstance(result, bool)


class TestStrategyInterfaceClassify:
    """Test classify method"""

    @pytest.mark.asyncio
    async def test_classify_returns_intent_result(self):
        """Test that classify returns an IntentResult"""
        context = RequestContext(message="test")
        strategy = DummyStrategy()

        result = await strategy.classify(context)
        assert isinstance(result, IntentResult)
        assert result.intent == "chat"
        assert result.confidence == 0.8
        assert result.method == "keyword"
