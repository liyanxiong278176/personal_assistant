"""Tests for LLMFallbackStrategy

Tests:
- test_llm_fallback_classify - With mocked LLM
- test_llm_fallback_priority - Returns 100
- test_llm_fallback_cost - Returns > 0
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.context import RequestContext
from app.core.intent.classifier import IntentResult
from app.core.intent.strategies.llm_fallback import LLMFallbackStrategy


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.fixture
def llm_fallback_strategy(mock_llm_client):
    """Create LLMFallbackStrategy with mocked LLM."""
    return LLMFallbackStrategy(llm_client=mock_llm_client)


@pytest.mark.asyncio
async def test_llm_fallback_classify(llm_fallback_strategy, mock_llm_client):
    """Test classification with mocked LLM."""
    # Mock LLM response
    mock_llm_client.chat.return_value = '{"intent": "itinerary", "confidence": 0.9}'

    # Create context
    context = RequestContext(message="帮我规划一个三天的北京行程")

    # Classify
    result = await llm_fallback_strategy.classify(context)

    # Assertions
    assert isinstance(result, IntentResult)
    assert result.intent == "itinerary"
    assert result.confidence == 0.9
    assert result.method == "llm"
    assert "LLM classified as" in result.reasoning

    # Verify LLM was called
    mock_llm_client.chat.assert_called_once()
    call_args = mock_llm_client.chat.call_args
    assert "messages" in call_args.kwargs
    assert call_args.kwargs["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_llm_fallback_classify_query(llm_fallback_strategy, mock_llm_client):
    """Test classification for query intent."""
    mock_llm_client.chat.return_value = '{"intent": "query", "confidence": 0.85}'

    context = RequestContext(message="北京明天天气怎么样")
    result = await llm_fallback_strategy.classify(context)

    assert result.intent == "query"
    assert result.confidence == 0.85


@pytest.mark.asyncio
async def test_llm_fallback_classify_chat(llm_fallback_strategy, mock_llm_client):
    """Test classification for chat intent."""
    mock_llm_client.chat.return_value = '{"intent": "chat", "confidence": 0.95}'

    context = RequestContext(message="你好呀")
    result = await llm_fallback_strategy.classify(context)

    assert result.intent == "chat"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_llm_fallback_classify_image(llm_fallback_strategy, mock_llm_client):
    """Test classification for image intent."""
    mock_llm_client.chat.return_value = '{"intent": "image", "confidence": 0.8}'

    context = RequestContext(message="这张图片是什么地方")
    result = await llm_fallback_strategy.classify(context)

    assert result.intent == "image"
    assert result.confidence == 0.8


@pytest.mark.asyncio
async def test_llm_fallback_no_llm_client():
    """Test behavior when no LLM client is provided."""
    strategy = LLMFallbackStrategy(llm_client=None)
    context = RequestContext(message="test message")

    result = await strategy.classify(context)

    assert result.intent == "chat"
    assert result.confidence == 0.5
    assert result.method == "llm"
    assert "No LLM client available" in result.reasoning


@pytest.mark.asyncio
async def test_llm_fallback_llm_failure(llm_fallback_strategy, mock_llm_client):
    """Test behavior when LLM call fails."""
    # Mock LLM to raise exception
    mock_llm_client.chat.side_effect = Exception("API error")

    context = RequestContext(message="test message")
    result = await llm_fallback_strategy.classify(context)

    assert result.intent == "chat"
    assert result.confidence == 0.5
    assert result.method == "llm"
    assert "LLM call failed" in result.reasoning


@pytest.mark.asyncio
async def test_llm_fallback_invalid_json(llm_fallback_strategy, mock_llm_client):
    """Test behavior when LLM returns invalid JSON."""
    mock_llm_client.chat.return_value = "This is not valid JSON"

    context = RequestContext(message="test message")
    result = await llm_fallback_strategy.classify(context)

    assert result.intent == "chat"
    assert result.confidence == 0.5
    assert "Failed to parse LLM response" in result.reasoning


@pytest.mark.asyncio
async def test_llm_fallback_json_in_markdown(llm_fallback_strategy, mock_llm_client):
    """Test parsing JSON response in markdown code blocks."""
    mock_llm_client.chat.return_value = '''```json
{
    "intent": "itinerary",
    "confidence": 0.95
}
```'''

    context = RequestContext(message="帮我规划行程")
    result = await llm_fallback_strategy.classify(context)

    assert result.intent == "itinerary"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_llm_fallback_can_handle(llm_fallback_strategy):
    """Test that can_handle always returns True."""
    context = RequestContext(message="any message")
    result = await llm_fallback_strategy.can_handle(context)
    assert result is True


def test_llm_fallback_priority(llm_fallback_strategy):
    """Test that priority returns 100."""
    assert llm_fallback_strategy.priority == 100


def test_llm_fallback_cost_default(llm_fallback_strategy):
    """Test that estimated_cost returns default value."""
    assert llm_fallback_strategy.estimated_cost() == 300.0


def test_llm_fallback_cost_custom():
    """Test that estimated_cost returns custom value."""
    strategy = LLMFallbackStrategy(llm_client=None, token_cost=500.0)
    assert strategy.estimated_cost() == 500.0


def test_llm_fallback_cost_positive(llm_fallback_strategy):
    """Test that estimated_cost returns > 0."""
    assert llm_fallback_strategy.estimated_cost() > 0


@pytest.mark.asyncio
async def test_llm_fallback_partial_json(llm_fallback_strategy, mock_llm_client):
    """Test parsing partial JSON with regex fallback."""
    mock_llm_client.chat.return_value = 'Some text before {"intent": "query", "confidence": 0.75} some text after'

    context = RequestContext(message="test message")
    result = await llm_fallback_strategy.classify(context)

    assert result.intent == "query"
    assert result.confidence == 0.75
