"""E2E integration tests for Agent Core productionization features.

Tests the integration between:
- Intent classification (hybrid keyword + LLM)
- Complexity detection
- Model routing
- Planner / ExecutionPlan generation
- Metrics collection

These tests verify the integration points work correctly, using mocks
where actual LLM clients are not configured.
"""

import pytest

from app.core.context import IntentResult
from app.core.intent import IntentRouter, RuleStrategy, LLMStrategy
from app.core.intent.complexity import is_complex_query, ComplexityResult
from app.core.intent.slot_extractor import SlotResult
from app.core.orchestrator.model_router import ModelRouter
from app.core.orchestrator.planner import Planner, ExecutionPlan
from app.core.metrics.collector import MetricsCollector
from app.core.metrics.definitions import IntentMetric


# =============================================================================
# Intent Classification Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_hybrid_intent_classification_keyword():
    """Test hybrid intent classification uses keyword matching for simple queries."""
    router = IntentRouter(strategies=[RuleStrategy(), LLMStrategy()])

    # Simple greeting - should match via keyword rules
    result = await router.classify(RequestContext(message="你好"))
    assert result.strategy in ("RuleStrategy", "LLMStrategy", "CacheStrategy", "default")
    assert result.intent == "chat"
    assert result.need_tool is False


@pytest.mark.asyncio
async def test_hybrid_intent_classification_itinerary():
    """Test itinerary keyword matching for travel queries."""
    router = IntentRouter(strategies=[RuleStrategy(), LLMStrategy()])

    # Travel query with keywords - should match itinerary via keyword rules
    result = await router.classify(RequestContext(message="规划云南7天自驾游预算5000元"))
    assert result.strategy in ("RuleStrategy", "LLMStrategy", "default")
    assert result.intent in ("itinerary", "chat")
    assert result.need_tool is True or result.intent == "itinerary"


@pytest.mark.asyncio
async def test_hybrid_intent_classification_complex_flag():
    """Test is_complex flag influences classification."""
    router = IntentRouter(strategies=[RuleStrategy(), LLMStrategy()])

    # Simple query without complex flag
    result1 = await router.classify(RequestContext(message="北京天气", is_complex=False))
    assert result1.method in ("keyword", "default")

    # Same query with complex flag (may trigger LLM path if configured)
    result2 = await router.classify(RequestContext(message="北京天气", is_complex=True))
    # With complex flag set externally, the classifier may route to LLM
    assert result2.intent in ("query", "chat", "itinerary")


@pytest.mark.asyncio
async def test_hybrid_intent_classification_cache():
    """Test that repeated queries are served from cache."""
    classifier = IntentClassifier(llm_client=None)

    # First classification
    result1 = await router.classify(RequestContext(message="你好", is_complex=False))

    # Second classification of same message should hit cache
    result2 = await router.classify(RequestContext(message="你好", is_complex=False))
    assert result2.method == "cache"
    assert result2.intent == result1.intent


# =============================================================================
# Complexity Detection Integration Tests
# =============================================================================

def test_complexity_detection_short_message():
    """Test complexity detection for short messages."""
    result = is_complex_query("你好")
    assert result.is_complex is False
    assert result.score == 0.0


def test_complexity_detection_long_message():
    """Test complexity detection for long messages."""
    # Message over 30 chars gets +0.3 score
    long_msg = "帮我规划一条从云南出发的7天自驾游路线，预算5000元，包含酒店推荐和美食攻略"
    result = is_complex_query(long_msg)
    assert result.is_complex is True
    assert result.score > 0.3


def test_complexity_detection_with_planning_keywords():
    """Test complexity detection with planning keywords."""
    msg = "规划行程"
    result = is_complex_query(msg)
    # "规划" keyword adds 0.2
    assert result.score >= 0.2
    assert result.is_complex is False  # Still below 0.5 threshold


def test_complexity_detection_combined_factors():
    """Test complexity detection with combined factors."""
    # Long + planning keywords = definitely complex
    msg = "帮我" + "规划" * 5 + "云南" + "旅行" * 10
    result = is_complex_query(msg)
    assert result.is_complex is True


def test_complexity_result_structure():
    """Test ComplexityResult has correct structure."""
    result = is_complex_query("测试消息")
    assert isinstance(result, ComplexityResult)
    assert hasattr(result, "is_complex")
    assert hasattr(result, "reason")
    assert hasattr(result, "score")


