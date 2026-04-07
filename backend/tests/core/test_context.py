"""Tests for RequestContext shared context object"""

import pytest
from app.core.context import RequestContext
from app.core.intent.slot_extractor import SlotResult


def test_request_context_basic():
    """Test basic RequestContext creation"""
    context = RequestContext(
        message="帮我规划去北京的三天行程",
        user_id="test_user",
        conversation_id="test_conv"
    )
    assert context.message == "帮我规划去北京的三天行程"
    assert context.user_id == "test_user"
    assert context.conversation_id == "test_conv"
    assert context.clarification_count == 0


def test_request_context_update():
    """Test context update method"""
    context = RequestContext(message="test")
    updated = context.update(slots=SlotResult(destination="北京"))
    assert updated.slots.destination == "北京"
    assert context.slots is None  # Original unchanged
