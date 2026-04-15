"""Intent Strategy Pattern Implementation

Provides a pluggable architecture for intent classification using
the Strategy Pattern. Each strategy implements IIntentStrategy.

Strategies (by priority):
    - CacheStrategy (priority=0): Check cache first
    - RuleStrategy (priority=10): Keyword matching for simple queries
    - SemanticValidator (priority=15): LLM validation for suspicious results
    - LLMStrategy (priority=100): LLM fallback for complex queries

Usage:
    from app.core.intent.strategies import CacheStrategy, RuleStrategy, LLMStrategy

    cache = CacheStrategy()
    rule = RuleStrategy()
    llm = LLMStrategy(llm_client=client)

    router = IntentRouter([cache, rule, llm])
"""

from .base import IIntentStrategy
from .cache import CacheStrategy, ClassificationCache
from .rule import RuleStrategy
from .semantic_validator import SemanticValidator
from .semantic_cache import SemanticCache, cosine_similarity
from .llm_fallback import LLMStrategy

# Legacy export for compatibility
LLMFallbackStrategy = LLMStrategy

__all__ = [
    "IIntentStrategy",
    "CacheStrategy",
    "ClassificationCache",
    "RuleStrategy",
    "SemanticValidator",
    "SemanticCache",
    "cosine_similarity",
    "LLMStrategy",
    "LLMFallbackStrategy",  # Legacy alias
]