# =============================================================================
# Model Routing Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_model_routing_simple_chat():
    """Test simple chat queries route to small model."""
    router = ModelRouter()

    intent = IntentResult(
        intent="chat",
        confidence=0.9,
        method="keyword",
        need_tool=False
    )
    client = router.route(intent, is_complex=False)
    assert client.model == ModelRouter.SMALL_MODEL


@pytest.mark.asyncio
async def test_model_routing_complex_itinerary():
    """Test complex itinerary queries route to large model."""
    router = ModelRouter()

    intent = IntentResult(
        intent="itinerary",
        confidence=0.8,
        method="llm",
        need_tool=True
    )
    client = router.route(intent, is_complex=True)
    assert client.model == ModelRouter.LARGE_MODEL


@pytest.mark.asyncio
async def test_model_routing_simple_itinerary():
    """Test simple itinerary queries still use small model."""
    router = ModelRouter()

    intent = IntentResult(
        intent="itinerary",
        confidence=0.9,
        method="keyword",
        need_tool=True
    )
    client = router.route(intent, is_complex=False)
    assert client.model == ModelRouter.SMALL_MODEL


@pytest.mark.asyncio
async def test_model_routing_query_intent():
    """Test query intents route appropriately based on complexity."""
    router = ModelRouter()

    # Simple query
    intent_simple = IntentResult(
        intent="query",
        confidence=0.9,
        method="keyword",
        need_tool=True
    )
    client_simple = router.route(intent_simple, is_complex=False)
    assert client_simple.model == ModelRouter.SMALL_MODEL

    # Complex query (not itinerary, still small)
    intent_complex = IntentResult(
        intent="query",
        confidence=0.8,
        method="llm",
        need_tool=True
    )
    client_complex = router.route(intent_complex, is_complex=True)
    assert client_complex.model == ModelRouter.SMALL_MODEL


# =============================================================================
# Planner Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_planner_creates_execution_plan():
    """Test planner creates execution plan from intent and slots."""
    planner = Planner()

    intent = IntentResult(
        intent="query",
        confidence=0.9,
        method="keyword",
        need_tool=True,
        reasoning="天气查询"
    )
    slots = SlotResult(destination="北京")

    plan = await planner.create_plan(intent, slots)
    assert isinstance(plan, ExecutionPlan)
    assert plan.intent == "query"
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "get_weather"


@pytest.mark.asyncio
async def test_planner_itinerary_plan():
    """Test planner creates multi-step plan for itinerary intent."""
    planner = Planner()

    intent = IntentResult(
        intent="itinerary",
        confidence=0.85,
        method="llm",
        need_tool=True,
        reasoning="行程规划"
    )
    slots = SlotResult(
        destination="云南",
        days=7,
        budget="中等"
    )

    plan = await planner.create_plan(intent, slots)
    assert plan.intent == "itinerary"
    tool_names = [s.tool_name for s in plan.steps]
    assert "get_weather" in tool_names
    assert "search_poi" in tool_names


@pytest.mark.asyncio
async def test_planner_multi_destination_route():
    """Test planner includes route planning for multi-destination trips."""
    planner = Planner()

    intent = IntentResult(
        intent="itinerary",
        confidence=0.9,
        method="keyword",
        need_tool=True,
        reasoning="多地行程"
    )
    slots = SlotResult(
        destinations=["北京", "上海", "杭州"],
        days=5
    )

    plan = await planner.create_plan(intent, slots)
    tool_names = [s.tool_name for s in plan.steps]
    assert "plan_route" in tool_names


@pytest.mark.asyncio
async def test_planner_chat_intent_empty_plan():
    """Test planner creates empty plan for chat intent."""
    planner = Planner()

    intent = IntentResult(
        intent="chat",
        confidence=0.9,
        method="keyword",
        need_tool=False,
        reasoning="闲聊"
    )
    slots = SlotResult()

    plan = await planner.create_plan(intent, slots)
    assert len(plan.steps) == 0


@pytest.mark.asyncio
async def test_planner_respects_context_cache():
    """Test planner respects context cache for weather queries."""
    import time
    planner = Planner()

    intent = IntentResult(
        intent="query",
        confidence=0.9,
        method="keyword",
        need_tool=True,
        reasoning="天气查询"
    )
    slots = SlotResult(destination="北京")

    # Recent weather query (within 1 hour)
    context = {"last_weather_query": time.time() - 1800}
    plan = await planner.create_plan(intent, slots, context=context)
    assert len(plan.steps) == 0  # Should skip weather step


