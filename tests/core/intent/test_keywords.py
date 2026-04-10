"""Tests for Intent Keywords Module.

Tests the centralized keyword definitions and intent patterns
for all 8 intent types.
"""

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
    """Test suite for the centralized keywords module."""

    def test_all_intent_keywords_has_8_intents(self):
        """Test that ALL_INTENT_KEYWORDS contains exactly 8 intent types."""
        expected_intents = {
            "itinerary",
            "query",
            "chat",
            "image",
            "hotel",
            "food",
            "budget",
            "transport",
        }
        actual_intents = set(ALL_INTENT_KEYWORDS.keys())
        assert actual_intents == expected_intents, (
            f"Expected 8 intent types {expected_intents}, "
            f"got {actual_intents}"
        )

    def test_hotel_keywords_defined(self):
        """Test that hotel keywords are defined with expected entries."""
        assert "酒店" in HOTEL_KEYWORDS, "Missing keyword: 酒店"
        assert "住宿" in HOTEL_KEYWORDS, "Missing keyword: 住宿"
        # Verify they have valid weights
        assert isinstance(HOTEL_KEYWORDS["酒店"], (int, float))
        assert isinstance(HOTEL_KEYWORDS["住宿"], (int, float))

    def test_food_keywords_defined(self):
        """Test that food keywords are defined with expected entries."""
        assert "美食" in FOOD_KEYWORDS, "Missing keyword: 美食"
        assert "小吃" in FOOD_KEYWORDS, "Missing keyword: 小吃"
        # Verify they have valid weights
        assert isinstance(FOOD_KEYWORDS["美食"], (int, float))
        assert isinstance(FOOD_KEYWORDS["小吃"], (int, float))

    def test_budget_keywords_defined(self):
        """Test that budget keywords are defined with expected entries."""
        assert "预算" in BUDGET_KEYWORDS, "Missing keyword: 预算"
        assert "多少钱" in BUDGET_KEYWORDS, "Missing keyword: 多少钱"
        # Verify they have valid weights
        assert isinstance(BUDGET_KEYWORDS["预算"], (int, float))
        assert isinstance(BUDGET_KEYWORDS["多少钱"], (int, float))

    def test_transport_keywords_defined(self):
        """Test that transport keywords are defined with expected entries."""
        assert "怎么去" in TRANSPORT_KEYWORDS, "Missing keyword: 怎么去"
        assert "交通" in TRANSPORT_KEYWORDS, "Missing keyword: 交通"
        # Verify they have valid weights
        assert isinstance(TRANSPORT_KEYWORDS["怎么去"], (int, float))
        assert isinstance(TRANSPORT_KEYWORDS["交通"], (int, float))

    def test_all_intent_patterns_has_correct_intents(self):
        """Test that ALL_INTENT_PATTERNS contains patterns for 6 intent types."""
        expected_pattern_intents = {
            "itinerary",
            "query",
            "hotel",
            "food",
            "budget",
            "transport",
        }
        actual_pattern_intents = set(ALL_INTENT_PATTERNS.keys())
        assert actual_pattern_intents == expected_pattern_intents, (
            f"Expected patterns for {expected_pattern_intents}, "
            f"got {actual_pattern_intents}"
        )
        # Verify each pattern list is non-empty
        for intent, patterns in ALL_INTENT_PATTERNS.items():
            assert isinstance(patterns, list), f"Patterns for {intent} should be a list"
            assert len(patterns) > 0, f"Patterns for {intent} should not be empty"

    def test_keyword_weights_in_valid_range(self):
        """Test that all keyword weights are between 0.1 and 0.3 (inclusive)."""
        invalid_weights = []
        for intent_name, keywords in ALL_INTENT_KEYWORDS.items():
            for keyword, weight in keywords.items():
                if not (0.1 <= weight <= 0.3):
                    invalid_weights.append(
                        f"intent={intent_name}, keyword={keyword}, weight={weight}"
                    )
        assert not invalid_weights, (
            f"Found keyword weights outside valid range [0.1, 0.3]: {invalid_weights}"
        )
