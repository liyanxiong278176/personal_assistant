import pytest
from app.core.session.error_classifier import ErrorClassifier, ErrorClassification
from app.core.session.state import ErrorCategory, RecoveryStrategy


def test_timeout_error_classification():
    """注: Python 3.11+ 中 TimeoutError 是 asyncio.TimeoutError 的别名.
    两者均映射到 RETRY_BACKOFF 策略。"""
    classifier = ErrorClassifier()
    error = TimeoutError("Request timeout")

    result = classifier.classify(error)

    assert result.category == ErrorCategory.TRANSIENT
    assert result.strategy == RecoveryStrategy.RETRY_BACKOFF
    assert result.max_retries == 3


def test_validation_error_classification():
    classifier = ErrorClassifier()
    error = ValueError("Invalid parameter")

    result = classifier.classify(error)

    assert result.category == ErrorCategory.VALIDATION
    assert result.strategy == RecoveryStrategy.DEGRADE
    assert result.max_retries == 0


def test_permission_error_classification():
    classifier = ErrorClassifier()
    error = PermissionError("Access denied")

    result = classifier.classify(error)

    assert result.category == ErrorCategory.PERMISSION
    assert result.strategy == RecoveryStrategy.FAIL
    assert result.max_retries == 0


def test_unknown_error_default_classification():
    classifier = ErrorClassifier()
    error = RuntimeError("Unknown error")

    result = classifier.classify(error)

    assert result.category == ErrorCategory.TRANSIENT
    assert result.strategy == RecoveryStrategy.RETRY
    assert result.max_retries == 1
