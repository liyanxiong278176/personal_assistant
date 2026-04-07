"""Tests for IntentMetricsCollector.

Tests recording of classification results, statistics aggregation,
and rule hit rate calculation.
"""

from unittest.mock import MagicMock

from app.core.intent.classifier import IntentResult
from app.core.intent.metrics import IntentMetricsCollector


class TestIntentMetricsCollector:
    """Tests for IntentMetricsCollector."""

    def test_record_classification(self) -> None:
        """Test that recording updates all statistics correctly."""
        collector = IntentMetricsCollector()

        result1 = IntentResult(
            intent="itinerary",
            confidence=0.95,
            method="keyword",
            reasoning="Matched travel keywords",
        )
        result2 = IntentResult(
            intent="query",
            confidence=0.85,
            method="llm",
            reasoning="Complex query",
        )
        result3 = IntentResult(
            intent="itinerary",
            confidence=0.92,
            method="keyword",
            reasoning="Matched planning keywords",
        )

        collector.record("conv1", result1, latency_ms=5.2)
        collector.record("conv2", result2, latency_ms=120.0)
        collector.record("conv3", result3, latency_ms=4.8)

        stats = collector.get_statistics()

        assert stats["total"] == 3
        assert stats["by_intent"] == {
            "itinerary": 2,
            "query": 1,
        }
        assert stats["by_strategy"] == {
            "keyword": 2,
            "llm": 1,
        }

    def test_hit_rate_calculation(self) -> None:
        """Test rule hit rate calculation across mixed method types."""
        collector = IntentMetricsCollector()

        # 4 keyword (rule) hits
        for i in range(4):
            collector.record(
                f"rule_conv_{i}",
                IntentResult(
                    intent="query",
                    confidence=0.9,
                    method="keyword",
                ),
                latency_ms=3.0,
            )

        # 6 non-rule (llm, default, etc.)
        for i in range(6):
            collector.record(
                f"non_rule_conv_{i}",
                IntentResult(
                    intent="itinerary",
                    confidence=0.8,
                    method="llm",
                ),
                latency_ms=150.0,
            )

        stats = collector.get_statistics()

        assert stats["total"] == 10
        assert abs(stats["rule_hit_rate"] - 0.4) < 0.001

    def test_hit_rate_empty(self) -> None:
        """Test rule hit rate is 0.0 when no records exist."""
        collector = IntentMetricsCollector()

        stats = collector.get_statistics()

        assert stats["total"] == 0
        assert stats["rule_hit_rate"] == 0.0

    def test_record_with_shared_metrics(self) -> None:
        """Test that record forwards to a shared MetricsCollector if provided."""
        shared = MagicMock()
        collector = IntentMetricsCollector(metrics=shared)

        result = IntentResult(
            intent="chat",
            confidence=0.5,
            method="default",
        )
        collector.record("conv_x", result, latency_ms=1.0)

        # Check local stats
        stats = collector.get_statistics()
        assert stats["total"] == 1
        assert stats["by_intent"]["chat"] == 1

        # Verify shared collector was called
        shared.increment.assert_called_once()
        call_args = shared.increment.call_args
        assert call_args[0][0] == "intent_classifications_total"
        assert call_args[1]["labels"] == {"intent": "chat", "method": "default"}

        shared.timing.assert_called_once()
        call_args_timing = shared.timing.call_args
        assert call_args_timing[0][0] == "intent_classification_latency_ms"
        assert call_args_timing[0][1] == 1.0
        assert call_args_timing[1]["labels"] == {"intent": "chat", "method": "default"}
