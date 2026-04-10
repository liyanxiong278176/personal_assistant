# tests/core/intent/test_keywords.py
import pytest
from app.core.intent.keywords import (
    ALL_INTENT_KEYWORDS,
    ALL_INTENT_PATTERNS,
    HOTEL_KEYWORDS,
    FOOD_KEYWORDS,
    BUDGET_KEYWORDS,
    TRANSPORT_KEYWORDS,
)


class TestKeywordsModule:
    """Test keywords module structure and content."""

    def test_all_intent_keywords_has_8_intents(self):
        """Should have 8 intent types defined."""
        assert len(ALL_INTENT_KEYWORDS) == 8
        expected_intents = {
            "itinerary", "query", "chat", "image",
            "hotel", "food", "budget", "transport"
        }
        assert set(ALL_INTENT_KEYWORDS.keys()) == expected_intents

    def test_hotel_keywords_defined(self):
        """Hotel keywords should be defined."""
        assert "酒店" in HOTEL_KEYWORDS
        assert "住宿" in HOTEL_KEYWORDS
        assert HOTEL_KEYWORDS["酒店"] == 0.3

    def test_food_keywords_defined(self):
        """Food keywords should be defined."""
        assert "美食" in FOOD_KEYWORDS
        assert "小吃" in FOOD_KEYWORDS
        assert FOOD_KEYWORDS["美食"] == 0.3

    def test_budget_keywords_defined(self):
        """Budget keywords should be defined."""
        assert "预算" in BUDGET_KEYWORDS
        assert "多少钱" in BUDGET_KEYWORDS
        assert BUDGET_KEYWORDS["预算"] == 0.3

    def test_transport_keywords_defined(self):
        """Transport keywords should be defined."""
        assert "怎么去" in TRANSPORT_KEYWORDS
        assert "交通" in TRANSPORT_KEYWORDS
        assert TRANSPORT_KEYWORDS["怎么去"] == 0.3

    def test_all_intent_patterns_has_correct_intents(self):
        """Should have patterns for 6 intent types."""
        assert len(ALL_INTENT_PATTERNS) == 6
        assert "hotel" in ALL_INTENT_PATTERNS
        assert "food" in ALL_INTENT_PATTERNS
        assert "budget" in ALL_INTENT_PATTERNS
        assert "transport" in ALL_INTENT_PATTERNS

    def test_keyword_weights_in_valid_range(self):
        """All keyword weights should be between 0.1 and 0.3."""
        for intent, keywords in ALL_INTENT_KEYWORDS.items():
            for keyword, weight in keywords.items():
                assert 0.1 <= weight <= 0.3, (
                    f"{intent}.{keyword} has invalid weight: {weight}"
                )
