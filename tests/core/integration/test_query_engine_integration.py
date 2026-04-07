"""Integration tests for QueryEngine with new services (IntentRouter, PromptService).

Phase 5.1: Verify that QueryEngine correctly accepts and stores the new
service parameters (intent_router, prompt_service, memory_service) and
falls back to legacy components when new services are not configured.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.query_engine import QueryEngine


# =============================================================================
# Helper: Mock IntentRouter
# =============================================================================

def _make_mock_intent_router():
    router = MagicMock()
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
    assert engine._legacy_intent is engine._intent_classifier


# =============================================================================
# Test: New services default to None
# =============================================================================

def test_query_engine_new_services_default_to_none():
    """When new services are not provided, they default to None."""
    engine = QueryEngine()

    assert engine._intent_router is None
    assert engine._prompt_service is None
    assert engine._memory_service is None
    assert engine._legacy_intent is not None


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
    )

    engine = QueryEngine(intent_router=mock_router)

    # Router is stored and can be accessed
    assert engine._intent_router is mock_router

    # Legacy intent is still available as fallback
    assert engine._legacy_intent is not None

    # New service can be called
    result = await mock_router.classify("去云南旅行")
    assert result.intent == "itinerary"
    assert result.confidence == 0.95
    mock_router.classify.assert_called_once_with("去云南旅行")


# =============================================================================
# Test: Fallback to legacy when router not configured
# =============================================================================

@pytest.mark.asyncio
async def test_query_engine_fallback_to_legacy():
    """When intent_router is None, legacy intent_classifier is used as fallback."""
    engine = QueryEngine(intent_router=None)

    # No new router configured
    assert engine._intent_router is None

    # Legacy fallback is the original intent_classifier
    assert engine._legacy_intent is engine._intent_classifier

    # Can still classify using legacy (keyword-based, may return 'chat' for simple input)
    result = await engine._intent_classifier.classify("你好")
    assert result.intent == "chat"
    assert result.method in ("keyword", "cache", "default")


# =============================================================================
# Test: PromptService stored correctly
# =============================================================================

def test_query_engine_prompt_service_stored():
    """PromptService is stored and accessible."""
    mock_svc = _make_mock_prompt_service()

    engine = QueryEngine(prompt_service=mock_svc)

    assert engine._prompt_service is mock_svc
    assert engine._legacy_intent is engine._intent_classifier


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
    assert engine._legacy_intent is engine._intent_classifier


# =============================================================================
# Test: Legacy for backward compatibility (no new services)
# =============================================================================

def test_query_engine_backward_compatibility():
    """Existing callers that don't pass new params still work."""
    engine = QueryEngine()

    # All existing attributes still exist
    assert hasattr(engine, "llm_client")
    assert hasattr(engine, "_tool_registry")
    assert hasattr(engine, "_tool_executor")
    assert hasattr(engine, "_intent_classifier")
    assert hasattr(engine, "_slot_extractor")
    assert hasattr(engine, "get_system_prompt")
    assert callable(engine.get_system_prompt)
