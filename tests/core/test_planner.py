import pytest
from app.core.orchestrator.planner import Planner, ExecutionPlan, ExecutionStep, FallbackStrategy
from app.core.context import IntentResult
from app.core.intent.slot_extractor import SlotResult


@pytest.mark.asyncio
async def test_weather_query_creates_single_step_plan():
    """天气查询应该生成单步计划"""
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
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "get_weather"
    assert plan.steps[0].params == {"city": "北京"}


@pytest.mark.asyncio
async def test_itinerary_creates_multi_step_plan():
    """行程规划应该生成多步计划"""
    planner = Planner()
    intent = IntentResult(
        intent="itinerary",
        confidence=0.8,
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
    assert len(plan.steps) >= 2  # 天气 + 景点
    tool_names = [s.tool_name for s in plan.steps]
    assert "get_weather" in tool_names
    assert "search_poi" in tool_names


@pytest.mark.asyncio
async def test_itinerary_with_multiple_destinations_includes_route():
    """多目的地行程应该包含路线规划"""
    planner = Planner()
    intent = IntentResult(
        intent="itinerary",
        confidence=0.85,
        method="llm",
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
async def test_chat_intent_creates_empty_plan():
    """聊天意图应该生成空计划"""
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
    assert plan.fallback_strategy == FallbackStrategy.FAIL_FAST


@pytest.mark.asyncio
async def test_image_intent_creates_empty_plan():
    """图片意图应该生成空计划（由其他组件处理）"""
    planner = Planner()
    intent = IntentResult(
        intent="image",
        confidence=1.0,
        method="attachment",
        need_tool=True,
        reasoning="图片识别"
    )
    slots = SlotResult()

    plan = await planner.create_plan(intent, slots)
    assert len(plan.steps) == 0


@pytest.mark.asyncio
async def test_execution_step_has_correct_defaults():
    """执行步骤应该有正确的默认值"""
    step = ExecutionStep(
        tool_name="get_weather",
        params={"city": "北京"}
    )
    assert step.dependencies == []
    assert step.can_fail is False
    assert step.timeout_ms == 5000
    assert step.fallback_strategy == FallbackStrategy.CONTINUE


@pytest.mark.asyncio
async def test_execution_plan_contains_intent():
    """执行计划应该包含原始意图类型"""
    planner = Planner()
    intent = IntentResult(
        intent="itinerary",
        confidence=0.8,
        method="llm",
        need_tool=True,
        reasoning="行程"
    )
    slots = SlotResult(destination="成都", days=3)

    plan = await planner.create_plan(intent, slots)
    assert plan.intent == "itinerary"


@pytest.mark.asyncio
async def test_weather_query_respects_context_cache():
    """天气查询应尊重上下文中的缓存（不重复查询）"""
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

    # 刚刚查过天气，1小时内不应重复查询
    context = {
        "last_weather_query": time.time() - 1800  # 30分钟前
    }

    plan = await planner.create_plan(intent, slots, context=context)
    assert len(plan.steps) == 0  # 应该跳过天气查询


@pytest.mark.asyncio
async def test_weather_query_outside_cache_window_queries():
    """天气查询在缓存过期后应该重新查询"""
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

    # 2小时前查过，缓存已过期
    context = {
        "last_weather_query": time.time() - 7200
    }

    plan = await planner.create_plan(intent, slots, context=context)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "get_weather"
