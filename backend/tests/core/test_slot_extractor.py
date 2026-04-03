"""Tests for slot_extractor module"""

import pytest
from datetime import date
from app.core.intent.slot_extractor import SlotResult, DateRange, SlotExtractor


def test_slot_result_empty():
    """空槽位结果"""
    result = SlotResult()
    assert result.destination is None
    assert result.start_date is None
    assert not result.has_required_slots


def test_slot_result_with_destination():
    """有目的地无日期"""
    result = SlotResult(destination="北京")
    assert result.destination == "北京"
    assert not result.has_required_slots  # 需要日期


def test_slot_result_complete():
    """完整槽位"""
    result = SlotResult(
        destination="北京",
        start_date="2026-05-01",
        end_date="2026-05-03"
    )
    assert result.has_required_slots
    assert result.num_days == 3


def test_extract_destination_with_keyword():
    """测试: 带关键词的目的地提取"""
    extractor = SlotExtractor()
    result = extractor.extract("帮我规划北京三日游")
    assert result.destination == "北京"


def test_extract_destination_common_cities():
    """测试: 常见城市名提取"""
    extractor = SlotExtractor()

    test_cases = [
        ("去上海旅游", "上海"),
        ("杭州有什么好玩的", "杭州"),
        ("规划成都行程", "成都"),
    ]
    for msg, expected in test_cases:
        result = extractor.extract(msg)
        assert result.destination == expected, f"Failed for: {msg}"


def test_extract_destination_none():
    """测试: 无目的地"""
    extractor = SlotExtractor()
    result = extractor.extract("你好在吗")
    assert result.destination is None


def test_extract_date_holidays():
    """测试: 节假日日期"""
    extractor = SlotExtractor()

    # 五一 (2026年5月1日-5日，共5天)
    result = extractor.extract("五一去北京旅游")
    assert result.start_date == "2026-05-01"
    assert result.end_date == "2026-05-05"
    assert result.num_days == 5

    # 国节 (2026年10月1日-7日，共7天)
    result = extractor.extract("国庆期间去上海")
    assert result.start_date == "2026-10-01"
    assert result.end_date == "2026-10-07"


def test_extract_date_month_day():
    """测试: 月日格式"""
    # 使用固定日期确保测试一致性（3月1日，3月15日未到）
    extractor = SlotExtractor(current_date=date(2026, 3, 1))

    result = extractor.extract("3月15日去杭州")
    assert result.start_date == "2026-03-15"
    assert result.end_date == "2026-03-15"


def test_extract_date_range():
    """测试: 日期范围"""
    extractor = SlotExtractor()

    result = extractor.extract("4月5日到4月10日去成都")
    assert result.start_date == "2026-04-05"
    assert result.end_date == "2026-04-10"
    assert result.num_days == 6


def test_extract_travelers():
    """测试: 提取出行人数"""
    extractor = SlotExtractor()

    result = extractor.extract("我们3个人去北京")
    assert result.travelers == 3

    result = extractor.extract("2人去上海旅游")
    assert result.travelers == 2


def test_extract_complete_query():
    """测试: 完整查询提取"""
    extractor = SlotExtractor()

    result = extractor.extract("五一期间我们4个人去北京旅游")
    assert result.destination == "北京"
    assert result.start_date == "2026-05-01"
    assert result.end_date == "2026-05-05"
    assert result.travelers == 4
    assert result.has_required_slots


def test_slot_result_with_interests():
    """测试: 兴趣标签"""
    result = SlotResult(
        destination="北京",
        start_date="2026-05-01",
        interests=["历史", "美食"]
    )
    assert result.interests == ["历史", "美食"]


def test_slot_result_with_budget():
    """测试: 预算等级"""
    result = SlotResult(
        destination="北京",
        start_date="2026-05-01",
        budget="medium"
    )
    assert result.budget == "medium"


def test_extract_with_fixed_date():
    """测试: 使用固定日期初始化"""
    extractor = SlotExtractor(current_date=date(2026, 4, 1))

    result = extractor.extract("3月15日去杭州")
    # 3月15日已过，应该使用明年
    assert result.start_date == "2027-03-15"


def test_date_range_num_days():
    """测试: DateRange 天数计算"""
    date_range = DateRange(start_date="2026-05-01", end_date="2026-05-03")
    assert date_range.num_days == 3

    date_range = DateRange(start_date="2026-05-01", end_date="2026-05-01")
    assert date_range.num_days == 1
