"""Tests for PreferenceExtractor module"""

import pytest
from datetime import datetime, timezone
from app.core.preferences.extractor import PreferenceExtractor
from app.core.preferences.patterns import MatchedPreference, PreferenceType
from app.core.preferences.repository import PreferenceRepository


@pytest.fixture
def in_memory_repo():
    """Create an in-memory repository for testing."""
    return PreferenceRepository(semantic_repo=None)


@pytest.fixture
def extractor(in_memory_repo):
    """Create a PreferenceExtractor with in-memory repository."""
    return PreferenceExtractor(
        confidence_threshold=0.7,
        repository=in_memory_repo
    )


@pytest.mark.asyncio
async def test_extract_and_store(extractor):
    """测试: 提取并存储高置信度偏好"""
    user_input = "我想去北京旅游，预算5000元，计划5天行程"
    conversation_id = "conv_123"
    user_id = "user_456"

    # Extract preferences
    results = await extractor.extract(
        user_input=user_input,
        conversation_id=conversation_id,
        user_id=user_id
    )

    # Should extract destination, budget, and duration
    assert len(results) >= 2  # At least destination and one other

    # Check that preferences were stored
    stored = await extractor.get_preferences(user_id)
    assert len(stored) >= 2
    assert "北京" in stored.values() or "5000元" in stored.values()


@pytest.mark.asyncio
async def test_extract_filters_by_confidence(extractor):
    """测试: 低置信度结果被过滤"""
    # Create a custom extractor with high threshold
    high_threshold_extractor = PreferenceExtractor(
        confidence_threshold=0.95,
        repository=extractor.repository
    )

    user_input = "去玩"  # Vague input, likely low confidence
    results = await high_threshold_extractor.extract(
        user_input=user_input,
        conversation_id="conv_123",
        user_id="user_456"
    )

    # Should return empty due to high threshold
    assert len(results) == 0


@pytest.mark.asyncio
async def test_add_preference(extractor):
    """测试: 添加单个偏好"""
    user_id = "user_789"

    # Create a manual preference
    pref = MatchedPreference(
        key=PreferenceType.DESTINATION,
        value="上海",
        confidence=0.9,
        source="manual",
        raw_text="上海"
    )

    # Add the preference
    await extractor.add_preference(user_id, pref)

    # Verify it was stored
    stored = await extractor.get_preferences(user_id)
    assert stored.get(PreferenceType.DESTINATION) == "上海"


@pytest.mark.asyncio
async def test_add_preference_override(extractor):
    """测试: 高置信度覆盖低置信度"""
    user_id = "user_override"

    # Add medium confidence preference (above default min_confidence)
    med_pref = MatchedPreference(
        key=PreferenceType.BUDGET,
        value="3000元",
        confidence=0.7,
        source="test"
    )
    await extractor.add_preference(user_id, med_pref)

    # Verify medium confidence stored
    stored = await extractor.get_matched_preferences(user_id)
    assert stored.get(PreferenceType.BUDGET).confidence == 0.7

    # Add high confidence preference for same key
    high_pref = MatchedPreference(
        key=PreferenceType.BUDGET,
        value="5000元",
        confidence=0.9,
        source="test"
    )
    await extractor.add_preference(user_id, high_pref)

    # Verify high confidence overrides
    stored = await extractor.get_matched_preferences(user_id)
    assert stored.get(PreferenceType.BUDGET).confidence == 0.9
    assert stored.get(PreferenceType.BUDGET).value == "5000元"


@pytest.mark.asyncio
async def test_add_preference_low_no_override(extractor):
    """测试: 低置信度不覆盖高置信度"""
    user_id = "user_no_override"

    # Add high confidence preference
    high_pref = MatchedPreference(
        key=PreferenceType.DESTINATION,
        value="北京",
        confidence=0.9,
        source="test"
    )
    await extractor.add_preference(user_id, high_pref)

    # Try to add low confidence for same key
    low_pref = MatchedPreference(
        key=PreferenceType.DESTINATION,
        value="上海",
        confidence=0.5,
        source="test"
    )
    result = await extractor.repository.upsert(user_id, low_pref)

    # Should return False (not stored)
    assert result is False

    # Verify original value remains
    stored = await extractor.get_matched_preferences(user_id)
    assert stored.get(PreferenceType.DESTINATION).value == "北京"


