"""Tests for the Executor (execution engine)"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.orchestrator.executor import Executor
from app.core.orchestrator.planner import ExecutionPlan, ExecutionStep, FallbackStrategy


@pytest.mark.asyncio
async def test_execute_single_step():
    """Test executing a single step successfully"""
    mock_tool = AsyncMock()
    mock_tool.execute.return_value = {"temp": 25}

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool

    executor = Executor(tool_registry=mock_registry)
    plan = ExecutionPlan(
        intent="query",
        steps=[
            ExecutionStep(
                tool_name="get_weather",
                params={"city": "北京"}
            )
        ],
        fallback_strategy=FallbackStrategy.CONTINUE
    )

    results = await executor.execute(plan)
    assert "get_weather" in results
    assert results["get_weather"]["success"] is True
    assert results["get_weather"]["data"] == {"temp": 25}
    assert "latency_ms" in results["get_weather"]


@pytest.mark.asyncio
async def test_execute_multiple_steps():
    """Test executing multiple steps"""
    mock_weather = AsyncMock()
    mock_weather.execute.return_value = {"temp": 25}
    mock_poi = AsyncMock()
    mock_poi.execute.return_value = [{"name": "故宫"}]

    mock_registry = MagicMock()
    mock_registry.get.side_effect = lambda name: {
        "get_weather": mock_weather,
        "search_poi": mock_poi
    }.get(name)

    executor = Executor(tool_registry=mock_registry)
    plan = ExecutionPlan(
        intent="itinerary",
        steps=[
            ExecutionStep(tool_name="get_weather", params={"city": "北京"}),
            ExecutionStep(tool_name="search_poi", params={"city": "北京"})
        ],
        fallback_strategy=FallbackStrategy.CONTINUE
    )

    results = await executor.execute(plan)
    assert "get_weather" in results
    assert "search_poi" in results
    assert results["get_weather"]["success"] is True
    assert results["search_poi"]["success"] is True


@pytest.mark.asyncio
async def test_execute_with_fallback_on_failure():
    """Test fallback to cache on tool failure"""
    mock_tool = AsyncMock()
    mock_tool.execute.side_effect = Exception("Network timeout")

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool

    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value={"temp": 20})

    executor = Executor(tool_registry=mock_registry, cache=mock_cache)
    plan = ExecutionPlan(
        intent="query",
        steps=[
            ExecutionStep(
                tool_name="get_weather",
                params={"city": "北京"},
                can_fail=True
            )
        ],
        fallback_strategy=FallbackStrategy.USE_CACHE
    )

    results = await executor.execute(plan)
    assert "get_weather" in results
    # After retry fails, should use cache
    assert results["get_weather"]["from_cache"] is True
    assert results["get_weather"]["data"] == {"temp": 20}


@pytest.mark.asyncio
async def test_execute_retry_on_timeout():
    """Test that retryable errors trigger a retry"""
    mock_tool = AsyncMock()
    # First call fails, second succeeds
    mock_tool.execute.side_effect = [Exception("Network timeout"), {"temp": 25}]

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool

    executor = Executor(tool_registry=mock_registry)
    plan = ExecutionPlan(
        intent="query",
        steps=[
            ExecutionStep(
                tool_name="get_weather",
                params={"city": "北京"},
                can_fail=True
            )
        ],
        fallback_strategy=FallbackStrategy.CONTINUE
    )

    results = await executor.execute(plan)
    assert "get_weather" in results
    assert results["get_weather"]["success"] is True
    # Should have been called twice (initial + retry)
    assert mock_tool.execute.call_count == 2


@pytest.mark.asyncio
async def test_execute_fail_fast_on_critical_failure():
    """Test that critical failures (can_fail=False) raise exceptions"""
    mock_tool = AsyncMock()
    mock_tool.execute.side_effect = Exception("API key invalid")

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool

    executor = Executor(tool_registry=mock_registry)
    plan = ExecutionPlan(
        intent="query",
        steps=[
            ExecutionStep(
                tool_name="get_weather",
                params={"city": "北京"},
                can_fail=False  # Critical step
            )
        ],
        fallback_strategy=FallbackStrategy.FAIL_FAST
    )

    with pytest.raises(Exception, match="API key invalid"):
        await executor.execute(plan)


@pytest.mark.asyncio
async def test_execute_with_custom_fallback_handler():
    """Test custom fallback handler provides graceful degradation"""
    mock_tool = AsyncMock()
    mock_tool.execute.side_effect = Exception("Service unavailable")

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool

    mock_fallback = MagicMock()
    mock_fallback_handler = MagicMock()
    mock_fallback_handler.get_fallback.return_value = mock_fallback

    executor = Executor(
        tool_registry=mock_registry,
        fallback_handler=mock_fallback_handler
    )
    plan = ExecutionPlan(
        intent="query",
        steps=[
            ExecutionStep(
                tool_name="get_weather",
                params={"city": "北京"},
                can_fail=True
            )
        ],
        fallback_strategy=FallbackStrategy.CONTINUE
    )

    results = await executor.execute(plan)
    assert "get_weather" in results
    assert results["get_weather"]["success"] is False
    assert results["get_weather"]["data"] == mock_fallback.message
    mock_fallback_handler.get_fallback.assert_called_once()


@pytest.mark.asyncio
async def test_execute_tool_not_found():
    """Test handling of missing tools"""
    mock_registry = MagicMock()
    mock_registry.get.return_value = None

    executor = Executor(tool_registry=mock_registry)
    plan = ExecutionPlan(
        intent="query",
        steps=[
            ExecutionStep(tool_name="unknown_tool", params={})
        ],
        fallback_strategy=FallbackStrategy.FAIL_FAST
    )

    with pytest.raises(ValueError, match="Tool unknown_tool not found"):
        await executor.execute(plan)


@pytest.mark.asyncio
async def test_is_retryable_error_detection():
    """Test detection of retryable errors"""
    executor = Executor()

    # Retryable errors
    assert executor._is_retryable(Exception("Request timeout"))
    assert executor._is_retryable(Exception("Network error"))
    assert executor._is_retryable(Exception("Rate limit exceeded"))
    assert executor._is_retryable(Exception("429 Too Many Requests"))
    assert executor._is_retryable(Exception("503 Service Unavailable"))

    # Non-retryable errors
    assert not executor._is_retryable(Exception("Invalid API key"))
    assert not executor._is_retryable(Exception("Authentication failed"))
    assert not executor._is_retryable(Exception("Bad request"))


@pytest.mark.asyncio
async def test_execute_with_latency_measurement():
    """Test that execution measures latency correctly"""
    import asyncio

    async def slow_execute(**kwargs):
        await asyncio.sleep(0.1)  # 100ms
        return {"result": "done"}

    mock_tool = AsyncMock()
    mock_tool.execute = slow_execute

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool

    executor = Executor(tool_registry=mock_registry)
    plan = ExecutionPlan(
        intent="query",
        steps=[
            ExecutionStep(tool_name="slow_tool", params={})
        ],
        fallback_strategy=FallbackStrategy.CONTINUE
    )

    results = await executor.execute(plan)
    assert "slow_tool" in results
    assert results["slow_tool"]["latency_ms"] >= 100  # At least 100ms
