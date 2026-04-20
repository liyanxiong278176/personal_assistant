"""Tests for TemplateContext dataclass"""
import pytest
from app.core.prompts.context import TemplateContext
from app.core.intent.slot_extractor import SlotResult


def test_template_context_creation():
    """Test TemplateContext can be created with all fields"""
    ctx = TemplateContext(
        intent="itinerary",
        slots=SlotResult(destination="北京", days=3),
        tool_results={"weather": {"temp": "25°C"}},
        context="测试上下文",
        user_message="帮我规划北京行程",
        memories="用户偏好历史景点",
        user_id="user-001",
        conversation_id="conv-001"
    )

    assert ctx.intent == "itinerary"
    assert ctx.slots.destination == "北京"
    assert ctx.slots.days == 3
    assert ctx.tool_results == {"weather": {"temp": "25°C"}}
    assert ctx.context == "测试上下文"
    assert ctx.user_message == "帮我规划北京行程"
    assert ctx.memories == "用户偏好历史景点"
    assert ctx.user_id == "user-001"
    assert ctx.conversation_id == "conv-001"


def test_template_context_optional_fields():
    """Test TemplateContext with optional fields omitted"""
    ctx = TemplateContext(
        intent="chat",
        slots=SlotResult(),
        tool_results={},
        context="",
        user_message="你好"
    )

    assert ctx.intent == "chat"
    assert ctx.memories is None
    assert ctx.user_id is None
    assert ctx.conversation_id is None


def test_to_template_vars_conversion():
    """Test to_template_vars() method returns correct dictionary"""
    ctx = TemplateContext(
        intent="query",
        slots=SlotResult(destination="上海"),
        tool_results={"data": {"result": "success"}},
        context="上下文内容",
        user_message="查询天气",
        memories="用户喜欢晴天",
        user_id="user-002",
        conversation_id="conv-002"
    )

    vars_dict = ctx.to_template_vars()

    assert vars_dict["user_message"] == "查询天气"
    assert vars_dict["slots"].destination == "上海"
    assert vars_dict["tool_results"] == {"data": {"result": "success"}}
    assert vars_dict["memories"] == "用户喜欢晴天"
    assert vars_dict["context"] == "上下文内容"
    assert vars_dict["user_id"] == "user-002"
    assert vars_dict["conversation_id"] == "conv-002"


def test_to_template_vars_with_missing_fields():
    """Test to_template_vars() with None fields uses defaults"""
    ctx = TemplateContext(
        intent="chat",
        slots=SlotResult(),
        tool_results={},
        context="",
        user_message="测试"
    )

    vars_dict = ctx.to_template_vars()

    assert vars_dict["memories"] == ""
    assert vars_dict["user_id"] == "anonymous"
    assert vars_dict["conversation_id"] == ""
