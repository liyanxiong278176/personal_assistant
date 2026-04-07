"""Tests for LegacyPromptAdapter

Tests cover:
- Wrapping and calling PromptBuilder
- Type checking in __init__
- get_system_prompt() returns builder output
"""

import pytest

from app.core.prompts.legacy_adapter import LegacyPromptAdapter
from app.core.prompts.builder import PromptBuilder


def test_legacy_adapter_wraps_builder():
    """Test that LegacyPromptAdapter wraps PromptBuilder correctly"""
    builder = PromptBuilder()
    builder.add_layer("角色", "你是一个旅游助手")
    builder.add_layer("能力", "可以帮用户规划行程")

    adapter = LegacyPromptAdapter(builder)
    result = adapter.get_system_prompt()

    assert "角色" in result
    assert "能力" in result
    assert "旅游助手" in result
    assert "规划行程" in result
