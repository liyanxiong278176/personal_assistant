"""Intent Strategy Interface - IIntentStrategy

Defines the contract for all intent classification strategies.
Strategies are ordered by priority and evaluated sequentially.

Priority ranges:
- 0-9: Rule-based strategies (fast, zero cost)
- 10-49: Model-based strategies (lightweight ML)
- 50-99: LLM-based strategies (expensive, high accuracy)
- 100: Fallback strategy (catch-all)
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.core.context import RequestContext, IntentResult


class IIntentStrategy(ABC):
    """Base interface for intent classification strategies.

    Each strategy implements a specific approach to intent classification:
    - RuleStrategy: Keyword/pattern matching (priority 0-9)
    - ModelStrategy: Lightweight ML models (priority 10-49)
    - LLMStrategy: Large language model classification (priority 50-99)
    - FallbackStrategy: Default classification (priority 100)
    """

    @property
    @abstractmethod
    def priority(self) -> int:
        """Strategy execution priority.

        Lower numbers execute first.
        - 0-9: Rules (keyword, pattern, regex)
        - 10-49: Models (lightweight ML, embeddings)
        - 50-99: LLM (expensive but accurate)
        - 100: Fallback (default handler)

        Returns:
            int: Priority value (lower = earlier execution)
        """
        pass

    @abstractmethod
    async def can_handle(self, context: RequestContext) -> bool:
        """Fast pre-check if this strategy can handle the request.

        This should be a lightweight check to avoid expensive
        operations for strategies that cannot handle the request.

        Args:
            context: The request context containing message and metadata

        Returns:
            bool: True if this strategy should attempt classification
        """
        pass

    @abstractmethod
    async def classify(self, context: RequestContext) -> IntentResult:
        """Perform intent classification.

        Called after can_handle returns True. Should return a complete
        IntentResult with intent type, confidence, and reasoning.

        Args:
            context: The request context containing message and metadata

        Returns:
            IntentResult: Classification result with intent, confidence,
                method, and optional reasoning
        """
        pass

    @abstractmethod
    def estimated_cost(self) -> float:
        """Estimated cost in tokens.

        Returns the approximate token cost for using this strategy:
        - 0: Rule-based (no LLM calls)
        - 10-100: Lightweight model calls
        - 500-2000: LLM-based classification
        - 2000+: Complex LLM chains

        Returns:
            float: Estimated token cost (0 for rule-based strategies)
        """
        pass
