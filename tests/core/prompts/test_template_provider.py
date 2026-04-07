"""测试 TemplateProvider"""

import pytest

from app.core.prompts.providers.base import PromptTemplate
from app.core.prompts.providers.template_provider import TemplateProvider


class TestTemplateProviderInit:
    """测试 TemplateProvider 初始化"""

    @pytest.mark.asyncio
    async def test_init_default_templates(self):
        """测试使用默认模板初始化"""
        provider = TemplateProvider()
        templates = await provider.list_templates()
        assert "itinerary" in templates
        assert "query" in templates
        assert "chat" in templates

    @pytest.mark.asyncio
    async def test_init_custom_templates_merge(self):
        """测试传入自定义模板会与默认模板合并"""
        provider = TemplateProvider({"weather": "查询 {city} 的天气"})
        templates = await provider.list_templates()
        assert "weather" in templates
        # 默认模板仍然存在
        assert "itinerary" in templates
        assert "query" in templates
        assert "chat" in templates

    @pytest.mark.asyncio
    async def test_init_custom_templates_override(self):
        """测试传入同名模板会覆盖默认模板"""
        custom_itinerary = "自定义行程模板"
        provider = TemplateProvider({"itinerary": custom_itinerary})
        template = await provider.get_template("itinerary")
        assert template.template == custom_itinerary


class TestTemplateProviderGetTemplate:
    """测试 get_template 方法"""

    @pytest.mark.asyncio
    async def test_get_default_template(self):
        """测试获取默认模板"""
        provider = TemplateProvider()
        template = await provider.get_template("itinerary")
        assert isinstance(template, PromptTemplate)
        assert template.intent == "itinerary"
        assert "旅游规划助手" in template.template

    @pytest.mark.asyncio
    async def test_get_query_template(self):
        """测试获取 query 模板"""
        provider = TemplateProvider()
        template = await provider.get_template("query")
        assert template.intent == "query"
        assert "旅游查询助手" in template.template
        assert "{user_message}" in template.template

    @pytest.mark.asyncio
    async def test_get_chat_template(self):
        """测试获取 chat 模板"""
        provider = TemplateProvider()
        template = await provider.get_template("chat")
        assert template.intent == "chat"
        assert "旅游助手" in template.template

    @pytest.mark.asyncio
    async def test_get_nonexistent_falls_back_to_chat(self):
        """测试获取不存在的意图时回退到 chat 模板"""
        provider = TemplateProvider()
        template = await provider.get_template("nonexistent_intent")
        assert template.intent == "chat"
        assert "旅游助手" in template.template

    @pytest.mark.asyncio
    async def test_get_template_version_field(self):
        """测试模板版本字段"""
        provider = TemplateProvider()
        template = await provider.get_template("itinerary")
        # 默认版本应为 "latest" 或已记录的版本
        assert template.version is not None


class TestTemplateProviderUpdateTemplate:
    """测试 update_template 方法"""

    @pytest.mark.asyncio
    async def test_update_template(self):
        """测试更新模板"""
        provider = TemplateProvider()
        new_content = "新的行程规划提示词：{destination}"
        version = await provider.update_template("itinerary", new_content)
        # 验证返回了版本号
        assert isinstance(version, str)
        assert "." in version  # 版本号格式应为 YYYYMMDD.N
        # 验证模板已更新
        template = await provider.get_template("itinerary")
        assert template.template == new_content

    @pytest.mark.asyncio
    async def test_update_creates_new_version(self):
        """测试更新模板会创建新版本"""
        provider = TemplateProvider()
        v1 = await provider.update_template("itinerary", "版本1")
        v2 = await provider.update_template("itinerary", "版本2")
        assert v1 != v2
        template = await provider.get_template("itinerary")
        assert template.template == "版本2"

    @pytest.mark.asyncio
    async def test_update_nonexistent_creates_new(self):
        """测试更新不存在的模板会创建新的"""
        provider = TemplateProvider()
        version = await provider.update_template("custom_intent", "自定义内容")
        assert isinstance(version, str)
        template = await provider.get_template("custom_intent")
        assert template.template == "自定义内容"

    @pytest.mark.asyncio
    async def test_update_template_version_increments(self):
        """测试连续更新版本号递增"""
        provider = TemplateProvider()
        v1 = await provider.update_template("test_intent", "v1")
        v2 = await provider.update_template("test_intent", "v2")
        v3 = await provider.update_template("test_intent", "v3")
        assert v1 != v2 != v3
        # 验证最后一个版本是 v3
        template = await provider.get_template("test_intent")
        assert template.template == "v3"


class TestTemplateProviderListTemplates:
    """测试 list_templates 方法"""

    @pytest.mark.asyncio
    async def test_list_templates(self):
        """测试列出可用模板"""
        provider = TemplateProvider()
        templates = await provider.list_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 3  # 至少包含 itinerary, query, chat
        assert "itinerary" in templates
        assert "query" in templates
        assert "chat" in templates

    @pytest.mark.asyncio
    async def test_list_templates_includes_custom(self):
        """测试列表包含自定义模板"""
        provider = TemplateProvider({"weather": "天气查询"})
        templates = await provider.list_templates()
        assert "weather" in templates

    @pytest.mark.asyncio
    async def test_list_templates_after_update(self):
        """测试更新后列表包含新模板"""
        provider = TemplateProvider()
        await provider.update_template("new_intent", "新内容")
        templates = await provider.list_templates()
        assert "new_intent" in templates
