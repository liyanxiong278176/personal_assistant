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
        """Hotel keywords should be defined with correct weights."""
        assert "酒店" in HOTEL_KEYWORDS
        assert "住宿" in HOTEL_KEYWORDS
        # Updated weights from YAML config (0.6 for strong indicators)
        assert HOTEL_KEYWORDS["酒店"] == 0.6

    def test_food_keywords_defined(self):
        """Food keywords should be defined with correct weights."""
        assert "美食" in FOOD_KEYWORDS
        assert "小吃" in FOOD_KEYWORDS
        # Updated weights from YAML config (0.65 for strong indicators)
        assert FOOD_KEYWORDS["美食"] == 0.65

    def test_budget_keywords_defined(self):
        """Budget keywords should be defined with correct weights."""
        assert "预算" in BUDGET_KEYWORDS
        assert "多少钱" in BUDGET_KEYWORDS
        # Updated weights from YAML config (0.65 for strong indicators)
        assert BUDGET_KEYWORDS["预算"] == 0.65

    def test_transport_keywords_defined(self):
        """Transport keywords should be defined with correct weights."""
        assert "怎么去" in TRANSPORT_KEYWORDS
        assert "交通" in TRANSPORT_KEYWORDS
        # Updated weights from YAML config (0.45 for "怎么去", 0.65 for "交通")
        assert TRANSPORT_KEYWORDS["怎么去"] == 0.45
        assert TRANSPORT_KEYWORDS["交通"] == 0.65

    def test_all_intent_patterns_has_correct_intents(self):
        """Should have patterns for 7 intent types (including chat)."""
        assert len(ALL_INTENT_PATTERNS) == 7
        assert "hotel" in ALL_INTENT_PATTERNS
        assert "food" in ALL_INTENT_PATTERNS
        assert "budget" in ALL_INTENT_PATTERNS
        assert "transport" in ALL_INTENT_PATTERNS
        assert "chat" in ALL_INTENT_PATTERNS  # Added in new config

    def test_keyword_weights_in_valid_range(self):
        """All keyword weights should be in valid range (positive: 0.1-0.7, negative: -0.1 to -0.5)."""
        # Updated weight range to accommodate:
        # - Positive weights (0.1-0.7) for keyword matches
        # - Negative weights (-0.1 to -0.5) for exclusion rules
        for intent, keywords in ALL_INTENT_KEYWORDS.items():
            for keyword, weight in keywords.items():
                if weight > 0:
                    assert 0.1 <= weight <= 0.7, (
                        f"{intent}.{keyword} has invalid positive weight: {weight}"
                    )
                else:
                    assert -0.5 <= weight <= -0.1, (
                        f"{intent}.{keyword} has invalid negative weight: {weight}"
                    )
