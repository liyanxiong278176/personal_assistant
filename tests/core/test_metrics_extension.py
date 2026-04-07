"""Tests for MetricsCollector extension - get_statistics unified API"""
import pytest
import asyncio
from app.core.metrics.collector import MetricsCollector
from app.core.metrics.definitions import IntentMetric, ToolMetric, TaskMetric


def test_metrics_get_statistics_intent():
    """Test get_statistics method with 'intent' prefix"""
    collector = MetricsCollector()

    # Record sample intent metric
    async def record_sample():
        await collector.record_intent(IntentMetric(
            intent="itinerary",
            method="rule",
            confidence=0.95,
            latency_ms=42.0,
            is_correct=True
        ))

    asyncio.run(record_sample())

    # New unified API
    stats = collector.get_statistics("intent")
    assert stats["total"] >= 1
    assert "by_method" in stats
    assert stats["by_method"].get("rule", 0) >= 1
    assert "accuracy" in stats
    assert "avg_latency_ms" in stats


def test_metrics_get_statistics_tool():
    """Test get_statistics method with 'tool' prefix"""
    collector = MetricsCollector()

    # Record sample tool metric
    async def record_sample():
        await collector.record_tool(ToolMetric(
            tool_name="weather_api",
            success=True,
            latency_ms=100.0,
            used_cache=False
        ))

    asyncio.run(record_sample())

    # New unified API
    stats = collector.get_statistics("tool")
    assert stats["total"] >= 1
    assert "success_rate" in stats
    assert "cache_hit_rate" in stats


def test_metrics_get_statistics_task():
    """Test get_statistics method with 'task' prefix"""
    collector = MetricsCollector()

    # Record sample task metric
    async def record_sample():
        await collector.record_task(TaskMetric(
            session_id="test-session",
            message_id="msg-1",
            intent="itinerary",
            completed=True,
            user_satisfied=None,
            latency_ms=500.0
        ))

    asyncio.run(record_sample())

    # New unified API
    stats = collector.get_statistics("task")
    assert stats["total"] >= 1
    assert "completion_rate" in stats


def test_metrics_get_statistics_invalid_prefix():
    """Test get_statistics method with invalid prefix raises ValueError"""
    collector = MetricsCollector()

    with pytest.raises(ValueError, match="Unknown prefix"):
        collector.get_statistics("invalid_prefix")
