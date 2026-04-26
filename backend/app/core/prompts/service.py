"""PromptService - 提示词模板渲染服务

统一渲染入口：加载模板 → 渲染区块 + 变量注入。
系统提示词通过模板内 {% include "system.md" %} 引入，无需 PromptBuilder。
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
    """提示词服务

    加载意图模板，通过 TemplateRenderer 渲染。
    工具描述通过 {tools} 变量注入，由调用方设置到 context 中。
    """

    def __init__(
        self,
        provider: IPromptProvider,
        config_loader: Optional["PromptConfigLoader"] = None,
        examples_dir: Optional[Path] = None,
    ):
        self.provider = provider
        self._config = config_loader

        if examples_dir:
            self._examples_loader = ExamplesLoader(examples_dir)
            self._renderer = TemplateRenderer(self._examples_loader)
        else:
            self._examples_loader = None
            self._renderer = None

        config_info = f" + ConfigLoader" if config_loader else ""
        renderer_info = f" + TemplateRenderer" if self._renderer else ""
        logger.info(f"[PromptService] Initialized with {provider.__class__.__name__}{config_info}{renderer_info}")

    async def render(
        self,
        intent: str,
        context: "RequestContext",
    ) -> str:
        """渲染指定意图的提示词

        Args:
            intent: 意图标识符 (e.g., "itinerary", "query")
            context: 请求上下文（含 tools, memories, slots, tool_results 等）

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

        # 2. 获取模板
        template = await self.provider.get_template(intent)

        # 3. 渲染（TemplateRenderer 处理 include、条件、区块、变量）
        if self._renderer:
            result = self._renderer.render(template.template, context)
        else:
            result = self._fallback_render(template.template, context)

        logger.debug(f"[PromptService] Rendered intent='{intent}', length={len(result)}")
        return result

    def _fallback_render(self, template: str, context: "RequestContext") -> str:
        """无 TemplateRenderer 时的降级渲染（简单变量替换）"""
        result = template
        result = result.replace("{user_message}", context.message)
        if context.slots:
            result = result.replace("{slots}", format_slots(context.slots))
        if context.memories:
            result = result.replace("{memories}", format_memories(context.memories))
        if context.tool_results:
            result = result.replace("{tool_results}", format_tool_results(context.tool_results))
        return result

    @staticmethod
    def format_slots(slots: Any) -> str:
        return format_slots(slots)

    @staticmethod
    def format_memories(memories: List[Any]) -> str:
        return format_memories(memories)

    @staticmethod
    def format_tool_results(results: Dict[str, Any]) -> str:
        return format_tool_results(results)
