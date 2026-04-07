"""Intent module for slot extraction and intent classification"""

from .slot_extractor import SlotExtractor, SlotResult, DateRange
from .classifier import (
    IntentClassifier,
    IntentResult,
    KEYWORD_RULES,
    intent_classifier
)
from .complexity import is_complex_query, ComplexityResult
from .llm_classifier import LLMIntentClassifier, LLM_CLASSIFY_PROMPT
from .config import IntentRouterConfig
from .metrics import IntentMetricsCollector
from .router import ClarificationResult, IntentRouter, RouterStatistics
from .legacy_adapter import LegacyIntentAdapter
from .strategies import (
    IIntentStrategy,
    RuleStrategy,
    LLMFallbackStrategy,
)

__all__ = [
    "SlotExtractor",
    "SlotResult",
    "DateRange",
    "IntentClassifier",
    "IntentResult",
    "KEYWORD_RULES",
    "intent_classifier",
    "is_complex_query",
    "ComplexityResult",
    "LLMIntentClassifier",
    "LLM_CLASSIFY_PROMPT",
    "IntentRouterConfig",
    "IntentRouter",
    "IntentMetricsCollector",
    "ClarificationResult",
    "RouterStatistics",
    "LegacyIntentAdapter",
    # Strategy pattern exports
    "IIntentStrategy",
    "RuleStrategy",
    "LLMFallbackStrategy",
]
