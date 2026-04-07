"""Tests for IPromptFilter interface

Tests the prompt filter interface that provides the foundation for
SecurityFilter, Validator, and Compressor filters.
"""

import pytest

from app.core.context import RequestContext
from app.core.prompts.pipeline.base import IPromptFilter
from app.core.prompts.providers.base import PromptFilterResult


class DummyFilter(IPromptFilter):
    """Dummy filter implementation for testing"""

    async def process(
        self,
        prompt: str,
        context: RequestContext,
    ) -> PromptFilterResult:
        return PromptFilterResult(
            success=True,
            content=prompt.upper(),
        )


class AnotherFilter(IPromptFilter):
    """Another filter implementation that modifies content"""

    async def process(
        self,
        prompt: str,
        context: RequestContext,
    ) -> PromptFilterResult:
        return PromptFilterResult(
            success=True,
            content=f"PROCESSED: {prompt}",
            warning="This is a test warning",
        )


class FailingFilter(IPromptFilter):
    """Filter that always fails"""

    async def process(
        self,
        prompt: str,
        context: RequestContext,
    ) -> PromptFilterResult:
        return PromptFilterResult(
            success=False,
            content="",
            error="Filter failed intentionally",
            should_fallback=True,
        )


@pytest.mark.asyncio
async def test_filter_interface_basic():
    """Test that IPromptFilter interface works as expected"""
    filter_obj = DummyFilter()
    context = RequestContext(message="test message")

    result = await filter_obj.process("hello world", context)

    assert result.success is True
    assert result.content == "HELLO WORLD"
    assert result.error is None
    assert result.warning is None


@pytest.mark.asyncio
async def test_filter_interface_with_warning():
    """Test filter that produces a warning"""
    filter_obj = AnotherFilter()
    context = RequestContext(message="test")

    result = await filter_obj.process("test prompt", context)

    assert result.success is True
    assert result.content == "PROCESSED: test prompt"
    assert result.warning == "This is a test warning"


@pytest.mark.asyncio
async def test_filter_interface_failure():
    """Test filter that fails"""
    filter_obj = FailingFilter()
    context = RequestContext(message="test")

    result = await filter_obj.process("any input", context)

    assert result.success is False
    assert result.content == ""
    assert result.error == "Filter failed intentionally"
    assert result.should_fallback is True


@pytest.mark.asyncio
async def test_filter_interface_with_context():
    """Test that filter receives and can use RequestContext"""
    filter_obj = DummyFilter()

    context = RequestContext(
        message="user message",
        user_id="user123",
        conversation_id="conv456",
        max_tokens=8000,
    )

    result = await filter_obj.process("test", context)

    # Verify filter processed successfully
    assert result.success is True
    assert result.content == "TEST"


@pytest.mark.asyncio
async def test_filter_chain_execution():
    """Test executing multiple filters in sequence"""
    filters = [
        DummyFilter(),  # Converts to uppercase
        AnotherFilter(),  # Prepends "PROCESSED: "
    ]
    context = RequestContext(message="test")

    content = "hello"
    for filter_obj in filters:
        result = await filter_obj.process(content, context)
        if not result.success:
            break
        content = result.content

    assert content == "PROCESSED: HELLO"


def test_filter_is_abstract():
    """Test that IPromptFilter cannot be instantiated directly"""
    with pytest.raises(TypeError):
        IPromptFilter()
