"""Tests for RuleStrategy keyword-based intent classification."""

import pytest
from app.core.intent.strategies.rule import RuleStrategy
from app.core.context import RequestContext


@pytest.fixture
def strategy():
    """Create a RuleStrategy instance for testing."""
    return RuleStrategy()


class TestRuleStrategyPriority:
    """Test RuleStrategy priority and cost properties."""

    def test_rule_strategy_priority(self, strategy):
        """Test: Priority returns 1 (highest priority)."""
        assert strategy.priority == 1

    def test_rule_strategy_zero_cost(self, strategy):
        """Test: Estimated cost returns 0.0 (no LLM)."""
        assert strategy.estimated_cost() == 0.0


class TestRuleStrategyCanHandle:
    """Test RuleStrategy.can_handle() method."""

    @pytest.mark.asyncio
    async def test_rule_strategy_can_handle(self, strategy):
        """Test: can_handle always returns True."""
        context = RequestContext(message="随便说点什么")
        assert await strategy.can_handle(context) is True

    @pytest.mark.asyncio
    async def test_rule_strategy_can_handle_empty_message(self, strategy):
        """Test: can_handle returns True for empty messages."""
        context = RequestContext(message="")
        assert await strategy.can_handle(context) is True


class TestRuleStrategyClassifyItinerary:
    """Test RuleStrategy itinerary intent classification."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_itinerary(self, strategy):
        """Test: Detects itinerary requests by keywords."""
        context = RequestContext(message="帮我规划北京三日游")
        result = await strategy.classify(context)
        assert result.intent == "itinerary"
        assert result.method == "keyword"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_itinerary_travel(self, strategy):
        """Test: Detects travel-related itinerary requests."""
        context = RequestContext(message="我想去成都旅游几天")
        result = await strategy.classify(context)
        assert result.intent == "itinerary"
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_itinerary_plan(self, strategy):
        """Test: Detects itinerary via '计划' keyword."""
        context = RequestContext(message="制定一个上海旅行计划")
        result = await strategy.classify(context)
        assert result.intent == "itinerary"
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_itinerary_route(self, strategy):
        """Test: Detects itinerary via '路线' keyword."""
        context = RequestContext(message="设计杭州三日游路线")
        result = await strategy.classify(context)
        assert result.intent == "itinerary"
        assert result.method == "keyword"


class TestRuleStrategyClassifyQuery:
    """Test RuleStrategy query intent classification."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_query(self, strategy):
        """Test: Detects query requests by weather keyword."""
        context = RequestContext(message="北京今天天气怎么样")
        result = await strategy.classify(context)
        assert result.intent == "query"
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_query_price(self, strategy):
        """Test: Detects query via '价格' keyword."""
        context = RequestContext(message="故宫门票价格是多少")
        result = await strategy.classify(context)
        assert result.intent == "query"
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_query_address(self, strategy):
        """Test: Detects query via '地址' keyword."""
        context = RequestContext(message="长城地址在哪里")
        result = await strategy.classify(context)
        assert result.intent == "query"
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_query_hours(self, strategy):
        """Test: Detects query via '开放时间' keyword."""
        context = RequestContext(message="景点开放时间是几点")
        result = await strategy.classify(context)
        assert result.intent == "query"
        assert result.method == "keyword"


class TestRuleStrategyClassifyChat:
    """Test RuleStrategy chat intent classification."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_chat_greeting(self, strategy):
        """Test: Detects chat via '你好' keyword."""
        context = RequestContext(message="你好")
        result = await strategy.classify(context)
        assert result.intent == "chat"
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_chat_thanks(self, strategy):
        """Test: Detects chat via '谢谢' keyword."""
        context = RequestContext(message="谢谢你的帮助")
        result = await strategy.classify(context)
        assert result.intent == "chat"
        assert result.method == "keyword"


class TestRuleStrategyLowConfidence:
    """Test RuleStrategy handling of ambiguous input."""

    @pytest.mark.asyncio
    async def test_rule_strategy_low_confidence(self, strategy):
        """Test: Ambiguous input returns low confidence chat."""
        context = RequestContext(message="嗯好的")
        result = await strategy.classify(context)
        assert result.intent == "chat"
        assert result.confidence < 0.5

    @pytest.mark.asyncio
    async def test_rule_strategy_no_keywords(self, strategy):
        """Test: No keyword matches returns low confidence."""
        context = RequestContext(message="abcxyz123")
        result = await strategy.classify(context)
        assert result.intent == "chat"
        assert result.confidence < 0.5
        assert result.method == "keyword"


class TestRuleStrategyPriorityOrder:
    """Test that RuleStrategy scores intents in correct priority order."""

    @pytest.mark.asyncio
    async def test_rule_strategy_itinerary_over_chat(self, strategy):
        """Test: '旅游' keyword triggers itinerary over chat greetings."""
        # Message contains '你好' (chat) but also '行程' (itinerary)
        context = RequestContext(message="你好，帮我规划北京行程")
        result = await strategy.classify(context)
        # itinerary has more keyword matches than chat
        assert result.intent == "itinerary"

    @pytest.mark.asyncio
    async def test_rule_strategy_query_vs_chat(self, strategy):
        """Test: '景点' keyword triggers query over generic chat."""
        context = RequestContext(message="你好，有哪些景点推荐")
        result = await strategy.classify(context)
        # '景点' is a query keyword, '你好' is chat - query has more weight
        # query has multiple matches (景点, 推荐)
        assert result.intent == "query"
