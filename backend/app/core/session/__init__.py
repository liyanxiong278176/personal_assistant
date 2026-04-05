"""Session state module for Phase 3: 会话生命周期."""

from .state import (
    ErrorCategory,
    RecoveryStrategy,
    SessionState,
)
from .error_classifier import (
    ErrorCategory,
    ErrorClassification,
    ErrorClassifier,
    RecoveryStrategy,
)
from .retry_manager import (
    RetryManager,
    RetryPolicy,
)
from .fallback import (
    FallbackHandler,
    FallbackResponse,
)
from .initializer import SessionInitializer
from .recovery import SessionRecovery

__all__ = [
    # state
    "SessionState",
    "ErrorCategory",
    "RecoveryStrategy",
    # error_classifier
    "ErrorClassification",
    "ErrorClassifier",
    # retry_manager
    "RetryManager",
    "RetryPolicy",
    # fallback
    "FallbackHandler",
    "FallbackResponse",
    # initializer
    "SessionInitializer",
    # recovery
    "SessionRecovery",
]