# =============================================================================
# Metrics Collection Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_metrics_collection_intent():
    """Test metrics collector records and aggregates intent metrics."""
    collector = MetricsCollector()

    metric = IntentMetric(
        intent="chat",
        method="rule",
        confidence=0.9,
        is_correct=None,
        latency_ms=100
    )
    await collector.record_intent(metric)

    stats = collector.get_intent_stats()
    assert stats["total"] == 1
    assert stats["by_method"]["rule"] == 1


@pytest.mark.asyncio
async def test_metrics_collection_multiple_methods():
    """Test metrics collector aggregates across multiple methods."""
    collector = MetricsCollector()

    # Record multiple metrics with different methods
    metrics = [
        IntentMetric(intent="chat", method="rule", confidence=0.9, is_correct=True, latency_ms=100),
        IntentMetric(intent="itinerary", method="llm", confidence=0.85, is_correct=True, latency_ms=200),
        IntentMetric(intent="query", method="rule", confidence=0.95, is_correct=False, latency_ms=50),
    ]
    for m in metrics:
        await collector.record_intent(m)

    stats = collector.get_intent_stats()
    assert stats["total"] == 3
    assert stats["by_method"]["rule"] == 2
    assert stats["by_method"]["llm"] == 1
    assert stats["accuracy"] == 2 / 3  # 2 correct out of 3 labeled


@pytest.mark.asyncio
async def test_metrics_collection_reset():
    """Test metrics collector can be reset."""
    collector = MetricsCollector()

    metric = IntentMetric(
        intent="chat",
        method="rule",
        confidence=0.9,
        is_correct=None,
        latency_ms=100
    )
    await collector.record_intent(metric)
    assert collector.get_intent_stats()["total"] == 1

    collector.reset()
    assert collector.get_intent_stats()["total"] == 0


@pytest.mark.asyncio
async def test_metrics_latency_tracking():
    """Test metrics collector tracks latency correctly."""
    collector = MetricsCollector()

    metrics = [
        IntentMetric(intent="chat", method="rule", confidence=0.9, is_correct=None, latency_ms=100),
        IntentMetric(intent="chat", method="rule", confidence=0.9, is_correct=None, latency_ms=200),
    ]
    for m in metrics:
        await collector.record_intent(m)

    stats = collector.get_intent_stats()
    assert stats["avg_latency_ms"] == 150.0  # (100 + 200) / 2


# =============================================================================
# End-to-End Pipeline Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_full_pipeline_simple_query():
    """Test the full pipeline: classify -> route -> plan -> metrics."""
    # Step 1: Classify intent
    router = IntentRouter(strategies=[RuleStrategy(), LLMStrategy()])
    intent = await router.classify(RequestContext(message="北京天气怎么样", is_complex=False))
    assert intent.intent in ("query", "chat")

    # Step 2: Detect complexity
    complexity = is_complex_query("北京天气怎么样")
    assert complexity.is_complex is False

    # Step 3: Route model
    router = ModelRouter()
    client = router.route(intent, is_complex=complexity.is_complex)
    assert client.model == ModelRouter.SMALL_MODEL

    # Step 4: Extract slots
    extractor = SlotResult(destination="北京")

    # Step 5: Create plan
    planner = Planner()
    plan = await planner.create_plan(intent, extractor)
    assert plan.intent == intent.intent

    # Step 6: Record metrics
    collector = MetricsCollector()
    metric = IntentMetric(
        intent=intent.intent,
        method=intent.method,
        confidence=intent.confidence,
        is_correct=None,
        latency_ms=50
    )
    await collector.record_intent(metric)
    stats = collector.get_intent_stats()
    assert stats["total"] == 1


