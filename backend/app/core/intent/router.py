"""IntentRouter - Strategy chain orchestration for intent classification.

Orchestrates multiple classification strategies in priority order, applying
confidence-based routing logic to determine when to accept results, trigger
clarification, or fall back to the next strategy.

Architecture:
    - Strategies sorted by priority (lowest first)
    - High confidence (>=0.9): Accept immediately
    - Medium confidence (0.7-0.9): Trigger clarification if enabled
    - Low confidence (<0.7): Try next strategy
    - No strategies succeed: Return fallback result

Usage:
    from app.core.intent import IntentRouter, IntentRouterConfig
    from app.core.intent.strategies import RuleStrategy, LLMFallbackStrategy

    config = IntentRouterConfig()
    strategies = [RuleStrategy(), LLMFallbackStrategy()]
    router = IntentRouter(strategies, config, metrics)

    result = await router.classify(context)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.context import RequestContext
from app.core.intent.classifier import IntentResult
from app.core.intent.config import IntentRouterConfig
from app.core.intent.strategies.base import IIntentStrategy

logger = logging.getLogger(__name__)


@dataclass
class ClarificationResult:
    """Result of a clarification flow.

    Attributes:
        needs_clarification: Whether clarification is needed
        question: The clarification question to ask the user
        original_intent: The original intent that triggered clarification
        suggested_followup: Suggested follow-up questions
    """

    needs_clarification: bool
    question: str = ""
    original_intent: str = ""
    suggested_followup: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "needs_clarification": self.needs_clarification,
            "question": self.question,
            "original_intent": self.original_intent,
            "suggested_followup": self.suggested_followup,
        }


@dataclass
class RouterStatistics:
    """Statistics collected by IntentRouter.

    Attributes:
        total_classifications: Total number of classification requests
        strategy_counts: Number of times each strategy was used
        confidence_distribution: Distribution of confidence scores
        clarification_count: Number of clarifications triggered
        fallback_count: Number of times fallback was used
    """

    total_classifications: int = 0
    strategy_counts: Dict[str, int] = field(default_factory=dict)
    confidence_distribution: Dict[str, int] = field(default_factory=lambda: {
        "high": 0,
        "mid": 0,
        "low": 0,
    })
    clarification_count: int = 0
    fallback_count: int = 0


class IntentRouter:
    """Orchestrates intent classification through a chain of strategies.

    The router manages multiple classification strategies and applies
    confidence-based routing logic to determine the best result.

    Strategy Priority:
        - Lower priority values execute first
        - Rule-based: 0-9 (fast, zero cost)
        - Model-based: 10-49 (lightweight ML)
        - LLM-based: 50-99 (expensive, high accuracy)
        - Fallback: 100 (catch-all)

    Confidence Handling:
        - High (>=0.9): Accept immediately, stop chain
        - Medium (0.7-0.9): Trigger clarification if enabled
        - Low (<0.7): Continue to next strategy
    """

    def __init__(
        self,
        strategies: List[IIntentStrategy],
        config: Optional[IntentRouterConfig] = None,
        metrics_collector: Optional[Any] = None,
    ):
        """Initialize the IntentRouter.

        Args:
            strategies: List of classification strategies (will be sorted by priority)
            config: Optional router configuration (uses defaults if not provided)
            metrics_collector: Optional metrics collector for observability
        """
        # Sort strategies by priority (lower first)
        self._strategies = sorted(strategies, key=lambda s: s.priority)
        self._config = config or IntentRouterConfig()
        self._metrics = metrics_collector
        self._stats = RouterStatistics()

        logger.debug(
            f"[IntentRouter] Initialized with {len(self._strategies)} strategies: "
            f"{[s.__class__.__name__ for s in self._strategies]}"
        )

    async def classify(self, context: RequestContext) -> IntentResult:
        """Classify intent using the strategy chain.

        Execution flow:
        1. Try each strategy in priority order
        2. For high confidence: Accept and return immediately
        3. For medium confidence: Trigger clarification or accept
        4. For low confidence: Continue to next strategy
        5. If all strategies fail: Return fallback result

        Args:
            context: Request context containing message and metadata

        Returns:
            IntentResult: Best classification result from the strategy chain
        """
        self._stats.total_classifications += 1

        if self._metrics:
            self._metrics.increment(
                "intent_router_classification_total",
                labels={"conversation_id": context.conversation_id or "unknown"},
            )

        best_result: Optional[IntentResult] = None
        best_confidence = 0.0

        # Try each strategy in priority order
        for strategy in self._strategies:
            strategy_name = strategy.__class__.__name__

            # Check if strategy can handle this request
            if not await strategy.can_handle(context):
                logger.debug(f"[IntentRouter] {strategy_name} cannot handle, skipping")
                continue

            logger.debug(
                f"[IntentRouter] Trying {strategy_name} (priority={strategy.priority})"
            )

            # Perform classification
            try:
                result = await strategy.classify(context)
            except Exception as e:
                logger.error(
                    f"[IntentRouter] {strategy_name} failed: {e}",
                    exc_info=True,
                )
                if self._metrics:
                    self._metrics.increment(
                        "intent_router_strategy_error",
                        labels={"strategy": strategy_name},
                    )
                continue

            # Track strategy usage
            self._stats.strategy_counts[strategy_name] = (
                self._stats.strategy_counts.get(strategy_name, 0) + 1
            )

            # Record confidence
            confidence = result.confidence
            if self._config.is_high_confidence(confidence):
                self._stats.confidence_distribution["high"] += 1
                logger.debug(
                    f"[IntentRouter] High confidence ({confidence:.2f}) from {strategy_name}"
                )
                return self._record_success(result, strategy_name)

            elif self._config.is_mid_confidence(confidence):
                self._stats.confidence_distribution["mid"] += 1

                # Check if we should trigger clarification
                if self._config.can_clarify(context.clarification_count):
                    self._stats.clarification_count += 1
                    clarification = self._generate_clarification(result, context)
                    logger.debug(
                        f"[IntentRouter] Medium confidence ({confidence:.2f}), "
                        f"triggering clarification"
                    )
                    # Return result with clarification flag
                    result.reasoning = (
                        f"{result.reasoning or ''} (clarification: {clarification.question})"
                    )
                    return self._record_success(result, strategy_name)

                # Accept medium confidence if clarification not available
                logger.debug(
                    f"[IntentRouter] Medium confidence ({confidence:.2f}), "
                    f"clarification limit reached, accepting"
                )
                return self._record_success(result, strategy_name)

            else:
                self._stats.confidence_distribution["low"] += 1
                logger.debug(
                    f"[IntentRouter] Low confidence ({confidence:.2f}) from {strategy_name}"
                )

            # Track best result for fallback
            if confidence > best_confidence:
                best_result = result
                best_confidence = confidence

        # All strategies exhausted, return best or fallback
        if best_result:
            logger.debug(
                f"[IntentRouter] All strategies exhausted, returning best "
                f"(confidence={best_confidence:.2f})"
            )
            return self._record_success(best_result, "best_effort")

        # Fallback to default
        self._stats.fallback_count += 1
        logger.warning("[IntentRouter] All strategies failed, returning fallback")
        return IntentResult(
            intent="chat",
            confidence=0.5,
            method="default",  # Use valid MethodType value
            reasoning="All strategies failed, using fallback",
        )

    def _record_success(
        self, result: IntentResult, strategy_name: str
    ) -> IntentResult:
        """Record successful classification and update metrics.

        Args:
            result: The classification result
            strategy_name: Name of the strategy that produced the result

        Returns:
            The same result (for chaining)
        """
        if self._metrics:
            self._metrics.increment(
                "intent_router_strategy_success",
                labels={"strategy": strategy_name, "intent": result.intent},
            )
            self._metrics.timing(
                "intent_router_confidence",
                result.confidence * 100,
                labels={"strategy": strategy_name},
            )
        return result

    def _generate_clarification(
        self, result: IntentResult, context: RequestContext
    ) -> ClarificationResult:
        """Generate a clarification question based on the classification result.

        Args:
            result: The classification result that triggered clarification
            context: The request context

        Returns:
            ClarificationResult with question and suggested follow-ups
        """
        intent = result.intent

        # Generate intent-specific clarifications
        questions = {
            "itinerary": (
                "I'd like to help plan your trip. Could you provide more details "
                "like your destination, travel dates, and trip duration?"
            ),
            "query": (
                "I can help you find that information. Are you asking about "
                "weather, transportation, tickets, or something else?"
            ),
            "chat": (
                "I'm here to help with travel planning. Would you like to plan "
                "a trip or ask a travel-related question?"
            ),
            "image": (
                "I can help identify that location. Would you like to know "
                "more about this place or plan a visit?"
            ),
        }

        # Suggested follow-ups per intent
        followups = {
            "itinerary": [
                "What's your destination?",
                "How many days are you planning?",
                "What's your budget range?",
            ],
            "query": [
                "What information do you need?",
                "Is this for a specific location?",
                "When are you planning to go?",
            ],
            "chat": [
                "Plan a trip",
                "Ask a travel question",
                "Identify a location",
            ],
            "image": [
                "Where is this?",
                "Tell me about this place",
                "How do I get there?",
            ],
        }

        return ClarificationResult(
            needs_clarification=True,
            question=questions.get(intent, "Could you please provide more details?"),
            original_intent=intent,
            suggested_followup=followups.get(intent, []),
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get classification statistics.

        Returns:
            Dictionary with classification stats including total counts,
            strategy usage, confidence distribution, and clarification/fallback counts
        """
        return {
            "total_classifications": self._stats.total_classifications,
            "strategy_counts": self._stats.strategy_counts.copy(),
            "confidence_distribution": self._stats.confidence_distribution.copy(),
            "clarification_count": self._stats.clarification_count,
            "fallback_count": self._stats.fallback_count,
            "strategies": [s.__class__.__name__ for s in self._strategies],
            "config": {
                "high_threshold": self._config.high_confidence_threshold,
                "mid_threshold": self._config.mid_confidence_threshold,
                "clarification_enabled": self._config.enable_clarification,
                "max_clarification_rounds": self._config.max_clarification_rounds,
            },
        }

    def reset_statistics(self) -> None:
        """Reset all statistics counters."""
        self._stats = RouterStatistics()
