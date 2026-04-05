import pytest
from app.core.orchestrator.model_router import ModelRouter
from app.core.intent.classifier import IntentResult

@pytest.mark.asyncio
async def test_simple_chat_uses_small_model():
    router = ModelRouter()
    intent = IntentResult(intent="chat", confidence=0.9, method="keyword", need_tool=False)
    client = router.route(intent, is_complex=False)
    assert client.model == ModelRouter.SMALL_MODEL

@pytest.mark.asyncio
async def test_complex_itinerary_uses_large_model():
    router = ModelRouter()
    intent = IntentResult(intent="itinerary", confidence=0.8, method="llm", need_tool=True)
    client = router.route(intent, is_complex=True)
    assert client.model == ModelRouter.LARGE_MODEL

@pytest.mark.asyncio
async def test_simple_itinerary_uses_small_model():
    router = ModelRouter()
    intent = IntentResult(intent="itinerary", confidence=0.9, method="keyword", need_tool=True)
    client = router.route(intent, is_complex=False)
    assert client.model == ModelRouter.SMALL_MODEL
