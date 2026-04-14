"""Tests for RequestContext prompt enhancement fields.

Tests the new fields: intent, output_format, examples_enabled, few_shot_count.
Also tests ExamplesLoader for few-shot YAML management.
And tests TemplateRenderer for structured block parsing.
"""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.context import RequestContext
from app.core.prompts.examples_loader import ExamplesLoader
from app.core.prompts.renderer import TemplateRenderer


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


class TestExamplesLoader:
    """Tests for ExamplesLoader - Few-shot YAML loader."""

    def test_examples_loader_loads_file(self):
        """能加载指定意图的 YAML 示例"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)
            from app.core.prompts.examples_loader import ExamplesLoader

            loader = ExamplesLoader(examples_dir)

            data = {
                "itinerary": [
                    {"input": "我想去杭州3天", "output": "好的，为您规划..."}
                ]
            }
            (examples_dir / "itinerary.yaml").write_text(yaml.dump(data), encoding="utf-8")

            examples = loader.get_examples("itinerary")
            assert len(examples) == 1
            assert examples[0]["input"] == "我想去杭州3天"

    def test_examples_loader_caches(self):
        """第二次调用返回缓存结果"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)
            from app.core.prompts.examples_loader import ExamplesLoader

            loader = ExamplesLoader(examples_dir)

            data = {"chat": [{"input": "hi", "output": "hello"}]}
            (examples_dir / "chat.yaml").write_text(yaml.dump(data), encoding="utf-8")

            first = loader.get_examples("chat")
            second = loader.get_examples("chat")
            # 同一对象（缓存）
            assert first is second

    def test_examples_loader_missing_file(self):
        """文件不存在时返回空列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.core.prompts.examples_loader import ExamplesLoader

            loader = ExamplesLoader(Path(tmpdir))
            assert loader.get_examples("nonexistent") == []

    def test_examples_loader_empty_yaml(self):
        """空 YAML 文件返回空列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)
            from app.core.prompts.examples_loader import ExamplesLoader

            loader = ExamplesLoader(examples_dir)

            # Empty file
            (examples_dir / "empty.yaml").write_text("", encoding="utf-8")

            examples = loader.get_examples("empty")
            assert examples == []

    def test_examples_loader_invalid_yaml(self):
        """无效 YAML 返回空列表并记录错误"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)
            from app.core.prompts.examples_loader import ExamplesLoader

            loader = ExamplesLoader(examples_dir)

            # Invalid YAML
            (examples_dir / "invalid.yaml").write_text(":::invalid:::yaml", encoding="utf-8")

            examples = loader.get_examples("invalid")
            assert examples == []

    def test_examples_loader_multiple_examples(self):
        """能加载多个示例"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)
            from app.core.prompts.examples_loader import ExamplesLoader

            loader = ExamplesLoader(examples_dir)

            data = {
                "query": [
                    {"input": "北京天气", "output": "北京今天晴..."},
                    {"input": "上海天气", "output": "上海今天多云..."},
                    {"input": "广州天气", "output": "广州今天雨..."},
                ]
            }
            (examples_dir / "query.yaml").write_text(yaml.dump(data), encoding="utf-8")

            examples = loader.get_examples("query")
            assert len(examples) == 3
            assert examples[0]["input"] == "北京天气"
            assert examples[2]["output"] == "广州今天雨..."


class TestTemplateRenderer:
    """Tests for TemplateRenderer - structured block parsing."""

    def test_template_renderer_parses_role_block(self):
        """Parses <role> block correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "<role>你是旅游助手</role>"
            ctx = RequestContext(message="测试")
            result = renderer.render(template, ctx)
            assert "你是旅游助手" in result

    def test_template_renderer_parses_rules_sorted(self):
        """Parses <rules> block and sorts by priority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = """<rules>
<rule priority="2">第二条规则</rule>
<rule priority="1">第一条规则</rule>
<rule priority="3">第三条规则</rule>
</rules>"""
            ctx = RequestContext(message="测试")
            result = renderer.render(template, ctx)
            assert result.index("第一条规则") < result.index("第二条规则")
            assert result.index("第二条规则") < result.index("第三条规则")

    def test_template_renderer_multiline_rules(self):
        """Handles multiline rules correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = """<rules>
