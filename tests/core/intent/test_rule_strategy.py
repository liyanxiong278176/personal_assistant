"""Tests for RuleStrategy intent classification.

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

from app.core.context import RequestContext
from app.core.intent.strategies.rule import RuleStrategy


@pytest.fixture
def rule_strategy():
    """Create a RuleStrategy instance for testing."""
    return RuleStrategy(
        max_confidence=0.9,
        keyword_weight=1.0,
        pattern_weight=0.15,
        max_length=50,  # Longer than default for testing
        complex_words=[],  # Disable complex word filtering for tests
    )


class TestRuleStrategyBasicFunctionality:
    """Test basic RuleStrategy functionality."""

    @pytest.mark.asyncio
    async def test_priority(self, rule_strategy):
        """RuleStrategy should have priority 10."""
        assert rule_strategy.priority == 10

    @pytest.mark.asyncio
    async def test_estimated_cost(self, rule_strategy):
        """RuleStrategy should have zero cost."""
        assert rule_strategy.estimated_cost() == 0.0

    @pytest.mark.asyncio
    async def test_can_handle_simple_message(self, rule_strategy):
        """Should handle simple short messages."""
        context = RequestContext(message="你好")
        assert await rule_strategy.can_handle(context)

    @pytest.mark.asyncio
    async def test_cannot_handle_too_long(self, rule_strategy):
        """Should skip very long messages."""
        context = RequestContext(message="a" * 100)
        assert not await rule_strategy.can_handle(context)

    @pytest.mark.asyncio
    async def test_cannot_handle_with_image(self, rule_strategy):
        """Should skip messages with images."""
        context = RequestContext(message="天气", has_image=True)
        assert not await rule_strategy.can_handle(context)

    @pytest.mark.asyncio
    async def test_cannot_handle_complex(self, rule_strategy):
        """Should skip messages marked as complex."""
        context = RequestContext(message="规划", is_complex=True)
        assert not await rule_strategy.can_handle(context)


class TestItineraryIntent:
    """Test itinerary/planning intent classification."""

    @pytest.mark.asyncio
    async def test_itinerary_with_keywords(self, rule_strategy):
        """Should classify itinerary with keyword '行程'."""
        context = RequestContext(message="帮我做个行程")
        result = await rule_strategy.classify(context)
        assert result.intent == "itinerary"
        assert result.confidence >= 0.2
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_itinerary_with_route_keyword(self, rule_strategy):
        """Should classify itinerary with keyword '路线'."""
        context = RequestContext(message="推荐路线")
        result = await rule_strategy.classify(context)
        assert result.intent == "itinerary"

    @pytest.mark.asyncio
    async def test_itinerary_with_pattern(self, rule_strategy):
        """Should match itinerary patterns like '去北京玩'."""
        context = RequestContext(message="去北京玩")
        result = await rule_strategy.classify(context)
        assert result.intent == "itinerary"


class TestQueryIntent:
    """Test information query intent classification."""

    @pytest.mark.asyncio
    async def test_query_with_weather_keyword(self, rule_strategy):
        """Should classify query with keyword '天气'."""
        context = RequestContext(message="今天天气怎么样")
        result = await rule_strategy.classify(context)
        assert result.intent == "query"
        assert result.confidence >= 0.2

    @pytest.mark.asyncio
    async def test_query_with_ticket_price(self, rule_strategy):
        """Should classify query with keyword '门票'."""
        context = RequestContext(message="门票多少钱")
        result = await rule_strategy.classify(context)
        assert result.intent == "query"

    @pytest.mark.asyncio
    async def test_query_with_temperature(self, rule_strategy):
        """Should classify query with keyword '温度'."""
        context = RequestContext(message="现在的温度")
        result = await rule_strategy.classify(context)
        assert result.intent == "query"


class TestChatIntent:
    """Test casual chat intent classification."""

    @pytest.mark.asyncio
    async def test_chat_with_greeting(self, rule_strategy):
        """Should classify chat with keyword '你好'."""
        context = RequestContext(message="你好")
        result = await rule_strategy.classify(context)
        assert result.intent == "chat"

    @pytest.mark.asyncio
    async def test_chat_with_thanks(self, rule_strategy):
        """Should classify chat with keyword '谢谢'."""
        context = RequestContext(message="谢谢帮忙")
        result = await rule_strategy.classify(context)
        assert result.intent == "chat"


class TestHotelIntent:
    """Test hotel/accommodation intent classification (NEW)."""

    @pytest.mark.asyncio
    async def test_hotel_with_hotel_keyword(self, rule_strategy):
        """Should classify hotel intent with keyword '酒店'."""
        context = RequestContext(message="推荐酒店")
        result = await rule_strategy.classify(context)
        assert result.intent == "hotel"
        assert result.confidence >= 0.2

    @pytest.mark.asyncio
    async def test_hotel_with_accommodation_keyword(self, rule_strategy):
        """Should classify hotel intent with keyword '住宿'."""
        context = RequestContext(message="住宿哪里好")
        result = await rule_strategy.classify(context)
        assert result.intent == "hotel"

    @pytest.mark.asyncio
    async def test_hotel_with_guesthouse_keyword(self, rule_strategy):
        """Should classify hotel intent with keyword '民宿'."""
        context = RequestContext(message="有好的民宿吗")
        result = await rule_strategy.classify(context)
        assert result.intent == "hotel"

    @pytest.mark.asyncio
    async def test_hotel_with_checkin_keyword(self, rule_strategy):
        """Should classify hotel intent with keyword '入住'."""
        context = RequestContext(message="怎么入住")
        result = await rule_strategy.classify(context)
        assert result.intent == "hotel"

    @pytest.mark.asyncio
    async def test_hotel_with_pattern(self, rule_strategy):
        """Should match hotel patterns like '北京住哪里'."""
        context = RequestContext(message="北京住哪里")
        result = await rule_strategy.classify(context)
        assert result.intent == "hotel"


class TestFoodIntent:
    """Test food/dining intent classification (NEW)."""

    @pytest.mark.asyncio
    async def test_food_with_food_keyword(self, rule_strategy):
        """Should classify food intent with keyword '美食'."""
        context = RequestContext(message="推荐美食")
        result = await rule_strategy.classify(context)
        assert result.intent == "food"
        assert result.confidence >= 0.2

    @pytest.mark.asyncio
    async def test_food_with_snack_keyword(self, rule_strategy):
        """Should classify food intent with keyword '小吃'."""
        context = RequestContext(message="有什么小吃")
        result = await rule_strategy.classify(context)
        assert result.intent == "food"

    @pytest.mark.asyncio
    async def test_food_with_restaurant_keyword(self, rule_strategy):
        """Should classify food intent with keyword '餐厅'."""
        context = RequestContext(message="推荐餐厅")
        result = await rule_strategy.classify(context)
        assert result.intent == "food"

    @pytest.mark.asyncio
    async def test_food_with_eat_keyword(self, rule_strategy):
        """Should classify food intent with keyword '吃'."""
        context = RequestContext(message="吃什么好")
        result = await rule_strategy.classify(context)
        assert result.intent == "food"

    @pytest.mark.asyncio
    async def test_food_with_pattern(self, rule_strategy):
        """Should match food patterns like '成都有什么好吃的'."""
        context = RequestContext(message="成都有什么好吃的")
        result = await rule_strategy.classify(context)
        assert result.intent == "food"


class TestBudgetIntent:
    """Test budget/cost intent classification (NEW)."""

    @pytest.mark.asyncio
    async def test_budget_with_budget_keyword(self, rule_strategy):
        """Should classify budget intent with keyword '预算'."""
        context = RequestContext(message="预算多少")
        result = await rule_strategy.classify(context)
        assert result.intent == "budget"
        assert result.confidence >= 0.2

    @pytest.mark.asyncio
    async def test_budget_with_how_much_keyword(self, rule_strategy):
        """Should classify budget intent with keyword '多少钱'."""
        context = RequestContext(message="要多少钱")
        result = await rule_strategy.classify(context)
        assert result.intent == "budget"

    @pytest.mark.asyncio
    async def test_budget_with_cost_keyword(self, rule_strategy):
        """Should classify budget intent with keyword '花费'."""
        context = RequestContext(message="大概花费")
        result = await rule_strategy.classify(context)
        assert result.intent == "budget"

    @pytest.mark.asyncio
    async def test_budget_with_cheap_keyword(self, rule_strategy):
        """Should classify budget intent with keyword '便宜'."""
        context = RequestContext(message="便宜点的地方")
        result = await rule_strategy.classify(context)
        assert result.intent == "budget"

    @pytest.mark.asyncio
    async def test_budget_with_pattern(self, rule_strategy):
        """Should match budget patterns like '5天预算多少'."""
        context = RequestContext(message="5天预算多少")
        result = await rule_strategy.classify(context)
        assert result.intent == "budget"


class TestTransportIntent:
    """Test transport/travel intent classification (NEW)."""

    @pytest.mark.asyncio
    async def test_transport_with_how_to_go_keyword(self, rule_strategy):
        """Should classify transport intent with keyword '怎么去'."""
        context = RequestContext(message="怎么去那里")
        result = await rule_strategy.classify(context)
        assert result.intent == "transport"
        assert result.confidence >= 0.2

    @pytest.mark.asyncio
    async def test_transport_with_traffic_keyword(self, rule_strategy):
        """Should classify transport intent with keyword '交通'."""
        context = RequestContext(message="交通方便吗")
        result = await rule_strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_transport_with_plane_keyword(self, rule_strategy):
        """Should classify transport intent with keyword '飞机'."""
        context = RequestContext(message="坐飞机去")
        result = await rule_strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_transport_with_high_speed_rail(self, rule_strategy):
        """Should classify transport intent with keyword '高铁'."""
        context = RequestContext(message="高铁票")
        result = await rule_strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_transport_with_driving_keyword(self, rule_strategy):
        """Should classify transport intent with keyword '开车'."""
        context = RequestContext(message="开车去")
        result = await rule_strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_transport_with_self_drive(self, rule_strategy):
        """Should classify transport intent with keyword '自驾'."""
        context = RequestContext(message="自驾游")
        result = await rule_strategy.classify(context)
        assert result.intent == "transport"

    @pytest.mark.asyncio
    async def test_transport_with_pattern(self, rule_strategy):
        """Should match transport patterns like '如何去上海'."""
        context = RequestContext(message="如何去上海")
        result = await rule_strategy.classify(context)
        assert result.intent == "transport"


class TestConfidenceCapping:
    """Test confidence capping behavior."""

    @pytest.mark.asyncio
    async def test_max_confidence_capped(self, rule_strategy):
        """Confidence should never exceed max_confidence."""
        # Message with multiple high-weight keywords
        context = RequestContext(message="规划行程旅游路线")
        result = await rule_strategy.classify(context)
        assert result.confidence <= 0.9

    @pytest.mark.asyncio
    async def test_no_matches_returns_low_confidence(self, rule_strategy):
        """Messages with no matches should return low confidence chat."""
        context = RequestContext(message="xyz123")
        result = await rule_strategy.classify(context)
        assert result.intent == "chat"
        assert result.confidence < 0.2


class TestTieBreaking:
    """Test behavior when multiple intents have similar scores."""

    @pytest.mark.asyncio
    async def test_tie_breaking_by_first_max(self, rule_strategy):
        """When scores tie, first max should win (implementation dependent)."""
        # Message that might match multiple intents
        context = RequestContext(message="怎么去北京")  # Could be transport or query
        result = await rule_strategy.classify(context)
        # Should be either transport or query with reasonable confidence
        assert result.intent in ["transport", "query"]
        assert result.confidence > 0.1