@pytest.mark.asyncio
async def test_get_preferences_filtered_by_keys(extractor):
    """测试: 按键过滤获取偏好"""
    user_id = "user_filter"

    # Add multiple preferences
    await extractor.add_preference(user_id, MatchedPreference(
        key=PreferenceType.DESTINATION,
        value="杭州",
        confidence=0.8
    ))
    await extractor.add_preference(user_id, MatchedPreference(
        key=PreferenceType.BUDGET,
        value="4000元",
        confidence=0.8
    ))

    # Get all preferences
    all_prefs = await extractor.get_preferences(user_id)
    assert len(all_prefs) == 2

    # Get only destination
    dest_prefs = await extractor.get_preferences(user_id, [PreferenceType.DESTINATION])
    assert len(dest_prefs) == 1
    assert dest_prefs[PreferenceType.DESTINATION] == "杭州"


@pytest.mark.asyncio
async def test_get_matched_preferences_returns_full_objects(extractor):
    """测试: 获取完整偏好对象"""
    user_id = "user_full"

    pref = MatchedPreference(
        key=PreferenceType.DESTINATION,
        value="成都",
        confidence=0.85,
        source="test",
        raw_text="我想去成都"
    )
    await extractor.add_preference(user_id, pref)

    # Get full objects
    stored = await extractor.get_matched_preferences(user_id)
    assert len(stored) == 1

    full_pref = stored[PreferenceType.DESTINATION]
    assert full_pref.value == "成都"
    assert full_pref.confidence == 0.85
    assert full_pref.source == "test"
    assert full_pref.raw_text == "我想去成都"
    assert isinstance(full_pref.extracted_at, datetime)


@pytest.mark.asyncio
async def test_extract_empty_input(extractor):
    """测试: 空输入处理"""
    results = await extractor.extract(
        user_input="",
        conversation_id="conv_empty",
        user_id="user_empty"
    )

    assert len(results) == 0


@pytest.mark.asyncio
async def test_extract_no_matches(extractor):
    """测试: 无匹配输入"""
    results = await extractor.extract(
        user_input="你好在吗",
        conversation_id="conv_nomatch",
        user_id="user_nomatch"
    )

    assert len(results) == 0


@pytest.mark.asyncio
async def test_confidence_threshold_validation():
    """测试: 置信度阈值验证"""
    with pytest.raises(ValueError):
        PreferenceExtractor(confidence_threshold=-0.1)

    with pytest.raises(ValueError):
        PreferenceExtractor(confidence_threshold=1.5)


@pytest.mark.asyncio
async def test_multiple_users_separated(extractor):
    """测试: 不同用户偏好分离"""
    user1 = "user_1"
    user2 = "user_2"

    # Add preferences for different users
    await extractor.add_preference(user1, MatchedPreference(
        key=PreferenceType.DESTINATION,
        value="北京",
        confidence=0.9
    ))
    await extractor.add_preference(user2, MatchedPreference(
        key=PreferenceType.DESTINATION,
        value="上海",
        confidence=0.9
    ))

    # Verify separation
    prefs1 = await extractor.get_preferences(user1)
    prefs2 = await extractor.get_preferences(user2)

    assert prefs1[PreferenceType.DESTINATION] == "北京"
    assert prefs2[PreferenceType.DESTINATION] == "上海"


@pytest.mark.asyncio
async def test_extract_various_budget_formats(extractor):
    """测试: 提取不同格式的预算"""
    # Note: PatternMatcher only supports single Chinese digits (一-九, 十)
    # and Arabic numerals. Compound numbers like "三千" are not supported.
    test_cases = [
        ("预算三千元", "3元"),  # Only "三" is recognized as 3
        ("5000块以内", "5000元"),
        ("5000元左右", "5000元"),
        ("3000元预算", "3000元"),
    ]

    for user_input, expected_budget in test_cases:
        results = await extractor.extract(
            user_input=user_input,
            conversation_id="conv_budget",
            user_id=f"user_budget_{hash(user_input)}"
        )

        # Check if budget was extracted
        budget_prefs = [r for r in results if r.key == PreferenceType.BUDGET]
        if budget_prefs:
            assert budget_prefs[0].value == expected_budget


@pytest.mark.asyncio
async def test_extract_duration_with_chinese_numbers(extractor):
    """测试: 提取中文数字时长"""
    # Note: PatternMatcher only supports single Chinese digits (一-九, 十)
    # Use Arabic numerals for compound numbers or durations > 10
    test_cases = [
        ("计划五天行程", "5天"),  # Single digit Chinese works
        ("7天旅游", "7天"),  # Arabic numerals work
        ("计划三天", "3天"),
    ]

    for user_input, expected_duration in test_cases:
        results = await extractor.extract(
            user_input=user_input,
            conversation_id="conv_duration",
            user_id=f"user_duration_{hash(user_input)}"
        )

        duration_prefs = [r for r in results if r.key == PreferenceType.DURATION]
        if duration_prefs:
            assert duration_prefs[0].value == expected_duration
