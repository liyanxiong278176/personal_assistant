"""Tests for RequestContext prompt enhancement fields.

Tests the new fields: intent, output_format, examples_enabled, few_shot_count.
"""

import pytest

from app.core.context import RequestContext


class TestRequestContextNewFields:
    """Test new prompt enhancement fields in RequestContext."""

    def test_request_context_new_fields(self):
        """New fields intent/output_format/examples_enabled/few_shot_count."""
        ctx = RequestContext(
            message="我想去杭州玩",
            intent="itinerary",
            output_format="structured",
            examples_enabled=True,
            few_shot_count=3,
        )
        assert ctx.intent == "itinerary"
        assert ctx.output_format == "structured"
        assert ctx.examples_enabled is True
        assert ctx.few_shot_count == 3

    def test_request_context_default_values(self):
        """New fields have default values, don't break existing code."""
        ctx = RequestContext(message="测试")
        assert ctx.intent is None
        assert ctx.output_format is None
        assert ctx.examples_enabled is True
        assert ctx.few_shot_count == 3

    def test_request_context_partial_new_fields(self):
        """Can set some new fields and leave others at defaults."""
        ctx = RequestContext(
            message="测试",
            intent="query",
            output_format="json",
        )
        assert ctx.intent == "query"
        assert ctx.output_format == "json"
        assert ctx.examples_enabled is True  # default
        assert ctx.few_shot_count == 3  # default

    def test_request_context_examples_disabled(self):
        """Can disable few-shot examples."""
        ctx = RequestContext(
            message="测试",
            examples_enabled=False,
        )
        assert ctx.examples_enabled is False
        assert ctx.few_shot_count == 3  # still has default

    def test_request_context_custom_few_shot_count(self):
        """Can customize few-shot example count."""
        ctx = RequestContext(
            message="测试",
            few_shot_count=5,
        )
        assert ctx.few_shot_count == 5
        assert ctx.examples_enabled is True  # default

    def test_request_context_output_format_free(self):
        """Can set output_format to free text."""
        ctx = RequestContext(
            message="测试",
            output_format="free",
        )
        assert ctx.output_format == "free"

    def test_request_context_update_preserves_new_fields(self):
        """update() method preserves new fields."""
        ctx = RequestContext(
            message="原始消息",
            intent="itinerary",
            output_format="structured",
        )
        updated = ctx.update(message="新消息")
        assert updated.intent == "itinerary"
        assert updated.output_format == "structured"
        assert updated.message == "新消息"

    def test_request_context_update_can_change_new_fields(self):
        """update() can change new field values."""
        ctx = RequestContext(
            message="测试",
            intent="query",
        )
        updated = ctx.update(intent="itinerary", few_shot_count=5)
        assert updated.intent == "itinerary"
        assert updated.few_shot_count == 5