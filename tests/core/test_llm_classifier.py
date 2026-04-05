"""Tests for LLM Intent Classifier"""

import pytest
from app.core.intent.llm_classifier import LLMIntentClassifier
from app.core.intent.classifier import IntentResult


@pytest.mark.asyncio
async def test_llm_classifier_returns_intent():
    """Test LLM classifier returns valid intent"""
    from unittest.mock import AsyncMock, MagicMock

    mock_client = AsyncMock()
    mock_client.chat.return_value = '{"intent": "itinerary", "need_tool": true, "confidence": 0.9}'

    classifier = LLMIntentClassifier(llm_client=mock_client)
    result = await classifier.classify("帮我规划一下行程")

    assert result.intent in ["itinerary", "query", "chat"]
    assert result.method == "llm"
    assert hasattr(result, "need_tool")


@pytest.mark.asyncio
async def test_llm_classifier_with_image():
    """Test LLM classifier returns image intent when has_image is True"""
    classifier = LLMIntentClassifier(llm_client=None)
    result = await classifier.classify("看看这张图片", has_image=True)

    assert result.intent == "image"
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_llm_classifier_fallback_on_no_client():
    """Test LLM classifier fallback when client is None"""
    classifier = LLMIntentClassifier(llm_client=None)
    result = await classifier.classify("你好")

    assert result.intent == "chat"
    assert result.method == "llm"


@pytest.mark.asyncio
async def test_llm_classifier_error_handling():
    """Test LLM classifier handles API errors gracefully"""
    from unittest.mock import AsyncMock

    mock_client = AsyncMock()
    mock_client.chat.side_effect = Exception("API error")

    classifier = LLMIntentClassifier(llm_client=mock_client)
    result = await classifier.classify("测试消息")

    assert result.intent == "chat"
    assert result.method == "llm"
    assert result.confidence == 0.3
