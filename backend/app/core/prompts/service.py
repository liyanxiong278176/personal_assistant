"""PromptService - 提示词模板渲染服务

注意：pipeline 模块已迁移到 security.injection_guard_enhanced
此��务已简化，移除了对已删除模块的依赖。

如需完整的安全过滤和 Token 压缩功能，请使用：
- security.injection_guard_enhanced.InjectionGuardEnhanced
- context_mgmt.guard.ContextGuard
- token_budget.TokenBudgetManager
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.core.prompts.providers.base import IPromptProvider
from app.core.prompts.examples_loader import ExamplesLoader
from app.core.prompts.renderer import TemplateRenderer, format_slots, format_memories, format_tool_results

if TYPE_CHECKING:
    from app.core.context import RequestContext

logger = logging.getLogger(__name__)


class PromptService:
    """提示词服务 - 简化版

    提供模板检索和变量注入功能。

    安全过滤和 Token 压缩已迁移到专用模块：
    - 使用 InjectionGuardEnhanced 进行输入安全检查
    - 使用 ContextGuard 进行上下文管理
    - 使用 TokenBudgetManager 进行 Token 预算管理
    """

    def __init__(
        self,
        provider: IPromptProvider,
        prompt_builder: Optional["PromptBuilder"] = None,
        config_loader: Optional["PromptConfigLoader"] = None,
        examples_dir: Optional[Path] = None,
    ):
        """初始化提示词服务

        Args:
            provider: 模板提供者
            prompt_builder: 可选的 PromptBuilder 实例，用于构建系统提示词层
            config_loader: 可选的 PromptConfigLoader 实例，用于获取意图配置
            examples_dir: 可选的 Few-shot 示例目录路径
        """
        self.provider = provider
        self._prompt_builder = prompt_builder
        self._config = config_loader

        # 初始化 ExamplesLoader 和 TemplateRenderer
        if examples_dir:
            self._examples_loader = ExamplesLoader(examples_dir)
            self._renderer = TemplateRenderer(self._examples_loader)
        else:
            self._examples_loader = None
            self._renderer = None

        builder_info = f" + PromptBuilder" if prompt_builder else ""
        config_info = f" + ConfigLoader" if config_loader else ""
        renderer_info = f" + TemplateRenderer" if self._renderer else ""
        logger.info(f"[PromptService] Initialized with provider {provider.__class__.__name__}{builder_info}{config_info}{renderer_info}")

    async def render(
        self,
        intent: str,
        context: "RequestContext",
    ) -> str:
        """渲染指定意图的提示词

        统一的提示词渲染入口，结合：
        1. 填充意图元数据到 context（从 config_loader 获取）
        2. PromptBuilder 构建的系统提示词层（如果可用）
        3. TemplateRenderer 渲染结构化模板（如果可用）

        Args:
            intent: 意图标识符 (e.g., "itinerary", "query")
            context: 请求上下文

        Returns:
            渲染后的提示词字符串
        """
        # 1. 填充意图元数据到 context
        if self._config:
            output_format = self._config.get_output_format(intent)
            examples_enabled, few_shot_count = self._config.get_few_shot_config(intent)
            context = context.update(
                intent=intent,
                output_format=output_format,
                examples_enabled=examples_enabled,
                few_shot_count=few_shot_count,
            )
            logger.debug(
                f"[PromptService] Filled intent metadata: intent={intent}, "
                f"output_format={output_format}, examples_enabled={examples_enabled}, "
                f"few_shot_count={few_shot_count}"
            )

        # 2. 构建系统提示词（使用 PromptBuilder，如果可用）
        system_prompt = ""
        if self._prompt_builder:
            system_prompt = self._prompt_builder.build()
            logger.debug(f"[PromptService] System prompt built, length={len(system_prompt)}")

        # 3. 获取并渲染模板
        template = await self.provider.get_template(intent)
        logger.debug(f"[PromptService] Got template for intent '{intent}'")

        # 4. 使用 TemplateRenderer 渲染（如果可用），否则使用原有逻辑
        if self._renderer:
            rendered_template = self._renderer.render(template.template, context)
        else:
            rendered_template = self._inject_variables(template.template, context)

        logger.debug(f"[PromptService] Template rendered, length={len(rendered_template)}")

        # 5. 组合系统提示词和渲染后的模板
        if system_prompt:
            result = system_prompt + "\n\n" + rendered_template
            logger.debug(f"[PromptService] Combined system prompt + template, total length={len(result)}")
            return result

        return rendered_template

    def _inject_variables(
        self,
        template: str,
        context: "RequestContext",
    ) -> str:
        """向模板注入变量

        支持的变量:
        - {user_message}: 原始用户消息
        - {slots}: 格式化的槽位提取结果
        - {memories}: 格式化的记忆项
        - {tool_results}: 格式化的工具执行结果
        - {intent}, {output_format} 等上下文字段

        Args:
            template: 包含变量占位符的模板字符串
            context: 包含变量数据的请求上下文

        Returns:
            替换变量后的模板
        """
        result = template

        # 注入用户消息（始终需要）
        result = result.replace("{user_message}", context.message)

        # 注入槽位（总是替换，即使为空）
        if "{slots}" in result:
            slots_content = PromptService.format_slots(context.slots) if context.slots else "未提取到槽位信息"
            result = result.replace("{slots}", slots_content)

        # 注入记忆（总是替换，即使为空）
        if "{memories}" in result:
            memories_content = PromptService.format_memories(context.memories) if context.memories else "无相关记忆"
            result = result.replace("{memories}", memories_content)

        # 注入工具结果（总是替换，即使为空）
        if "{tool_results}" in result:
            results_content = PromptService.format_tool_results(context.tool_results) if context.tool_results else "无工具调用结果"
            result = result.replace("{tool_results}", results_content)

        # 注入其他上下文变量（如 intent, output_format 等）
        def replace_context_var(match):
            var_name = match.group(1)
            value = getattr(context, var_name, None)
            if value is None:
                return match.group(0)  # 保留原始占位符
            return str(value)

        import re
        result = re.sub(r'\{(\w+)\}', replace_context_var, result)

        return result

    @staticmethod
    def format_slots(slots: Any) -> str:
        """格式化槽位结果为字符串（静态方法，供外部调用）

        返回格式（不带标题）:
        - 目的地: xxx
        - 日期: xxx

        Args:
            slots: 槽位对象或字典

        Returns:
            格式化的槽位字符串
        """
        return format_slots(slots)

    @staticmethod
    def format_memories(memories: List[Any]) -> str:
        """格式化记忆列表为字符串（静态方法，供外部调用）

        返回格式（不带标题）:
        1. xxx
        2. yyy

        Args:
            memories: 记忆列表

        Returns:
            格式化的记忆字符串
        """
        return format_memories(memories)

    @staticmethod
    def format_tool_results(results: Dict[str, Any]) -> str:
        """格式化工具结果为字符串（静态方法，供外部调用）

        返回格式（不带标题）:
        tool_name: {...}
        tool_name2: ...

        Args:
            results: 工具执行结果字典

        Returns:
            格式化的工具结果字符串
        """
        return format_tool_results(results)
