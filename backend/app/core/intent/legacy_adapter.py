"""LegacyIntentAdapter - Adapter for gradual migration from IntentClassifier to IntentRouter.

This adapter wraps the existing IntentClassifier and makes it compatible with
the new IIntentStrategy interface, allowing for gradual migration.

Priority: 50 (default, configurable)
Cost: estimated_tokens (default 50.0)
"""

import logging
from typing import Optional

from app.core.context import RequestContext
from app.core.intent.classifier import IntentClassifier, IntentResult

logger = logging.getLogger(__name__)


class LegacyIntentAdapter:
    """Adapter for wrapping IntentClassifier as IIntentStrategy.

    This adapter allows the existing IntentClassifier to participate in the
    new IntentRouter strategy chain, enabling gradual migration without
    breaking existing functionality.

    Behavior:
    - Wraps the legacy IntentClassifier instance
    - can_handle() always returns True (backward compatible)
    - classify() calls legacy classifier and converts result
    - estimated_cost() returns configured token estimate
    """

    def __init__(
        self,
        legacy_classifier: IntentClassifier,
        priority: int = 50,
        estimated_tokens: float = 50.0
    ):
        """Initialize the legacy adapter.

        Args:
            legacy_classifier: The existing IntentClassifier instance to wrap
            priority: Strategy priority (default 50, medium priority)
            estimated_tokens: Estimated token cost for this strategy
        """
        self._classifier = legacy_classifier
        self._priority = priority
        self._estimated_tokens = estimated_tokens
        self._logger = logging.getLogger(__name__)

    @property
    def priority(self) -> int:
        """Get the strategy priority.

        Returns:
            int: Priority value (default 50, configurable via __init__)
        """
        return self._priority

    def estimated_cost(self) -> float:
        """Get estimated token cost.

        Returns:
            float: Estimated token cost (default 50.0, configurable via __init__)
        """
        return self._estimated_tokens

    async def can_handle(self, context: RequestContext) -> bool:
        """Check if this strategy can handle the request.

        The legacy classifier was designed to handle all requests, so this
        always returns True for backward compatibility.

        Args:
            context: The request context

        Returns:
            bool: Always True - legacy classifier handles all requests
        """
        return True

    async def classify(self, context: RequestContext) -> IntentResult:
        """Classify intent using the wrapped legacy classifier.

        Args:
            context: The request context containing message and metadata

        Returns:
            IntentResult: Classification result from the legacy classifier
        """
        message = context.message
        has_image = bool(context.tool_results.get("has_image", False))

        try:
            # Call the legacy classifier's async method
            result = await self._classifier.classify(
                message=message,
                has_image=has_image
            )

            self._logger.debug(
                f"[LegacyIntentAdapter] Classified as {result.intent} "
                f"with confidence {result.confidence} via {result.method}"
            )

            return result

        except Exception as e:
            # Fallback to sync method if async fails or for compatibility
            self._logger.warning(
                f"[LegacyIntentAdapter] Async classify failed, falling back to sync: {e}"
            )
            result = self._classifier.classify_sync(
                message=message,
                has_image=has_image
            )
            return result

    def classify_sync(self, context: RequestContext) -> IntentResult:
        """Synchronous classify method for non-async contexts.

        Args:
            context: The request context

        Returns:
            IntentResult: Classification result from legacy classifier
        """
        message = context.message
        has_image = bool(context.tool_results.get("has_image", False))

        return self._classifier.classify_sync(
            message=message,
            has_image=has_image
        )
