"""Tests for RuleStrategy keyword-based intent classification.

Tests coverage for all intent types including new intents:
- itinerary (existing)
- query (existing)
- chat (existing)
- hotel (NEW)
- food (NEW)
- budget (NEW)
- transport (NEW)
"""

import pytest
from app.core.intent.strategies.rule import RuleStrategy
from app.core.context import RequestContext


@pytest.fixture
def strategy():
    """Create a RuleStrategy instance for testing."""
    # Use lenient settings for comprehensive testing
    return RuleStrategy(
        max_confidence=0.9,
        max_length=100,  # Allow longer messages
        complex_words=[],  # Don't skip complex words in tests
    )


class TestRuleStrategyPriority:
    """Test RuleStrategy priority and cost properties."""

    def test_rule_strategy_priority(self, strategy):
        """Test: Priority returns 10 (high priority, after cache/image checks)."""
        assert strategy.priority == 10

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
        assert result.method == "rule"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_itinerary_travel(self, strategy):
        """Test: Detects travel-related itinerary requests."""
        context = RequestContext(message="我想去成都旅游几天")
        result = await strategy.classify(context)
        assert result.intent == "itinerary"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_itinerary_plan(self, strategy):
        """Test: Detects itinerary via '计划' keyword."""
        context = RequestContext(message="制定一个上海旅行计划")
        result = await strategy.classify(context)
        assert result.intent == "itinerary"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_itinerary_route(self, strategy):
        """Test: Detects itinerary via '路线' keyword."""
        context = RequestContext(message="设计杭州三日游路线")
        result = await strategy.classify(context)
        assert result.intent == "itinerary"
        assert result.method == "rule"


class TestRuleStrategyClassifyQuery:
    """Test RuleStrategy query intent classification."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_query(self, strategy):
        """Test: Detects query requests by weather keyword."""
        context = RequestContext(message="北京今天天气怎么样")
        result = await strategy.classify(context)
        assert result.intent == "query"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_query_price(self, strategy):
        """Test: Detects query via '价格' keyword."""
        context = RequestContext(message="故宫门票价格是多少")
        result = await strategy.classify(context)
        assert result.intent == "query"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_query_address(self, strategy):
        """Test: Detects query via '地址' keyword."""
        context = RequestContext(message="长城地址在哪里")
        result = await strategy.classify(context)
        assert result.intent == "query"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_query_hours(self, strategy):
        """Test: Detects query via '开放时间' keyword."""
        context = RequestContext(message="景点开放时间是几点")
        result = await strategy.classify(context)
        assert result.intent == "query"
        assert result.method == "rule"


class TestRuleStrategyClassifyChat:
    """Test RuleStrategy chat intent classification."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_chat_greeting(self, strategy):
        """Test: Detects chat via '你好' keyword."""
        context = RequestContext(message="你好")
        result = await strategy.classify(context)
        assert result.intent == "chat"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_chat_thanks(self, strategy):
        """Test: Detects chat via '谢谢' keyword."""
        context = RequestContext(message="谢谢你的帮助")
        result = await strategy.classify(context)
        assert result.intent == "chat"
        assert result.method == "rule"


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
        assert result.method == "rule"


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
        """Test: Query keywords with stronger weight trigger query over chat."""
        context = RequestContext(message="天气怎么样")
        result = await strategy.classify(context)
        # '天气' is a strong query keyword (0.3 weight)
        assert result.intent == "query"


