"""Integration tests for QueryEngine with IntentRouter and PromptConfigLoader.

Verifies that QueryEngine correctly accepts and stores the new
service parameters (intent_router, prompt_service, memory_service),
automatically creates an IntentRouter when none is provided, and
integrates the hot-reload PromptConfigLoader system.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from app.core.query_engine import QueryEngine
from app.core.intent import IntentRouter
from app.core.context import RequestContext
from app.core.prompts.loader import PromptConfigLoader
from app.core.prompts.service import PromptService


# =============================================================================
# Helper: Mock IntentRouter
# =============================================================================

def _make_mock_intent_router():
    router = MagicMock(spec=IntentRouter)
    router.classify = AsyncMock()
    return router


# =============================================================================
# Helper: Mock PromptService
# =============================================================================

def _make_mock_prompt_service():
    svc = MagicMock()
    svc.render = AsyncMock()
    svc.render_safe = AsyncMock()
    return svc


# =============================================================================
# Test: New services stored as instance variables
# =============================================================================

def test_query_engine_stores_new_service_params():
    """QueryEngine stores intent_router, prompt_service, memory_service as instance vars."""
    mock_router = _make_mock_intent_router()
    mock_prompt_svc = _make_mock_prompt_service()
    mock_memory = MagicMock()

    engine = QueryEngine(
        intent_router=mock_router,
        prompt_service=mock_prompt_svc,
        memory_service=mock_memory,
    )

    assert engine._intent_router is mock_router
    assert engine._prompt_service is mock_prompt_svc
    assert engine._memory_service is mock_memory


# =============================================================================
# Test: IntentRouter auto-created when not provided
# =============================================================================

def test_query_engine_intent_router_auto_created():
    """When intent_router is not provided, QueryEngine auto-creates one."""
    engine = QueryEngine()

    # Router is auto-created
    assert engine._intent_router is not None
    assert isinstance(engine._intent_router, IntentRouter)


# =============================================================================
# Test: Uses router when configured
# =============================================================================

@pytest.mark.asyncio
async def test_query_engine_with_intent_router():
    """When intent_router is configured, it is stored and accessible."""
    mock_router = _make_mock_intent_router()
    mock_router.classify.return_value = MagicMock(
        intent="itinerary",
        confidence=0.95,
        method="rule",
        need_tool=True,
        strategy="MockRouter",
    )

    engine = QueryEngine(intent_router=mock_router)

    # Router is stored and can be accessed
    assert engine._intent_router is mock_router

    # New service can be called with RequestContext
    ctx = RequestContext(message="去云南旅行", user_id="test")
    result = await mock_router.classify(ctx)
    assert result.intent == "itinerary"
    assert result.confidence == 0.95
    mock_router.classify.assert_called_once()


# =============================================================================
# Test: Auto-created router classifies correctly
# =============================================================================

@pytest.mark.asyncio
async def test_query_engine_auto_router_classifies():
    """Auto-created IntentRouter with real strategies can classify intents."""
    engine = QueryEngine()

    ctx = RequestContext(message="你好", conversation_id="test", user_id="test")
    result = await engine._intent_router.classify(ctx)

    assert result.intent in ("chat", "query", "itinerary", "image")
    assert 0.0 <= result.confidence <= 1.0
    assert result.strategy is not None


# =============================================================================
# Test: PromptService stored correctly
# =============================================================================

def test_query_engine_prompt_service_stored():
    """PromptService is stored and accessible."""
    mock_svc = _make_mock_prompt_service()

    engine = QueryEngine(prompt_service=mock_svc)

    assert engine._prompt_service is mock_svc
    # Router should still be auto-created
    assert engine._intent_router is not None


# =============================================================================
# Test: MemoryService stored correctly
# =============================================================================

def test_query_engine_memory_service_stored():
    """MemoryService is stored and accessible."""
    mock_memory = MagicMock()
    mock_memory.get = MagicMock(return_value=[])

    engine = QueryEngine(memory_service=mock_memory)

    assert engine._memory_service is mock_memory


# =============================================================================
# Test: All three services together
# =============================================================================

def test_query_engine_all_three_services_together():
    """QueryEngine accepts all three new services simultaneously."""
    mock_router = _make_mock_intent_router()
    mock_prompt_svc = _make_mock_prompt_service()
    mock_memory = MagicMock()

    engine = QueryEngine(
        intent_router=mock_router,
        prompt_service=mock_prompt_svc,
        memory_service=mock_memory,
    )

    assert engine._intent_router is mock_router
    assert engine._prompt_service is mock_prompt_svc
    assert engine._memory_service is mock_memory


# =============================================================================
# Test: Backward compatibility (no new services)
# =============================================================================

def test_query_engine_backward_compatibility():
    """Existing callers that don't pass new params still work."""
    engine = QueryEngine()

    # All existing attributes still exist
    assert hasattr(engine, "llm_client")
    assert hasattr(engine, "_tool_registry")
    assert hasattr(engine, "_tool_executor")
    assert hasattr(engine, "_slot_extractor")
    assert hasattr(engine, "get_system_prompt")
    assert callable(engine.get_system_prompt)

    # Router is auto-created
    assert engine._intent_router is not None


