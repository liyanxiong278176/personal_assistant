import pytest
import asyncio
from app.core.session.retry_manager import RetryManager, RetryPolicy
from app.core.session.error_classifier import ErrorClassifier


@pytest.mark.asyncio
async def test_transient_error_retry():
    classifier = ErrorClassifier()
    manager = RetryManager(classifier)
    conv_id = "test-conv"

    error = TimeoutError("Timeout")

    # 第一次：允许重试
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is True
    assert count == 1

    # 第二次：允许重试
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is True
    assert count == 2

    # 第三次：允许重试
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is True
    assert count == 3

    # 第四次：超过最大重试次数
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is False
    assert count == 3


@pytest.mark.asyncio
async def test_validation_error_no_retry():
    classifier = ErrorClassifier()
    manager = RetryManager(classifier)
    conv_id = "test-conv"

    error = ValueError("Invalid")

    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is False  # VALIDATION 错误不重试
    assert count == 0


@pytest.mark.asyncio
async def test_backoff_delay():
    classifier = ErrorClassifier()
    policy = RetryPolicy(backoff_base=0.01, backoff_max=0.05)
    manager = RetryManager(classifier, policy)

    start = asyncio.get_event_loop().time()
    await manager.apply_backoff(2)
    elapsed = asyncio.get_event_loop().time() - start

    # 2^1 * 0.01 = 0.02s (allowing for scheduling overhead)
    assert 0.015 < elapsed < 0.05


def test_reset():
    classifier = ErrorClassifier()
    manager = RetryManager(classifier)
    conv_id = "test-conv"

    error = TimeoutError("Timeout")
    manager.should_retry(conv_id, error)
    assert manager.get_retry_count(conv_id) == 1

    manager.reset(conv_id)
    assert manager.get_retry_count(conv_id) == 0
