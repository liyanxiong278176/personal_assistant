import pytest
from app.core.intent.complexity import is_complex_query, ComplexityResult

def test_simple_query_not_complex():
    result = is_complex_query("你好")
    assert result.is_complex is False, f"Expected simple query, score={result.score}"

def test_long_query_is_complex():
    result = is_complex_query("帮我规划" + "玩" * 30)
    assert result.is_complex

def test_multiple_slots_is_complex():
    from dataclasses import dataclass
    @dataclass
    class Slots:
        destination: str
        duration: str
        budget: str
        people: str

    result = is_complex_query(
        "规划云南7天自驾游，预算5000元，3个人",
        extract_slots=lambda msg: Slots(
            destination="云南",
            duration="7天",
            budget="5000元",
            people="3"
        )
    )
    assert result.is_complex
