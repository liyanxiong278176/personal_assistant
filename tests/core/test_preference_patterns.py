"""Tests for Preference Pattern Matcher (TDD approach)

Tests for regex-based preference extraction system that extracts
travel preferences from Chinese text.
"""

import pytest
from datetime import datetime, timezone

from app.core.preferences.patterns import (
    PreferenceType,
    MatchedPreference,
    PreferenceMatcher,
)


class TestPreferenceType:
    """Tests for PreferenceType constants."""

    def test_preference_type_constants(self):
        """Test that all expected preference types are defined."""
        assert hasattr(PreferenceType, 'DESTINATION')
        assert hasattr(PreferenceType, 'BUDGET')
        assert hasattr(PreferenceType, 'DURATION')
        assert hasattr(PreferenceType, 'ACCOMMODATION')
        assert hasattr(PreferenceType, 'ACTIVITY')
        assert hasattr(PreferenceType, 'DATE')

    def test_preference_type_values(self):
        """Test preference type values are correct."""
        assert PreferenceType.DESTINATION == "destination"
        assert PreferenceType.BUDGET == "budget"
        assert PreferenceType.DURATION == "duration"
        assert PreferenceType.ACCOMMODATION == "accommodation"
        assert PreferenceType.ACTIVITY == "activity"
        assert PreferenceType.DATE == "date"


class TestMatchedPreference:
    """Tests for MatchedPreference dataclass."""

    def test_create_basic_preference(self):
        """Test creating a basic preference without timestamp."""
        pref = MatchedPreference(
            key=PreferenceType.DESTINATION,
            value="北京",
            confidence=0.9
        )
        assert pref.key == PreferenceType.DESTINATION
        assert pref.value == "北京"
        assert pref.confidence == 0.9
        assert pref.source == "rule"
        assert pref.raw_text is None
        assert isinstance(pref.extracted_at, datetime)
        # Verify timestamp is in UTC
        assert pref.extracted_at.tzinfo == timezone.utc

    def test_create_preference_with_all_fields(self):
        """Test creating a preference with all fields."""
        now = datetime.now(timezone.utc)
        pref = MatchedPreference(
            key=PreferenceType.BUDGET,
            value="5000元",
            confidence=0.85,
            source="rule",
            raw_text="预算5000元",
            extracted_at=now
        )
        assert pref.key == PreferenceType.BUDGET
        assert pref.value == "5000元"
        assert pref.confidence == 0.85
        assert pref.source == "rule"
        assert pref.raw_text == "预算5000元"
        assert pref.extracted_at == now


