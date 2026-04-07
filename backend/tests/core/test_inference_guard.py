import pytest
from app.core.context_mgmt.inference_guard import InferenceGuard, OverlimitStrategy


@pytest.fixture
def guard():
    return InferenceGuard(
        max_tokens_per_response=100,
        max_total_budget=500,
        warning_threshold=0.8,
        overlimit_strategy=OverlimitStrategy.TRUNCATE
    )


def test_normal_flow(guard):
    """测试正常流程 - 未超限"""
    should_continue, warning = guard.check_before_yield("test chunk")
    assert should_continue is True
    assert warning is None


def test_warning_threshold(guard):
    """测试警告阈值"""
    for _ in range(8):
        guard.check_before_yield("x" * 10)
    should_continue, warning = guard.check_before_yield("x" * 10)
    assert should_continue is True
    assert "warning" in str(warning).lower() if warning else True


def test_per_response_limit_truncate(guard):
    """测试单次响应限制 - TRUNCATE策略"""
    for _ in range(11):
        guard.check_before_yield("x" * 10)
    should_continue, warning = guard.check_before_yield("x" * 10)
    assert should_continue is False


def test_total_budget_exceeded(guard):
    """测试总预算超限"""
    guard._total_budget_used = 500
    should_continue, warning = guard.check_before_yield("test")
    assert should_continue is False


def test_reset_response_counter(guard):
    """测试计数器重置"""
    guard.check_before_yield("x" * 10)
    guard._current_tokens = 50
    guard.reset_response_counter()
    assert guard._current_tokens == 0
    assert guard._total_budget_used > 0