<rule priority="1">第一行
第二行
第三行</rule>
</rules>"""
            ctx = RequestContext(message="测试")
            result = renderer.render(template, ctx)
            assert "第一行" in result
            assert "第二行" in result

    def test_template_renderer_conditionals_truthy(self):
        """Includes content when conditional variable is truthy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "{#if slots}槽位信息：{slots}{/if}"
            ctx = RequestContext(message="测试", slots={"destination": "杭州"})
            result = renderer.render(template, ctx)
            assert "槽位信息" in result

    def test_template_renderer_conditionals_falsy(self):
        """Excludes content when conditional variable is falsy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "{#if memories}记忆：{memories}{/if}"
            ctx = RequestContext(message="测试", memories=[])
            result = renderer.render(template, ctx)
            assert "记忆" not in result

    def test_template_renderer_injects_user_message(self):
        """Injects {user_message} variable correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "用户说：{user_message}"
            ctx = RequestContext(message="我想去杭州")
            result = renderer.render(template, ctx)
            assert "我想去杭州" in result

    def test_template_renderer_examples_disabled(self):
        """Skips examples block when examples_enabled=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "<examples><example><input>test</input><output>resp</output></example></examples>"
            ctx = RequestContext(message="test", examples_enabled=False)
            result = renderer.render(template, ctx)
            assert "示例" not in result

    def test_template_renderer_unknown_block_preserved(self):
        """Preserves unknown blocks as-is."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "<unknown>some content</unknown>"
            ctx = RequestContext(message="test")
            result = renderer.render(template, ctx)
            assert "some content" in result

    def test_template_renderer_output_format(self):
        """Parses <output_format> block correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "<output_format>JSON格式输出</output_format>"
            ctx = RequestContext(message="测试")
            result = renderer.render(template, ctx)
            assert "JSON格式输出" in result
            assert "输出格式要求" in result

    def test_template_renderer_multiple_blocks(self):
        """Handles multiple blocks in one template."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = """<role>你是助手</role>

<rules>
<rule priority="1">规则1</rule>
</rules>

<output_format>文本</output_format>"""
            ctx = RequestContext(message="测试")
            result = renderer.render(template, ctx)
            assert "你是助手" in result
            assert "规则1" in result
            assert "文本" in result

    def test_template_renderer_conditional_with_string_value(self):
        """Handles conditionals with string values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "{#if intent}Intent: {intent}{/if}"
            ctx = RequestContext(message="测试", intent="itinerary")
            result = renderer.render(template, ctx)
            assert "Intent: itinerary" in result

    def test_template_renderer_conditional_with_none(self):
        """Removes conditional block when value is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = "{#if intent}Intent: {intent}{/if}"
            ctx = RequestContext(message="测试", intent=None)
            result = renderer.render(template, ctx)
            assert "Intent:" not in result

    def test_template_renderer_rules_without_priority(self):
        """Handles rules without priority (defaults to 99)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            template = """<rules>
<rule>无优先级规则</rule>
<rule priority="1">有优先级规则</rule>
</rules>"""
            ctx = RequestContext(message="测试")
            result = renderer.render(template, ctx)
            assert "无优先级规则" in result
            assert "有优先级规则" in result


class TestPromptConfigLoader:
    """Tests for PromptConfigLoader query methods."""

    def test_loader_get_output_format(self):
        """get_output_format 返回正确的 output_format"""
        from app.core.prompts.loader import PromptConfigLoader
        loader = PromptConfigLoader()
        assert loader.get_output_format("itinerary") == "structured"
        assert loader.get_output_format("chat") == "free"
        assert loader.get_output_format("unknown") == "free"  # 默认值

    def test_loader_get_few_shot_config(self):
        """get_few_shot_config 返回正确的 Few-shot 配置"""
        from app.core.prompts.loader import PromptConfigLoader
        loader = PromptConfigLoader()
        enabled, count = loader.get_few_shot_config("itinerary")
        assert enabled is True
        assert count == 3
        enabled, count = loader.get_few_shot_config("unknown")
        assert enabled is True  # 默认值
        assert count == 3  # 默认值