# =============================================================================
# Test: PromptConfigLoader integration with QueryEngine
# =============================================================================

def _get_prompts_config_path() -> str:
    """Helper to get the prompts.yaml config file path."""
    # The tests are in tests/core/integration/, backend is in backend/app/core/
    # From tests/core/integration/, go up 3 levels to root, then into backend/app/core
    test_dir = Path(__file__).parent
    root_dir = test_dir.parent.parent.parent
    config_path = root_dir / "backend" / "app" / "core" / "prompts" / "config" / "prompts.yaml"
    return str(config_path)


def test_query_engine_with_prompt_config_loader():
    """QueryEngine creates PromptService with PromptConfigLoader when config_path is provided."""
    config_path = _get_prompts_config_path()

    engine = QueryEngine(prompt_config_path=config_path)

    # PromptService should be created with _LoaderProvider
    assert engine._prompt_service is not None
    assert isinstance(engine._prompt_service, PromptService)

    # The loader reference should be stored
    assert engine._prompt_loader is not None
    assert isinstance(engine._prompt_loader, PromptConfigLoader)

    # Cache stats should be accessible
    stats = engine._prompt_loader.get_cache_stats()
    assert "config_last_mtime" in stats
    assert "template_cache_size" in stats


@pytest.mark.asyncio
async def test_query_engine_hot_reload_renders_templates():
    """PromptService with _LoaderProvider can render templates for all intents."""
    config_path = _get_prompts_config_path()

    engine = QueryEngine(prompt_config_path=config_path)

    # Test that we can get templates via the provider
    provider = engine._prompt_service.provider
    intents = await provider.list_templates()

    # Should include all 8 intents from prompts.yaml
    expected_intents = {"itinerary", "query", "chat", "image", "hotel", "food", "budget", "transport"}
    assert expected_intents.issubset(set(intents))


# =============================================================================
# Test: 4 new intents (hotel, food, budget, transport)
# =============================================================================

@pytest.mark.parametrize("intent,query", [
    ("hotel", "帮我推荐一家酒店"),
    ("food", "有什么好吃的"),
    ("budget", "预算大概多少钱"),
    ("transport", "怎么去最方便"),
])
def test_new_intents_have_templates(intent, query):
    """All 4 new intents (hotel, food, budget, transport) have templates configured."""
    config_path = _get_prompts_config_path()

    loader = PromptConfigLoader(config_path=config_path)
    template = loader.get_template(intent)

    # Template should not be empty
    assert template
    assert len(template) > 0

    # Template should contain expected variables or content
    assert "你" in template or "请" in template or "帮助" in template


@pytest.mark.asyncio
@pytest.mark.parametrize("intent,expected_keywords", [
    ("hotel", ["酒店", "住宿", "推荐"]),
    ("food", ["美食", "餐厅", "推荐"]),
    ("budget", ["预算", "费用", "规划"]),
    ("transport", ["交通", "出行", "路线"]),
])
async def test_new_intents_render_with_context(intent, expected_keywords):
    """New intents can be rendered with RequestContext using PromptService."""
    config_path = _get_prompts_config_path()

    engine = QueryEngine(prompt_config_path=config_path)

    # Create a request context
    ctx = RequestContext(
        message="测试消息",
        user_id="test_user",
        conversation_id="test_conv",
        clarification_count=0
    )

    # Render should succeed (may have empty slots, etc.)
    result = await engine._prompt_service.render_safe(intent, ctx)

    # Should succeed
    assert result.success is True
    assert result.content

    # Content should contain relevant keywords
    content_lower = result.content.lower()
    assert any(kw.lower() in content_lower for kw in expected_keywords)


@pytest.mark.asyncio
async def test_hot_reload_cache_stats_accessible():
    """Cache statistics from PromptConfigLoader are accessible through QueryEngine."""
    config_path = _get_prompts_config_path()

    engine = QueryEngine(prompt_config_path=config_path)

    # Get cache stats
    stats = engine._prompt_loader.get_cache_stats()

    # Should have expected keys
    assert "config_last_mtime" in stats
    assert "template_cache_size" in stats
    assert "template_cached" in stats

    # Template cache should be a list
    assert isinstance(stats["template_cached"], list)

    # Clear cache should work
    engine._prompt_loader.clear_cache()
    stats_after = engine._prompt_loader.get_cache_stats()
    assert stats_after["template_cache_size"] == 0


# =============================================================================
# Test: Backward compatibility - no prompt_config_path
# =============================================================================

def test_query_engine_without_prompt_config_path():
    """When prompt_config_path is not provided, uses default TemplateProvider."""
    engine = QueryEngine()

    # PromptService should still be created
    assert engine._prompt_service is not None

    # But no loader reference
    assert engine._prompt_loader is None