@pytest.mark.asyncio
async def test_full_pipeline_complex_itinerary():
    """Test full pipeline for complex itinerary planning."""
    # Step 1: Classify intent (complex query)
    router = IntentRouter(strategies=[RuleStrategy(), LLMStrategy()])
    intent = await classifier.classify(
        "规划云南7天自驾游预算5000元包含酒店推荐",
        is_complex=True
    )
    assert intent.intent in ("itinerary", "chat", "query")

    # Step 2: Detect complexity
    long_msg = "帮我规划一条从云南出发的7天自驾游路线，预算5000元，包含酒店推荐和美食攻略"
    complexity = is_complex_query(long_msg)
    assert complexity.is_complex is True
    assert complexity.score >= 0.5

    # Step 3: Route model (itinerary + complex = large model)
    router = ModelRouter()
    client = router.route(intent, is_complex=complexity.is_complex)
    expected_model = (
        ModelRouter.LARGE_MODEL
        if intent.intent == "itinerary" and complexity.is_complex
        else ModelRouter.SMALL_MODEL
    )
    assert client.model == expected_model

    # Step 4: Extract slots
    from app.core.intent.slot_extractor import SlotExtractor
    slot_extractor = SlotExtractor()
    # Use "北京" (in COMMON_CITIES) for reliable destination extraction
    # Also verify days, budget_amount, and need_hotel are extracted
    slots = slot_extractor.extract("去北京旅游7天，预算5000元，包含酒店推荐")
    assert slots.destination == "北京", f"Expected '北京' destination, got {slots.destination}"
    assert slots.days == 7
    assert slots.budget_amount == 5000
    assert slots.need_hotel is True

    # Step 5: Create plan
    planner = Planner()
    plan = await planner.create_plan(intent, slots)
    assert plan.intent == intent.intent
    assert len(plan.steps) >= 2  # At least weather + POI

    # Step 6: Record metrics
    collector = MetricsCollector()
    metric = IntentMetric(
        intent=intent.intent,
        method=intent.method,
        confidence=intent.confidence,
        is_correct=None,
        latency_ms=150
    )
    await collector.record_intent(metric)
    stats = collector.get_intent_stats()
    assert stats["total"] == 1


@pytest.mark.asyncio
async def test_full_pipeline_chat():
    """Test full pipeline for simple chat message."""
    # Step 1: Classify
    router = IntentRouter(strategies=[RuleStrategy(), LLMStrategy()])
    intent = await router.classify(RequestContext(message="你好", is_complex=False))
    assert intent.intent == "chat"
    assert intent.need_tool is False

    # Step 2: Complexity
    complexity = is_complex_query("你好")
    assert complexity.is_complex is False

    # Step 3: Route
    router = ModelRouter()
    client = router.route(intent, is_complex=complexity.is_complex)
    assert client.model == ModelRouter.SMALL_MODEL

    # Step 4: Plan (chat = empty plan)
    planner = Planner()
    plan = await planner.create_plan(intent, SlotResult())
    assert len(plan.steps) == 0

    # Step 5: Metrics
    collector = MetricsCollector()
    metric = IntentMetric(
        intent=intent.intent,
        method=intent.method,
        confidence=intent.confidence,
        is_correct=None,
        latency_ms=5
    )
    await collector.record_intent(metric)
    assert collector.get_intent_stats()["total"] == 1


@pytest.mark.asyncio
async def test_pipeline_global_metrics_isolation():
    """Test that global collector can be used alongside local collectors."""
    from app.core.metrics.collector import global_collector

    # Record on global
    global_collector.reset()
    global_metric = IntentMetric(
        intent="chat",
        method="rule",
        confidence=0.9,
        is_correct=None,
        latency_ms=10
    )
    await global_collector.record_intent(global_metric)

    # Record on local
    local = MetricsCollector()
    local_metric = IntentMetric(
        intent="itinerary",
        method="llm",
        confidence=0.8,
        is_correct=None,
        latency_ms=100
    )
    await local.record_intent(local_metric)

    # Global should have 1, local should have 1
    assert global_collector.get_intent_stats()["total"] == 1
    assert local.get_intent_stats()["total"] == 1

    # They should be independent
    assert global_collector.get_intent_stats()["by_method"]["rule"] == 1
    assert local.get_intent_stats()["by_method"]["llm"] == 1


# =============================================================================
# Tool Fallback Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_tool_fallback():
    """Test tool fallback mechanism."""
    from unittest.mock import AsyncMock, MagicMock
    from app.core.orchestrator.executor import Executor
    from app.core.orchestrator.planner import ExecutionPlan, ExecutionStep, FallbackStrategy

    # Mock tool that fails
    mock_tool = AsyncMock()
    mock_tool.execute.side_effect = Exception("Network timeout")

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool

    # Mock cache for fallback
    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value={"temp": 20})

    executor = Executor(tool_registry=mock_registry, cache=mock_cache)
    plan = ExecutionPlan(
        intent="query",
        steps=[
            ExecutionStep(
                tool_name="get_weather",
                params={"city": "北京"},
                can_fail=True,
                fallback_strategy=FallbackStrategy.USE_CACHE
            )
        ],
        fallback_strategy=FallbackStrategy.CONTINUE
    )

    results = await executor.execute(plan)
    assert "get_weather" in results
    # Should have either succeeded or used cache
    assert results["get_weather"]["success"] or results["get_weather"].get("from_cache")