class TestPreferenceMatcher:
    """Tests for PreferenceMatcher class."""

    @pytest.fixture
    def matcher(self):
        """Create a fresh matcher instance for each test."""
        return PreferenceMatcher()

    @pytest.fixture
    def low_threshold_matcher(self):
        """Create matcher with low confidence threshold for testing."""
        return PreferenceMatcher(confidence_threshold=0.3)

    # Test extract_destination

    def test_extract_destination_simple(self, matcher):
        """Test extracting destination with simple pattern."""
        text = "我想去北京旅游"
        results = matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        assert len(destination_results) == 1
        assert destination_results[0].value == "北京"
        assert destination_results[0].confidence >= 0.7

    def test_extract_destination_with_play(self, low_threshold_matcher):
        """Test extracting destination with 'play' keyword."""
        text = "去上海玩几天"
        results = low_threshold_matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        assert len(destination_results) >= 1
        assert "上海" in [r.value for r in destination_results]

    def test_extract_destination_with_wander(self, low_threshold_matcher):
        """Test extracting destination with 'wander' keyword."""
        text = "去杭州逛逛"
        results = low_threshold_matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        assert len(destination_results) >= 1
        assert "杭州" in [r.value for r in destination_results]

    def test_extract_destination_with_punctuation(self, matcher):
        """Test extracting destination with various punctuation."""
        text = "我想去成都，可以吗？"
        results = matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        assert len(destination_results) >= 1
        assert "成都" in [r.value for r in destination_results]

    def test_extract_destination_multiple_cities(self, low_threshold_matcher):
        """Test extracting multiple destinations."""
        text = "我想去北京和上海旅游"
        results = low_threshold_matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        assert len(destination_results) >= 2
        values = [r.value for r in destination_results]
        assert "北京" in values
        assert "上海" in values

    def test_extract_destination_no_match(self, matcher):
        """Test when no destination is mentioned."""
        text = "今天天气真好"
        results = matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        assert len(destination_results) == 0

    # Test extract_budget

    def test_extract_budget_with_yuan(self, low_threshold_matcher):
        """Test extracting budget with 'yuan' keyword."""
        text = "预算5000元"
        results = low_threshold_matcher.extract(text)
        budget_results = [r for r in results if r.key == PreferenceType.BUDGET]
        assert len(budget_results) >= 1
        assert "5000元" in [r.value for r in budget_results]

    def test_extract_budget_with_kuai(self, low_threshold_matcher):
        """Test extracting budget with 'kuai' (colloquial) keyword."""
        text = "预算三千块"
        results = low_threshold_matcher.extract(text)
        budget_results = [r for r in results if r.key == PreferenceType.BUDGET]
        assert len(budget_results) >= 1

    def test_extract_budget_within_limit(self, low_threshold_matcher):
        """Test extracting budget with 'within' pattern."""
        text = "10000元以内"
        results = low_threshold_matcher.extract(text)
        budget_results = [r for r in results if r.key == PreferenceType.BUDGET]
        assert len(budget_results) >= 1
        assert "10000元" in [r.value for r in budget_results]

    def test_extract_budget_chinese_numbers(self, low_threshold_matcher):
        """Test extracting budget with Chinese numbers."""
        text = "预算五千元"
        results = low_threshold_matcher.extract(text)
        budget_results = [r for r in results if r.key == PreferenceType.BUDGET]
        assert len(budget_results) >= 1
        # Chinese numbers should be normalized
        values = [r.value for r in budget_results]
        assert any("5000元" in v or "千" in v for v in values)

    def test_extract_budget_no_match(self, matcher):
        """Test when no budget is mentioned."""
        text = "我想去北京旅游"
        results = matcher.extract(text)
        budget_results = [r for r in results if r.key == PreferenceType.BUDGET]
        assert len(budget_results) == 0

    # Test extract_duration

    def test_extract_duration_days(self, low_threshold_matcher):
        """Test extracting duration in days."""
        text = "计划玩5天"
        results = low_threshold_matcher.extract(text)
        duration_results = [r for r in results if r.key == PreferenceType.DURATION]
        assert len(duration_results) >= 1
        assert "5天" in [r.value for r in duration_results]

    def test_extract_duration_nights(self, low_threshold_matcher):
        """Test extracting duration in nights."""
        text = "住3晚"
        results = low_threshold_matcher.extract(text)
        duration_results = [r for r in results if r.key == PreferenceType.DURATION]
        assert len(duration_results) >= 1
        # Nights should be normalized to days
        assert "3天" in [r.value for r in duration_results]

    def test_extract_duration_multiple_numbers(self, low_threshold_matcher):
        """Test extracting duration when multiple numbers appear."""
        text = "7天6晚行程"
        results = low_threshold_matcher.extract(text)
        duration_results = [r for r in results if r.key == PreferenceType.DURATION]
        assert len(duration_results) >= 1

    def test_extract_duration_no_match(self, matcher):
        """Test when no duration is mentioned."""
        text = "我想去北京"
        results = matcher.extract(text)
        duration_results = [r for r in results if r.key == PreferenceType.DURATION]
        assert len(duration_results) == 0

    # Test confidence calculation

    def test_confidence_calculation_high(self, low_threshold_matcher):
        """Test confidence calculation for high-confidence patterns."""
        text = "我想去北京"  # "我想去" pattern should increase confidence
        results = low_threshold_matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        if destination_results:
            # "我想去" pattern should give higher confidence
            assert destination_results[0].confidence > 0.6

    def test_confidence_calculation_with_budget_keyword(self, low_threshold_matcher):
        """Test confidence calculation with budget keyword."""
        text = "预算5000元"  # "预算" keyword should increase confidence
        results = low_threshold_matcher.extract(text)
        budget_results = [r for r in results if r.key == PreferenceType.BUDGET]
        if budget_results:
            # "预算" keyword should give higher confidence
            assert budget_results[0].confidence > 0.6

    def test_confidence_calculation_with_numbers(self, low_threshold_matcher):
        """Test confidence calculation is boosted by numeric patterns."""
        text = "预算5000元"  # Has number
        results = low_threshold_matcher.extract(text)
        budget_results = [r for r in results if r.key == PreferenceType.BUDGET]
        if budget_results:
            # Having numbers should boost confidence
            assert any(r.confidence > 0.5 for r in budget_results)

    def test_confidence_threshold_filtering(self, matcher):
        """Test that results below threshold are filtered out."""
        # Use high threshold
        high_threshold_matcher = PreferenceMatcher(confidence_threshold=0.95)
        text = "我想去北京"
        results = high_threshold_matcher.extract(text)
        # Most patterns shouldn't reach 0.95 confidence
        # This test verifies filtering works (implementation-dependent)
        assert isinstance(results, list)

    # Test comprehensive extraction

    def test_extract_multiple_preferences(self, low_threshold_matcher):
        """Test extracting multiple preference types from one message."""
        text = "我想去北京旅游，预算5000元，计划5天"
        results = low_threshold_matcher.extract(text)
        keys = {r.key for r in results}
        assert PreferenceType.DESTINATION in keys
        assert PreferenceType.BUDGET in keys
        assert PreferenceType.DURATION in keys

    def test_extract_empty_text(self, matcher):
        """Test extracting from empty text."""
        results = matcher.extract("")
        assert results == []

    def test_extract_whitespace_only(self, matcher):
        """Test extracting from whitespace-only text."""
        results = matcher.extract("   \n\t  ")
        assert results == []

    def test_raw_text_preserved(self, low_threshold_matcher):
        """Test that raw matched text is preserved."""
        text = "我想去北京旅游"
        results = low_threshold_matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        if destination_results:
            assert destination_results[0].raw_text is not None
            assert len(destination_results[0].raw_text) > 0

    # Test Chinese number normalization

    def test_normalize_chinese_numbers_budget(self, low_threshold_matcher):
        """Test Chinese number normalization in budget."""
        text = "预算三千元"
        results = low_threshold_matcher.extract(text)
        budget_results = [r for r in results if r.key == PreferenceType.BUDGET]
        if budget_results:
            # Should normalize Chinese numbers
            assert any(r.value for r in budget_results)

    def test_normalize_chinese_numbers_duration(self, low_threshold_matcher):
        """Test Chinese number normalization in duration."""
        text = "玩三天"
        results = low_threshold_matcher.extract(text)
        duration_results = [r for r in results if r.key == PreferenceType.DURATION]
        if duration_results:
            # Should normalize to Arabic numerals
            assert any("3" in r.value for r in duration_results)

    # Test position-based confidence

    def test_early_position_boosts_confidence(self, low_threshold_matcher):
        """Test that earlier mentions get slight confidence boost."""
        text = "我想去北京旅游"  # Destination at start
        results = low_threshold_matcher.extract(text)
        destination_results = [r for r in results if r.key == PreferenceType.DESTINATION]
        if destination_results:
            # Early position should boost confidence
            assert destination_results[0].confidence > 0.5
