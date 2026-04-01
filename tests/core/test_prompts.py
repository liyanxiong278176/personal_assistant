"""测试提示词构建器"""

import pytest

from app.core.prompts.layers import PromptLayer, PromptLayerDef
from app.core.prompts.builder import PromptBuilder, DEFAULT_SYSTEM_PROMPT, APPEND_TOOL_DESCRIPTION


class TestPromptLayer:
    """测试提示词层级枚举"""

    def test_layer_priority_values(self):
        """测试层级优先级值"""
        assert PromptLayer.OVERRIDE.value == 0
        assert PromptLayer.DEFAULT.value == 50
        assert PromptLayer.APPEND.value == 100

    def test_layer_ordering(self):
        """测试层级排序"""
        layers = [PromptLayer.APPEND, PromptLayer.OVERRIDE, PromptLayer.DEFAULT]
        sorted_layers = sorted(layers, key=lambda x: x.value)
        assert sorted_layers == [PromptLayer.OVERRIDE, PromptLayer.DEFAULT, PromptLayer.APPEND]


class TestPromptLayerDef:
    """测试提示词层定义"""

    def test_basic_layer_def(self):
        """测试基本层定义"""
        layer = PromptLayerDef("test", "content", PromptLayer.DEFAULT)
        assert layer.name == "test"
        assert layer.content == "content"
        assert layer.layer == PromptLayer.DEFAULT
        assert layer.condition is None

    def test_should_apply_without_condition(self):
        """测试无条件时总是应用"""
        layer = PromptLayerDef("test", "content", PromptLayer.DEFAULT)
        assert layer.should_apply() is True

    def test_should_apply_with_condition(self):
        """测试条件触发"""
        layer_true = PromptLayerDef("test", "content", PromptLayer.DEFAULT, condition=lambda: True)
        layer_false = PromptLayerDef("test", "content", PromptLayer.DEFAULT, condition=lambda: False)
        assert layer_true.should_apply() is True
        assert layer_false.should_apply() is False


class TestPromptBuilder:
    """测试提示词构建器"""

    def test_empty_builder(self):
        """测试空构建器"""
        builder = PromptBuilder()
        assert builder.build() == ""

    def test_add_layer(self):
        """测试添加层"""
        builder = PromptBuilder()
        builder.add_layer("test", "test content", PromptLayer.DEFAULT)
        result = builder.build()
        assert "# test" in result
        assert "test content" in result

    def test_layer_ordering(self):
        """测试层级排序"""
        builder = PromptBuilder()
        builder.add_layer("append", "append content", PromptLayer.APPEND)
        builder.add_layer("override", "override content", PromptLayer.OVERRIDE)
        builder.add_layer("default", "default content", PromptLayer.DEFAULT)

        result = builder.build()
        # OVERRIDE (0) should come first, then DEFAULT (50), then APPEND (100)
        override_pos = result.index("# override")
        default_pos = result.index("# default")
        append_pos = result.index("# append")

        assert override_pos < default_pos < append_pos

    def test_clear(self):
        """测试清空"""
        builder = PromptBuilder()
        builder.add_layer("test", "content", PromptLayer.DEFAULT)
        builder.clear()
        assert builder.build() == ""

    def test_remove_layer(self):
        """测试移除层"""
        builder = PromptBuilder()
        builder.add_layer("test1", "content1", PromptLayer.DEFAULT)
        builder.add_layer("test2", "content2", PromptLayer.DEFAULT)

        assert builder.remove_layer("test1") is True
        assert "test1" not in builder.build()
        assert "test2" in builder.build()

    def test_remove_layer_not_found(self):
        """测试移除不存在的层"""
        builder = PromptBuilder()
        builder.add_layer("test", "content", PromptLayer.DEFAULT)

        assert builder.remove_layer("nonexistent") is False
        assert "test" in builder.build()

    def test_conditional_layer_applied(self):
        """测试条件层被应用"""
        builder = PromptBuilder()
        builder.add_layer("conditional", "content", PromptLayer.DEFAULT, condition=lambda: True)
        result = builder.build()
        assert "conditional" in result
        assert "content" in result

    def test_conditional_layer_not_applied(self):
        """测试条件层不被应用"""
        builder = PromptBuilder()
        builder.add_layer("base", "base content", PromptLayer.DEFAULT)
        builder.add_layer("conditional", "conditional content", PromptLayer.DEFAULT, condition=lambda: False)

        result = builder.build()
        assert "base content" in result
        assert "conditional content" not in result


class TestPredefinedPrompts:
    """测试预定义提示词"""

    def test_default_system_prompt_exists(self):
        """测试默认系统提示词存在"""
        assert DEFAULT_SYSTEM_PROMPT
        assert "旅游助手" in DEFAULT_SYSTEM_PROMPT

    def test_append_tool_description_exists(self):
        """测试工具描述模板存在"""
        assert APPEND_TOOL_DESCRIPTION
        assert "{tools}" in APPEND_TOOL_DESCRIPTION
        assert "可用工具" in APPEND_TOOL_DESCRIPTION

    def test_tool_description_formatting(self):
        """测试工具描述格式化"""
        tools = "- search_weather: 查询天气"
        formatted = APPEND_TOOL_DESCRIPTION.format(tools=tools)
        assert "search_weather" in formatted