class TestRuleStrategyClassifyHotel:
    """Test RuleStrategy hotel/accommodation intent classification (NEW)."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_hotel(self, strategy):
        """Test: Detects hotel requests via '酒店' keyword."""
        context = RequestContext(message="推荐好的酒店")
        result = await strategy.classify(context)
        assert result.intent == "hotel"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_accommodation(self, strategy):
        """Test: Detects accommodation via '住宿' keyword."""
        context = RequestContext(message="住宿哪里好")
        result = await strategy.classify(context)
        assert result.intent == "hotel"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_guesthouse(self, strategy):
        """Test: Detects hotel via '民宿' keyword."""
        context = RequestContext(message="有好的民宿吗")
        result = await strategy.classify(context)
        assert result.intent == "hotel"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_hotel_pattern(self, strategy):
        """Test: Matches hotel pattern like '北京住哪里'."""
        context = RequestContext(message="北京住哪里")
        result = await strategy.classify(context)
        assert result.intent == "hotel"


class TestRuleStrategyClassifyFood:
    """Test RuleStrategy food/dining intent classification (NEW)."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_food(self, strategy):
        """Test: Detects food requests via '美食' keyword."""
        context = RequestContext(message="推荐当地美食")
        result = await strategy.classify(context)
        assert result.intent == "food"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_snack(self, strategy):
        """Test: Detects food via '小吃' keyword."""
        context = RequestContext(message="有什么特色小吃")
        result = await strategy.classify(context)
        assert result.intent == "food"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_restaurant(self, strategy):
        """Test: Detects food via '餐厅' keyword."""
        context = RequestContext(message="推荐餐厅")
        result = await strategy.classify(context)
        assert result.intent == "food"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_food_pattern(self, strategy):
        """Test: Matches food pattern like '成都有什么好吃的'."""
        context = RequestContext(message="成都有什么好吃的")
        result = await strategy.classify(context)
        assert result.intent == "food"


class TestRuleStrategyClassifyBudget:
    """Test RuleStrategy budget/cost intent classification (NEW)."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_budget(self, strategy):
        """Test: Detects budget requests via '预算' keyword."""
        context = RequestContext(message="大概需要多少预算")
        result = await strategy.classify(context)
        assert result.intent == "budget"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_how_much(self, strategy):
        """Test: Detects budget via '多少钱' keyword."""
        context = RequestContext(message="这要多少钱")
        result = await strategy.classify(context)
        assert result.intent == "budget"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_cost(self, strategy):
        """Test: Detects budget via '花费' keyword."""
        context = RequestContext(message="大概花费多少")
        result = await strategy.classify(context)
        assert result.intent == "budget"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_cheap(self, strategy):
        """Test: Detects budget via '便宜' keyword."""
        context = RequestContext(message="便宜点的地方")
        result = await strategy.classify(context)
        assert result.intent == "budget"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_budget_pattern(self, strategy):
        """Test: Matches budget pattern like '5天预算多少'."""
        context = RequestContext(message="5天预算多少")
        result = await strategy.classify(context)
        assert result.intent == "budget"


class TestRuleStrategyClassifyTransport:
    """Test RuleStrategy transport/travel intent classification (NEW)."""

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_transport(self, strategy):
        """Test: Detects transport via '怎么去' keyword."""
        context = RequestContext(message="怎么去那里")
        result = await strategy.classify(context)
        assert result.intent == "transport"
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_traffic(self, strategy):
        """Test: Detects transport via '交通' keyword."""
        context = RequestContext(message="交通方便吗")
        result = await strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_plane(self, strategy):
        """Test: Detects transport via '飞机' keyword."""
        context = RequestContext(message="坐飞机去")
        result = await strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_high_speed_rail(self, strategy):
        """Test: Detects transport via '高铁' keyword."""
        context = RequestContext(message="高铁票")
        result = await strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_driving(self, strategy):
        """Test: Detects transport via '开车' keyword."""
        context = RequestContext(message="开车去")
        result = await strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_self_drive(self, strategy):
        """Test: Detects transport via '自驾' keyword."""
        context = RequestContext(message="自驾游")
        result = await strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_rule_strategy_classify_transport_pattern(self, strategy):
        """Test: Matches transport pattern like '如何去上海'."""
        context = RequestContext(message="如何去上海")
        result = await strategy.classify(context)
        assert result.intent == "transport"

