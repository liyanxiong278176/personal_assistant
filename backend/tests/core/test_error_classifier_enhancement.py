"""Tests for ErrorClassifier enhancement (Agent Core v1.1)."""

import pytest
from app.core.session.error_classifier import (
    ErrorClassifier,
    ErrorClassification,
    ENHANCEMENT_PRESET_RULES,
)
from app.core.session.state import ErrorCategory, RecoveryStrategy


class ToolExecutionFailed(Exception):
    """Simulated tool execution failure."""
    pass


class ToolTimeout(Exception):
    """Simulated tool timeout."""
    pass


class ToolLoopExhausted(Exception):
    """Simulated tool loop exhaustion."""
    pass


class TokenBudgetExceeded(Exception):
    """Simulated token budget exceeded."""
    pass


class CustomError(Exception):
    """Simulated custom error."""
    pass


class TestToolExecutionFailed:
    """Test ToolExecutionFailed error classification."""

    def test_tool_execution_failed(self):
        """Test: ToolExecutionFailed is classified as TRANSIENT/RETRY with max_retries=1."""
        classifier = ErrorClassifier()
        error = ToolExecutionFailed("Tool failed to execute")

        result = classifier.classify(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.strategy == RecoveryStrategy.RETRY
        assert result.max_retries == 1

    def test_tool_timeout(self):
        """Test: ToolTimeout is classified as TRANSIENT/RETRY_BACKOFF with max_retries=2."""
        classifier = ErrorClassifier()
        error = ToolTimeout("Tool timed out")

        result = classifier.classify(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.strategy == RecoveryStrategy.RETRY_BACKOFF
        assert result.max_retries == 2

    def test_tool_loop_exhausted(self):
        """Test: ToolLoopExhausted is classified as VALIDATION/DEGRADE."""
        classifier = ErrorClassifier()
        error = ToolLoopExhausted("Tool loop exhausted")

        result = classifier.classify(error)

        assert result.category == ErrorCategory.VALIDATION
        assert result.strategy == RecoveryStrategy.DEGRADE
        assert result.max_retries == 0

    def test_token_budget_exceeded(self):
        """Test: TokenBudgetExceeded is classified as RESOURCE/DEGRADE."""
        classifier = ErrorClassifier()
        error = TokenBudgetExceeded("Token budget exceeded")

        result = classifier.classify(error)

        assert result.category == ErrorCategory.RESOURCE
        assert result.strategy == RecoveryStrategy.DEGRADE
        assert result.max_retries == 0


class TestEnhancementRules:
    """Test ENHANCEMENT_PRESET_RULES constants."""

    def test_enhancement_rules_keys(self):
        """Test: ENHANCEMENT_PRESET_RULES contains expected keys."""
        assert "ToolExecutionFailed" in ENHANCEMENT_PRESET_RULES
        assert "ToolTimeout" in ENHANCEMENT_PRESET_RULES
        assert "ToolLoopExhausted" in ENHANCEMENT_PRESET_RULES
        assert "TokenBudgetExceeded" in ENHANCEMENT_PRESET_RULES

    def test_enhancement_rules_values(self):
        """Test: ENHANCEMENT_PRESET_RULES values match expected (category, strategy, retries)."""
        assert ENHANCEMENT_PRESET_RULES["ToolExecutionFailed"] == (
            ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY, 1
        )
        assert ENHANCEMENT_PRESET_RULES["ToolTimeout"] == (
            ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY_BACKOFF, 2
        )
        assert ENHANCEMENT_PRESET_RULES["ToolLoopExhausted"] == (
            ErrorCategory.VALIDATION, RecoveryStrategy.DEGRADE, 0
        )
        assert ENHANCEMENT_PRESET_RULES["TokenBudgetExceeded"] == (
            ErrorCategory.RESOURCE, RecoveryStrategy.DEGRADE, 0
        )


class TestCustomErrorRegistration:
    """Test custom error registration."""

    def test_custom_error_registration(self):
        """Test: Custom errors can be registered and override preset rules."""
        custom_rules = {
            "CustomError": (ErrorCategory.FATAL, RecoveryStrategy.FAIL, 0),
        }
        classifier = ErrorClassifier(custom_rules=custom_rules)
        error = CustomError("Custom error message")

        result = classifier.classify(error)

        assert result.category == ErrorCategory.FATAL
        assert result.strategy == RecoveryStrategy.FAIL
        assert result.max_retries == 0

    def test_custom_override_enhancement_rule(self):
        """Test: Custom rule can override an enhancement preset rule."""
        custom_rules = {
            "ToolExecutionFailed": (ErrorCategory.FATAL, RecoveryStrategy.FAIL, 0),
        }
        classifier = ErrorClassifier(custom_rules=custom_rules)
        error = ToolExecutionFailed("Overridden")

        result = classifier.classify(error)

        # Custom rule takes precedence
        assert result.category == ErrorCategory.FATAL
        assert result.strategy == RecoveryStrategy.FAIL
        assert result.max_retries == 0

    def test_unknown_error_defaults(self):
        """Test: Unknown errors fall back to default classification."""
        classifier = ErrorClassifier()
        error = CustomError("Unknown error")

        result = classifier.classify(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.strategy == RecoveryStrategy.RETRY
        assert result.max_retries == 1


class TestPresetRulesMerged:
    """Test that enhancement rules are merged with preset rules."""

    def test_preset_rules_count(self):
        """Test: ErrorClassifier merges enhancement rules into preset rules."""
        classifier = ErrorClassifier()
        # PRESET_RULES has 4 entries (TimeoutError, ConnectionError, ValueError, PermissionError)
        # ENHANCEMENT_PRESET_RULES has 4 entries (string keys)
        # Total: 4 type-based + 4 string-keyed = 8 entries
        assert len(classifier._preset_rules) >= 8

    def test_enhancement_rules_in_preset_rules(self):
        """Test: Enhancement rules are accessible via _preset_rules dict."""
        classifier = ErrorClassifier()

        # String keys from ENHANCEMENT_PRESET_RULES should be in _preset_rules
        for key in ENHANCEMENT_PRESET_RULES:
            assert key in classifier._preset_rules
            assert classifier._preset_rules[key] == ENHANCEMENT_PRESET_RULES[key]
