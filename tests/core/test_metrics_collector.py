import pytest
from app.core.metrics.collector import MetricsCollector
from app.core.metrics.definitions import IntentMetric

@pytest.mark.asyncio
async def test_record_intent_metric():
    collector = MetricsCollector()
    metric = IntentMetric(
        intent="itinerary",
        method="llm",
        confidence=0.9,
        is_correct=None,
        latency_ms=150
    )
    await collector.record_intent(metric)
    stats = collector.get_intent_stats()
    assert stats["total"] == 1
    assert stats["by_method"]["llm"] == 1

@pytest.mark.asyncio
async def test_record_tool_metric():
    collector = MetricsCollector()
    from app.core.metrics.definitions import ToolMetric
    metric = ToolMetric(
        tool_name="get_weather",
        success=True,
        latency_ms=100,
        used_cache=False
    )
    await collector.record_tool(metric)
    stats = collector.get_tool_stats()
    assert stats["total"] == 1
    assert stats["success_rate"] == 1.0

@pytest.mark.asyncio
async def test_record_task_metric():
    collector = MetricsCollector()
    from app.core.metrics.definitions import TaskMetric
    metric = TaskMetric(
        session_id="test_session",
        message_id="msg1",
        intent="itinerary",
        completed=True,
        user_satisfied=None,
        latency_ms=2000
    )
    await collector.record_task(metric)
    stats = collector.get_task_stats()
    assert stats["total"] == 1
    assert stats["completion_rate"] == 1.0