class TestPromptServiceIntegration:
    """Integration tests for PromptService with TemplateRenderer."""

    def test_prompt_service_integration_with_renderer(self):
        """PromptService 正确集成 TemplateRenderer"""
        from app.core.prompts.service import PromptService
        from app.core.prompts.renderer import TemplateRenderer
        from app.core.prompts.examples_loader import ExamplesLoader
        from app.core.context import RequestContext
        from app.core.prompts.providers.base import IPromptProvider, PromptTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)
            (examples_dir / "itinerary.yaml").write_text(
                yaml.dump({"itinerary": [{"input": "test", "output": "resp"}]}),
                encoding="utf-8"
            )

            mock_provider = MagicMock(spec=IPromptProvider)
            mock_provider.get_template = AsyncMock()
            mock_provider.get_template.return_value = PromptTemplate(
                intent="itinerary",
                template="<role>旅游助手</role>",
                version="1.0",
            )

            service = PromptService(
                provider=mock_provider,
                config_loader=None,
                examples_dir=examples_dir,
            )

            assert service._renderer is not None
            assert isinstance(service._renderer, TemplateRenderer)

            ctx = RequestContext(
                message="测试",
                intent="itinerary",
                examples_enabled=True,
                few_shot_count=1,
            )

            # render() 是 async 的，需要 await
            import asyncio
            result = asyncio.run(service.render("itinerary", ctx))
            assert "旅游助手" in result

    def test_prompt_service_without_renderer_fallback(self):
        """PromptService 在没有 examples_dir 时使用原有逻辑"""
        from app.core.prompts.service import PromptService
        from app.core.context import RequestContext
        from app.core.prompts.providers.base import IPromptProvider, PromptTemplate

        mock_provider = MagicMock(spec=IPromptProvider)
        mock_provider.get_template = AsyncMock()
        mock_provider.get_template.return_value = PromptTemplate(
            intent="chat",
            template="你好，{user_message}！",
            version="1.0",
        )

        service = PromptService(
            provider=mock_provider,
            config_loader=None,
            examples_dir=None,
        )

        assert service._renderer is None

        ctx = RequestContext(message="世界")
        import asyncio
        result = asyncio.run(service.render("chat", ctx))
        assert "你好，世界！" in result

    def test_prompt_service_fills_context_from_config(self):
        """PromptService 从 config_loader 填充意图元数据"""
        from app.core.prompts.service import PromptService
        from app.core.context import RequestContext
        from app.core.prompts.providers.base import IPromptProvider, PromptTemplate
        from app.core.prompts.loader import PromptConfigLoader

        mock_provider = MagicMock(spec=IPromptProvider)
        mock_provider.get_template = AsyncMock()
        mock_provider.get_template.return_value = PromptTemplate(
            intent="itinerary",
            template="Intent: {intent}, Format: {output_format}",
            version="1.0",
        )

        # 使用真实的 PromptConfigLoader
        config_loader = PromptConfigLoader()

        service = PromptService(
            provider=mock_provider,
            config_loader=config_loader,
            examples_dir=None,  # 不使用 renderer
        )

        # 传入没有元数据的 context
        ctx = RequestContext(message="测试")

        import asyncio
        result = asyncio.run(service.render("itinerary", ctx))

        # 验证元数据被填充
        assert "Intent: itinerary" in result
        # itinerary 的 output_format 是 "structured"
        assert "Format: structured" in result

    def test_prompt_service_renderer_with_config(self):
        """PromptService 同时使用 TemplateRenderer 和 config_loader"""
        from app.core.prompts.service import PromptService
        from app.core.prompts.renderer import TemplateRenderer
        from app.core.context import RequestContext
        from app.core.prompts.providers.base import IPromptProvider, PromptTemplate
        from app.core.prompts.loader import PromptConfigLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)
            # 创建示例文件
            (examples_dir / "query.yaml").write_text(
                yaml.dump({
                    "query": [
                        {"input": "北京天气", "output": "北京今天晴天"},
                    ]
                }),
                encoding="utf-8"
            )

            mock_provider = MagicMock(spec=IPromptProvider)
            mock_provider.get_template = AsyncMock()
            # 使用带 <examples> 区块的模板
            mock_provider.get_template.return_value = PromptTemplate(
                intent="query",
                template="<role>查询助手</role>\n\n<examples></examples>",
                version="1.0",
            )

            config_loader = PromptConfigLoader()

            service = PromptService(
                provider=mock_provider,
                config_loader=config_loader,
                examples_dir=examples_dir,
            )

            assert service._renderer is not None
            assert isinstance(service._renderer, TemplateRenderer)

            # 传入没有元数据的 context，应该被 config_loader 填充
            ctx = RequestContext(message="测试")
            import asyncio
            result = asyncio.run(service.render("query", ctx))

            # 验证基本渲染
            assert "查询助手" in result
            # query 的 output_format 是 "free"
            # 由于有 examples_enabled=True，应该注入示例
            # 但示例注入需要 TemplateRenderer 的 _render_examples 实现


