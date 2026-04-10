"""IntentRouter - Simplified strategy chain orchestration.

Design principles:
    - Unified confidence thresholds (0.8 high, 0.5 mid)
    - No二次判断 - trust each strategy's output
    - Cache-first for performance
    - Simple flow: cache → rule → llm → fallback

Flow:
    1. Check cache → hit → return
    2. Try rule strategy (simple queries only)
       - confidence ≥ 0.8 → return, cache
       - confidence < 0.8 → continue
    3. Try LLM strategy
       - confidence ≥ 0.5 → return, cache
       - confidence < 0.5 → fallback
    4. Fallback → return chat with 0.5 confidence
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.context import RequestContext, IntentResult
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
    """Statistics collected by IntentRouter."""
    total_classifications: int = 0
    strategy_counts: Dict[str, int] = field(default_factory=dict)
    confidence_distribution: Dict[str, int] = field(default_factory=lambda: {
        "high": 0,  # ≥ 0.8
        "mid": 0,   # 0.5 - 0.8
        "low": 0,   # < 0.5
    })
    clarification_count: int = 0
    fallback_count: int = 0
    cache_stats: Dict[str, Any] = field(default_factory=dict)


class IntentRouter:
    """Simplified intent router with unified confidence thresholds.

    Strategy order (by priority):
        0. CacheStrategy - check for cached results
        10. RuleStrategy - keyword matching (simple queries only)
        100. LLMStrategy - LLM classification (fallback)

    Confidence handling (unified across all strategies):
        - ≥ 0.8: High confidence, accept immediately
        - 0.5 - 0.8: Mid confidence, can trigger clarification
        - < 0.5: Low confidence, try next strategy

    No二次判断 - each strategy's confidence is trusted.
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

        # Extract cache strategy if present
        self._cache_strategy = None
        for s in self._strategies:
            if s.__class__.__name__ == "CacheStrategy":
                self._cache_strategy = s
                break

        logger.debug(
            f"[IntentRouter] Initialized with {len(self._strategies)} strategies: "
            f"{[s.__class__.__name__ for s in self._strategies]}"
        )

    async def classify(self, context: RequestContext) -> IntentResult:
        """Classify intent using the simplified strategy chain.

        Simplified flow:
        1. Try cache → hit → return
        2. Try rule → high conf → return, cache
        3. Try LLM → mid/high conf → return, cache
        4. Fallback → return chat

        Args:
            context: Request context containing message and metadata

        Returns:
            IntentResult: Best classification result
        """
        self._stats.total_classifications += 1

        if self._metrics:
            self._metrics.increment(
                "intent_router_classification_total",
                labels={"conversation_id": context.conversation_id or "unknown"},
            )

        # Update cache stats
        if self._cache_strategy:
            self._stats.cache_stats = self._cache_strategy.cache.get_stats()

        best_result: Optional[IntentResult] = None
        best_confidence = 0.0
        best_strategy: str = "unknown"

        # Try each strategy in priority order
        for strategy in self._strategies:
            strategy_name = strategy.__class__.__name__

            # CacheStrategy: check cache first
            if strategy_name == "CacheStrategy":
                cached = await strategy.classify(context)
                if cached:
                    cached.strategy = "CacheStrategy"
                    self._stats.strategy_counts["CacheStrategy"] = (
                        self._stats.strategy_counts.get("CacheStrategy", 0) + 1
                    )
                    self._stats.cache_stats = self._cache_strategy.cache.get_stats()
                    return cached
                continue

            # Check if strategy can handle this request
            if not await strategy.can_handle(context):
                logger.debug(f"[IntentRouter] {strategy_name} cannot handle, skipping")
                continue

            # Perform classification
            try:
                result = await strategy.classify(context)
                result.strategy = strategy_name
            except Exception as e:
                logger.error(f"[IntentRouter] {strategy_name} failed: {e}", exc_info=True)
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

            # Get confidence
            confidence = result.confidence

            # High confidence: accept immediately
            if self._config.is_high_confidence(confidence):
                self._stats.confidence_distribution["high"] += 1
                logger.info(
                    f"[IntentRouter] High confidence ({confidence:.2f}) from {strategy_name}"
                )
                # Cache and return
                self._cache_result(context, result)
                return self._record_success(result, strategy_name)

            # Mid confidence: can trigger clarification
            elif self._config.is_mid_confidence(confidence):
                self._stats.confidence_distribution["mid"] += 1

                # Check if we should trigger clarification
                if self._config.can_clarify(context.clarification_count):
                    self._stats.clarification_count += 1
                    clarification = self._generate_clarification(result, context)
                    logger.info(
                        f"[IntentRouter] Mid confidence ({confidence:.2f}), "
                        f"triggering clarification"
                    )
                    # Attach clarification to result
                    result.clarification = clarification
                    # Cache and return
                    self._cache_result(context, result)
                    return self._record_success(result, strategy_name)

                # Accept medium confidence if clarification not available
                logger.info(
                    f"[IntentRouter] Mid confidence ({confidence:.2f}), "
                    f"clarification limit reached, accepting"
                )
                self._cache_result(context, result)
                return self._record_success(result, strategy_name)

            # Low confidence: track best and continue
            else:
                self._stats.confidence_distribution["low"] += 1
                logger.debug(
                    f"[IntentRouter] Low confidence ({confidence:.2f}) from {strategy_name}"
                )

            # Track best result for fallback
            if confidence > best_confidence:
                best_result = result
                best_confidence = confidence
                best_strategy = strategy_name

        # All strategies exhausted
        if best_result:
            logger.info(
                f"[IntentRouter] All strategies exhausted, returning best "
                f"(confidence={best_confidence:.2f})"
            )
            best_result.strategy = best_strategy
            # Cache and return best effort
            self._cache_result(context, best_result)
            return self._record_success(best_result, "best_effort")

        # Fallback to default
        self._stats.fallback_count += 1
        logger.warning("[IntentRouter] All strategies failed, returning fallback")
        fallback = IntentResult(
            intent=self._config.fallback_intent,
            confidence=self._config.fallback_confidence,
            method="default",
            reasoning="All strategies failed, using fallback",
            strategy="default",
        )
        # Cache even fallback results
        self._cache_result(context, fallback)
        return fallback

    def _cache_result(self, context: RequestContext, result: IntentResult) -> None:
        """Cache a classification result if cache is available.

        Args:
            context: Request context
            result: Result to cache
        """
        if self._cache_strategy:
            self._cache_strategy.cache.put(
                context.message, context.has_image, result
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
            "itinerary": "请告诉我目的地、出行日期和天数",
            "query": "您想查询天气、交通还是门票信息？",
            "chat": "您是想规划行程还是咨询旅行问题？",
            "image": "您想了解这个地点的什么信息？",
        }

        # Suggested follow-ups per intent
        followups = {
            "itinerary": [
                "您的目的地是哪里？",
                "计划出行几天？",
                "大概的预算范围？",
            ],
            "query": [
                "需要查询什么信息？",
                "是针对哪个地点？",
                "计划什么时候去？",
            ],
            "chat": [
                "规划行程",
                "咨询问题",
                "识别地点",
            ],
            "image": [
                "这是哪里？",
                "介绍一下这个地方",
                "怎么去这里？",
            ],
        }

        return ClarificationResult(
            needs_clarification=True,
            question=questions.get(intent, "请提供更多详细信息"),
            original_intent=intent,
            suggested_followup=followups.get(intent, []),
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get classification statistics.

        Returns:
            Dictionary with classification stats
        """
        # Update cache stats
        if self._cache_strategy:
            self._stats.cache_stats = self._cache_strategy.cache.get_stats()

        return {
            "total_classifications": self._stats.total_classifications,
            "strategy_counts": self._stats.strategy_counts.copy(),
            "confidence_distribution": self._stats.confidence_distribution.copy(),
            "clarification_count": self._stats.clarification_count,
            "fallback_count": self._stats.fallback_count,
            "cache_stats": self._stats.cache_stats.copy(),
            "strategies": [s.__class__.__name__ for s in self._strategies],
            "config": {
                "high_threshold": self._config.high_confidence,
                "mid_threshold": self._config.mid_confidence,
                "clarification_enabled": self._config.enable_clarification,
                "max_clarification_rounds": self._config.max_clarification_rounds,
            },
        }

    def reset_statistics(self) -> None:
        """Reset all statistics counters."""
        self._stats = RouterStatistics()
        if self._cache_strategy:
            self._cache_strategy.cache.clear()
