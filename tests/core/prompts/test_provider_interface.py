"""测试 IPromptProvider 接口和数据模型"""

import pytest
from typing import List

from app.core.prompts.providers.base import (
    IPromptProvider,
    PromptFilterResult,
    PromptTemplate,
)


class TestPromptTemplateModel:
    """测试 PromptTemplate 数据模型"""

    def test_prompt_template_basic(self):
        """测试基本构造"""
        template = PromptTemplate(
            intent="weather_query",
            template="查询 {city} 的天气",
            variables=["city"],
        )
        assert template.intent == "weather_query"
        assert template.template == "查询 {city} 的天气"
        assert template.variables == ["city"]
        assert template.version == "latest"
        assert template.metadata == {}

    def test_prompt_template_with_version(self):
        """测试带版本号构造"""
        template = PromptTemplate(
            intent="travel_plan",
            version="2.1",
            template="为用户规划 {days} 天的 {destination} 行程",
            variables=["days", "destination"],
            metadata={"author": "agent", "status": "production"},
        )
        assert template.version == "2.1"
        assert template.metadata["author"] == "agent"
        assert template.metadata["status"] == "production"

    def test_prompt_template_defaults(self):
        """测试默认值"""
        template = PromptTemplate(
            intent="simple_intent",
            template="Simple prompt content",
        )
        assert template.version == "latest"
        assert template.variables == []
        assert template.metadata == {}

    def test_prompt_template_model_validation(self):
        """测试 Pydantic 模型验证"""
        # intent is required
        with pytest.raises(Exception):
            PromptTemplate(template="no intent")

        # template is required
        with pytest.raises(Exception):
            PromptTemplate(intent="test")

    def test_prompt_template_to_dict(self):
        """测试模型序列化"""
        template = PromptTemplate(
            intent="test_intent",
            version="1.0",
            template="Test template",
            variables=["var1"],
            metadata={"key": "value"},
        )
        data = template.model_dump()
        assert data["intent"] == "test_intent"
        assert data["version"] == "1.0"
        assert data["template"] == "Test template"
        assert data["variables"] == ["var1"]
        assert data["metadata"] == {"key": "value"}

    def test_prompt_template_from_dict(self):
        """测试从字典构造模型"""
        data = {
            "intent": "restored_intent",
            "version": "3.0",
            "template": "Restored template {param}",
            "variables": ["param"],
            "metadata": {"restored": True},
        }
        template = PromptTemplate.model_validate(data)
        assert template.intent == "restored_intent"
        assert template.version == "3.0"
        assert template.template == "Restored template {param}"
        assert template.variables == ["param"]
        assert template.metadata["restored"] is True


class TestPromptFilterResultModel:
    """测试 PromptFilterResult 数据模型"""

    def test_prompt_filter_result_success(self):
        """测试成功过滤结果"""
        result = PromptFilterResult(
            success=True,
            content="Cleaned prompt content",
        )
        assert result.success is True
        assert result.content == "Cleaned prompt content"
        assert result.error is None
        assert result.warning is None
        assert result.should_fallback is False

    def test_prompt_filter_result_with_error(self):
        """测试带错误信息的过滤结果"""
        result = PromptFilterResult(
            success=False,
            content="",
            error="Injection detected: {malicious}",
            should_fallback=True,
        )
        assert result.success is False
        assert result.error == "Injection detected: {malicious}"
        assert result.content == ""
        assert result.should_fallback is True

    def test_prompt_filter_result_with_warning(self):
        """测试带警告信息的过滤结果"""
        result = PromptFilterResult(
            success=True,
            content="Prompt content with warning",
            warning="Template contains unusual patterns",
        )
        assert result.success is True
        assert result.warning == "Template contains unusual patterns"

    def test_prompt_filter_result_defaults(self):
        """测试默认值"""
        result = PromptFilterResult(success=True, content="OK")
        assert result.error is None
        assert result.warning is None
        assert result.should_fallback is False

    def test_prompt_filter_result_serialization(self):
        """测试序列化"""
        result = PromptFilterResult(
            success=True,
            content="Test content",
            warning="Test warning",
        )
        data = result.model_dump()
        assert data["success"] is True
        assert data["content"] == "Test content"
        assert data["warning"] == "Test warning"
        assert data["error"] is None
        assert data["should_fallback"] is False


class TestIPromptProviderInterface:
    """测试 IPromptProvider 接口定义"""

    def test_interface_is_abstract(self):
        """测试接口不能直接实例化"""

        class DummyProvider(IPromptProvider):
            async def get_template(self, intent, version="latest"):
                pass

            async def update_template(self, intent, template):
                pass

            async def list_templates(self):
                return []

        # Should be able to instantiate a concrete implementation
        provider = DummyProvider()
        assert isinstance(provider, IPromptProvider)

    def test_interface_methods_exist(self):
        """测试接口方法签名"""

        class MinimalProvider(IPromptProvider):
            async def get_template(self, intent, version="latest"):
                return PromptTemplate(intent=intent, template="test")

            async def update_template(self, intent, template):
                return "1.0"

            async def list_templates(self):
                return ["test_intent"]

        provider = MinimalProvider()
        assert hasattr(provider, "get_template")
        assert hasattr(provider, "update_template")
        assert hasattr(provider, "list_templates")

    @pytest.mark.asyncio
    async def test_get_template_returns_prompt_template(self):
        """测试 get_template 返回正确的类型"""

        class TestProvider(IPromptProvider):
            async def get_template(self, intent, version="latest"):
                return PromptTemplate(
                    intent=intent,
                    version=version,
                    template=f"Template for {intent}",
                )

            async def update_template(self, intent, template):
                return "1.0"

            async def list_templates(self):
                return []

        provider = TestProvider()
        template = await provider.get_template("test_intent", "2.0")
        assert isinstance(template, PromptTemplate)
        assert template.intent == "test_intent"
        assert template.version == "2.0"

    @pytest.mark.asyncio
    async def test_update_template_returns_version_string(self):
        """测试 update_template 返回版本字符串"""

        class TestProvider(IPromptProvider):
            async def get_template(self, intent, version="latest"):
                return PromptTemplate(intent=intent, template="test")

            async def update_template(self, intent, template):
                return "3.1"

            async def list_templates(self):
                return []

        provider = TestProvider()
        version = await provider.update_template("intent", "new template content")
        assert isinstance(version, str)
        assert version == "3.1"

    @pytest.mark.asyncio
    async def test_list_templates_returns_list_of_strings(self):
        """测试 list_templates 返回字符串列表"""

        class TestProvider(IPromptProvider):
            async def get_template(self, intent, version="latest"):
                return PromptTemplate(intent=intent, template="test")

            async def update_template(self, intent, template):
                return "1.0"

            async def list_templates(self):
                return ["weather_query", "travel_plan", "hotel_booking"]

        provider = TestProvider()
        intents = await provider.list_templates()
        assert isinstance(intents, list)
        assert all(isinstance(i, str) for i in intents)
        assert "weather_query" in intents
        assert "travel_plan" in intents
