"""Intent module for slot extraction and intent routing."""

from .slot_extractor import SlotExtractor, SlotResult, DateRange
from .router import IntentRouter, ClarificationResult, RouterStatistics
from .config import IntentRouterConfig
from .metrics import IntentMetricsCollector
from .keywords_loader import KeywordsLoader, get_keywords_loader
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
    ITINERARY_PATTERNS,
    QUERY_PATTERNS,
    HOTEL_PATTERNS,
    FOOD_PATTERNS,
    BUDGET_PATTERNS,
    TRANSPORT_PATTERNS,
    CHAT_PATTERNS,
    get_exclusion_keywords,
    has_exclusion_match,
    reload_keywords,
)
from .strategies import (
    IIntentStrategy,
    CacheStrategy,
    ClassificationCache,
    RuleStrategy,
    SemanticValidator,
    SemanticCache,
    cosine_similarity,
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
    # Keywords loader
    "KeywordsLoader",
    "get_keywords_loader",
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
    # Pattern exports
    "ITINERARY_PATTERNS",
    "QUERY_PATTERNS",
    "HOTEL_PATTERNS",
    "FOOD_PATTERNS",
    "BUDGET_PATTERNS",
    "TRANSPORT_PATTERNS",
    "CHAT_PATTERNS",
    # Helper functions
    "get_exclusion_keywords",
    "has_exclusion_match",
    "reload_keywords",
    # Strategy pattern exports
    "IIntentStrategy",
    "CacheStrategy",
    "ClassificationCache",
    "RuleStrategy",
    "SemanticValidator",
    "SemanticCache",
    "cosine_similarity",
    "LLMStrategy",
]
