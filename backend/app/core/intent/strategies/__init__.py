"""Intent Strategy Pattern Implementation

Provides a pluggable architecture for intent classification using
the Strategy Pattern. Each strategy implements IIntentStrategy.

Usage:
    from app.core.intent.strategies import IIntentStrategy

    class MyStrategy(IIntentStrategy):
        @property
        def priority(self) -> int:
            return 10

        async def can_handle(self, context: RequestContext) -> bool:
            return True

        async def classify(self, context: RequestContext) -> IntentResult:
            return IntentResult(intent="chat", confidence=0.8, method="my_method")

        def estimated_cost(self) -> float:
            return 0
"""

from .base import IIntentStrategy
from .rule import RuleStrategy

__all__ = [
    "IIntentStrategy",
    "RuleStrategy",
]
