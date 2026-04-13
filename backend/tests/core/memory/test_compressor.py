# backend/tests/core/memory/test_compressor.py
"""Tests for ConversationCompressor."""
import asyncio
import pytest
import re
from unittest.mock import AsyncMock
from app.core.memory.compressor import (
    ConversationCompressor,
    SlotExtractionTemplate,
    TRAVEL_TEMPLATES,
    GENERIC_TEMPLATES,
)


class TestSlotExtractionTemplate:
    """Tests for SlotExtractionTemplate."""

    def test_compile_returns_pattern(self):
        """compile() should return a compiled regex pattern."""
        template = SlotExtractionTemplate("test", r"(\d+)", "数字")
        pattern = template.compile()

        match = pattern.search("我有123元")
        assert match is not None
        assert match.group(1) == "123"

    def test_compile_with_flags(self):
        """compile() should support regex flags."""
        template = SlotExtractionTemplate("test", r"hello", "问候", flags=re.IGNORECASE)
        pattern = template.compile()

        assert pattern.search("HELLO") is not None


class TestConversationCompressor:
    """Tests for ConversationCompressor."""

    def test_extract_slots_travel(self):
        """Should extract travel-related slots correctly."""
        compressor = ConversationCompressor(AsyncMock())

        result = compressor._extract_slots("我预算5000元，5月1日去北京旅游，计划待3天")

        assert "预算: 5000" in result or "预算: 5000元" in result
        assert "时间: 5月1日" in result or "时间: 5/1" in result or "时间: 1日" in result
        assert "目的地: 北京" in result

    def test_extract_slots_empty(self):
        """Should return empty string for non-matching content."""
        compressor = ConversationCompressor(AsyncMock())

        result = compressor._extract_slots("你好")

        assert result == ""

    def test_extract_slots_with_generic_templates(self):
        """Should work with generic templates."""
        compressor = ConversationCompressor(AsyncMock(), slot_templates=GENERIC_TEMPLATES)

        result = compressor._extract_slots("价格 99.99 元，联系 test@example.com")

        assert "数字: 99.99" in result or "数字: 99" in result
        assert "邮箱: test@example.com" in result

    @pytest.mark.asyncio
    async def test_compress_no_change_under_limit(self):
        """Messages under recent_limit should be returned unchanged."""
        llm = AsyncMock()
        compressor = ConversationCompressor(llm)

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]

        result = await compressor.compress(messages)

        assert result == messages
        llm.chat.assert_not_awaited()  # No LLM call needed

    @pytest.mark.asyncio
    async def test_compress_three_levels(self):
        """Should apply all three compression levels correctly."""
        llm = AsyncMock()
        llm.chat.return_value = "用户计划5月去北京旅游，预算5000元。"
        compressor = ConversationCompressor(llm, recent_limit=3, mid_limit=10)

        # Create 25 messages: 3 recent + 7 mid + 15 old
        messages = [{"role": "user", "content": f"消息{i}"} for i in range(25)]

        result = await compressor.compress(messages)

        # Level 1: 3 recent messages preserved
        recent_full = [m for m in result if not m.get("_compressed")]
        assert len(recent_full) == 3

        # Level 3: At least one summary
        summary = [m for m in result if m["role"] == "system"]
        assert len(summary) >= 1

        # Total should be <= original
        assert len(result) <= len(messages)

    @pytest.mark.asyncio
    async def test_compress_slot_extraction(self):
        """Mid-range messages should be compressed to slots."""
        llm = AsyncMock()
        compressor = ConversationCompressor(llm, recent_limit=2, mid_limit=5)

        messages = [
            {"role": "user", "content": "预算5000元"},
            {"role": "user", "content": "去上海"},
            {"role": "user", "content": "待7天"},
            {"role": "user", "content": "6月1日出发"},
            {"role": "user", "content": "最近消息"},
        ]

        result = await compressor.compress(messages)

        # Messages 3 mid messages should be slot-compressed
        compressed = [m for m in result if m.get("_compressed")]
        # Since mid_limit=5 and len=5, no old/summary
        # recent_limit=2, so mid = messages[0:3] = 3 messages slot-compressed
        assert len(compressed) >= 3  # slot-extracted mid messages

    @pytest.mark.asyncio
    async def test_summarize_timeout_fallback(self):
        """LLM timeout should fallback gracefully."""
        llm = AsyncMock()
        llm.chat.side_effect = asyncio.TimeoutError()

        compressor = ConversationCompressor(llm, llm_timeout=0.1, recent_limit=2, mid_limit=3)

        messages = [{"role": "user", "content": f"old{i}"} for i in range(5)]

        result = await compressor.compress(messages)

        # Should contain the fallback text
        assert any("早期对话已压缩" in m.get("content", "") for m in result)

    def test_set_slot_templates(self):
        """Should update slot templates dynamically."""
        compressor = ConversationCompressor(AsyncMock())

        new_templates = [
            SlotExtractionTemplate("test", r"(\w+)", "词"),
        ]

        compressor.set_slot_templates(new_templates)

        assert len(compressor._slot_templates) == 1
        assert compressor._slot_templates[0].name == "test"

        # Should extract using new templates
        result = compressor._extract_slots("hello world")
        assert "词: hello" in result
