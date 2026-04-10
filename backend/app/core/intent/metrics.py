"""Intent-specific metrics collector.

Tracks intent classification results, strategies used, and latency
for monitoring and optimization of the intent routing pipeline.
"""

from collections import defaultdict
from threading import Lock
from typing import Any, Dict, Optional

from ..context import IntentResult
from ..observability.metrics import MetricsCollector


class IntentMetricsCollector:
    """Specialized metrics collector for intent classification.

    Aggregates classification results across conversations, tracking
    intent distribution, strategy effectiveness, and latency.

    Args:
        metrics: Optional shared MetricsCollector for forwarding metrics.
                 If None, metrics are only stored locally.
    """

    def __init__(self, metrics: Optional[MetricsCollector] = None) -> None:
        self._metrics = metrics
        self._lock = Lock()

        # Local aggregation (also forwarded to MetricsCollector)
        self._total: int = 0
        self._by_intent: Dict[str, int] = defaultdict(int)
        self._by_strategy: Dict[str, int] = defaultdict(int)
        # Track rule-based (keyword) vs non-rule methods for hit rate
        self._rule_methods = {"keyword"}
        self._rule_hits: int = 0

    def record(
        self,
        conversation_id: str,
        result: IntentResult,
        latency_ms: float,
    ) -> None:
        """Record a classification result.

        Args:
            conversation_id: Unique conversation identifier
            result: The IntentResult from classification
            latency_ms: Classification latency in milliseconds
        """
        with self._lock:
            self._total += 1
            self._by_intent[result.intent] += 1
            self._by_strategy[result.method] += 1

            if result.method in self._rule_methods:
                self._rule_hits += 1

        # Forward to shared MetricsCollector if provided
        if self._metrics is not None:
            self._metrics.increment(
                "intent_classifications_total",
                labels={"intent": result.intent, "method": result.method},
            )
            self._metrics.timing(
                "intent_classification_latency_ms",
                latency_ms,
                labels={"intent": result.intent, "method": result.method},
            )

    def get_statistics(self) -> Dict[str, Any]:
        """Return aggregated statistics.

        Returns:
            Dictionary with total classifications, breakdowns by intent
            and strategy, and rule hit rate.
        """
        with self._lock:
            total = self._total
            by_intent = dict(self._by_intent)
            by_strategy = dict(self._by_strategy)
            rule_hit_rate = (
                self._rule_hits / total if total > 0 else 0.0
            )

        return {
            "total": total,
            "by_intent": by_intent,
            "by_strategy": by_strategy,
            "rule_hit_rate": rule_hit_rate,
        }