class TestFullPipelineIntegration:
    """完整集成测试 - 端到端渲染测试，验证完整 pipeline。"""

    def test_full_pipeline_render(self):
        """完整流程：从 YAML 配置 -> 模板渲染 -> 变量注入"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)

            # 创建 examples YAML
            data = {"itinerary": [{"input": "test", "output": "resp"}]}
            (examples_dir / "itinerary.yaml").write_text(yaml.dump(data), encoding="utf-8")

            loader = ExamplesLoader(examples_dir)
            renderer = TemplateRenderer(loader)

            from app.core.intent.slot_extractor import SlotResult
            slots = SlotResult(
                destination="杭州",
                days="3",
                destinations=["杭州"],
            )

            ctx = RequestContext(
                message="我想去杭州",
                intent="itinerary",
                output_format="structured",
                examples_enabled=True,
                few_shot_count=1,
                slots=slots,
            )

            template = renderer.render("<role>旅游助手</role>", ctx)
            assert "旅游助手" in template

    def test_pipeline_with_rules_and_output_format(self):
        """验证 rules 和 output_format 区块渲染"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            ctx = RequestContext(message="测试")

            template = """<role>助手</role>
<rules>
<rule priority="1">规则一</rule>
<rule priority="2">规则二</rule>
</rules>
<output_format>
格式说明
</output_format>"""

            result = renderer.render(template, ctx)
            assert "助手" in result
            assert "规则一" in result
            assert "规则二" in result
            assert result.index("规则一") < result.index("规则二")
            assert "输出格式要求" in result
            assert "格式说明" in result

    def test_pipeline_preserves_conditional_context(self):
        """验证条件注入正确处理 slots/memories/tool_results"""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExamplesLoader(Path(tmpdir))
            renderer = TemplateRenderer(loader)

            from app.core.intent.slot_extractor import SlotResult
            slots = SlotResult(
                destination="杭州",
                destinations=["杭州"],
            )

            ctx = RequestContext(
                message="测试",
                slots=slots,
                memories=[],
                tool_results={},
            )

            template = "{#if slots}槽位：{slots}{/if}{#if memories}记忆：{memories}{/if}"
            result = renderer.render(template, ctx)
            assert "槽位" in result
            assert "杭州" in result
            assert "记忆" not in result  # memories 为空列表，不渲染

    def test_full_pipeline_with_examples_injection(self):
        """验证 Few-shot 示例正确注入"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)

            # 创建 examples YAML
            data = {
                "query": [
                    {"input": "北京天气", "output": "北京今天晴天"},
                    {"input": "上海天气", "output": "上海今天多云"},
                ]
            }
            (examples_dir / "query.yaml").write_text(yaml.dump(data), encoding="utf-8")

            loader = ExamplesLoader(examples_dir)
            renderer = TemplateRenderer(loader)

            ctx = RequestContext(
                message="测试",
                intent="query",
                examples_enabled=True,
                few_shot_count=2,
            )

            template = "<examples></examples>"
            result = renderer.render(template, ctx)

            # 验证示例被注入
            assert "示例 1" in result
            assert "示例 2" in result
            assert "北京天气" in result
            assert "上海天气" in result

    def test_full_pipeline_examples_disabled(self):
        """验证 examples_enabled=False 时跳过示例"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)

            data = {"chat": [{"input": "hi", "output": "hello"}]}
            (examples_dir / "chat.yaml").write_text(yaml.dump(data), encoding="utf-8")

            loader = ExamplesLoader(examples_dir)
            renderer = TemplateRenderer(loader)

            ctx = RequestContext(
                message="测试",
                intent="chat",
                examples_enabled=False,
            )

            template = "<examples></examples>"
            result = renderer.render(template, ctx)

            # 验证示例未被注入
            assert "示例" not in result
            assert "hi" not in result

    def test_full_pipeline_with_all_blocks(self):
        """验证所有区块协同工作"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)

            data = {
                "itinerary": [
                    {"input": "杭州3天", "output": "为您规划杭州3天行程..."}
                ]
            }
            (examples_dir / "itinerary.yaml").write_text(yaml.dump(data), encoding="utf-8")

            loader = ExamplesLoader(examples_dir)
            renderer = TemplateRenderer(loader)

            from app.core.intent.slot_extractor import SlotResult
            slots = SlotResult(
                destination="杭州",
                days="3",
                destinations=["杭州"],
            )

            ctx = RequestContext(
                message="我想去杭州玩3天",
                intent="itinerary",
                slots=slots,
                examples_enabled=True,
                few_shot_count=1,
            )

            template = """<role>旅游规划助手</role>

<rules>
<rule priority="1">优先推荐热门景点</rule>
<rule priority="2">考虑用户预算</rule>
</rules>

<examples></examples>

<output_format>
- 每日行程
- 景点推荐
- 注意事项
</output_format>"""

            result = renderer.render(template, ctx)

            # 验证所有区块都被正确渲染
            assert "旅游规划助手" in result
            assert "优先推荐热门景点" in result
            assert "考虑用户预算" in result
            assert result.index("优先推荐热门景点") < result.index("考虑用户预算")
            assert "示例 1" in result
            assert "杭州3天" in result
            assert "输出格式要求" in result
            assert "每日行程" in result