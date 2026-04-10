"""Intent module for slot extraction and intent routing."""

from .slot_extractor import SlotExtractor, SlotResult, DateRange
from .router import IntentRouter, ClarificationResult, RouterStatistics
from .config import IntentRouterConfig
from .metrics import IntentMetricsCollector
from .keywords import (
    ALL_INTENT_KEYWORDS,
    ALL_INTENT_PATTERNS,
    ITINERARY_KEYWORDS,
    QUERY_KEYWORDS,
    CHAT_KEYWORDS,
    IMAGE_KEYWORDS,
    HOTEL_KEYWORDS,
    FOOD_KEYWORDS,
    BUDGET_KEYWORDS,
    TRANSPORT_KEYWORDS,
)
from .strategies import (
    IIntentStrategy,
    CacheStrategy,
    ClassificationCache,
    RuleStrategy,
    LLMStrategy,
)

__all__ = [
    "SlotExtractor",
    "SlotResult",
    "DateRange",
    "IntentRouter",
    "ClarificationResult",
    "RouterStatistics",
    "IntentRouterConfig",
    "IntentMetricsCollector",
    # Keyword exports
    "ALL_INTENT_KEYWORDS",
    "ALL_INTENT_PATTERNS",
    "ITINERARY_KEYWORDS",
    "QUERY_KEYWORDS",
    "CHAT_KEYWORDS",
    "IMAGE_KEYWORDS",
    "HOTEL_KEYWORDS",
    "FOOD_KEYWORDS",
    "BUDGET_KEYWORDS",
    "TRANSPORT_KEYWORDS",
    # Strategy pattern exports
    "IIntentStrategy",
    "CacheStrategy",
    "ClassificationCache",
    "RuleStrategy",
    "LLMStrategy",
]
