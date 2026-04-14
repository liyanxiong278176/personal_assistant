"""TemplateRenderer - 结构化 Markdown 模板渲染器

解析 <role>/<rules>/<examples>/<output_format> 区块，
处理 {#if}/{/if} 条件注入，调用 ExamplesLoader 获取示例。
"""

import logging
import re
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from app.core.context import RequestContext
    from app.core.prompts.examples_loader import ExamplesLoader

from app.core.prompts.service import PromptService

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """解析 Markdown 中的 <role>/<rules>/<examples>/<output_format> 区块"""

    def __init__(self, examples_loader: "ExamplesLoader"):
        self.examples_loader = examples_loader
        self._block_pattern = re.compile(r'<(\w+)>([\s\S]*?)</\1>')

    def render(self, template: str, context: "RequestContext") -> str:
        # 第一步：处理条件注入 {#if}...{/if}
        template = self._process_conditionals(template, context)

        # 第二步：解析区块
        blocks = self._parse_blocks(template)
        rendered_parts = []

        for block_type, content in blocks:
            if block_type == "role":
                rendered_parts.append(self._render_role(content, context))
            elif block_type == "rules":
                rendered_parts.append(self._render_rules(content, context))
            elif block_type == "examples":
                rendered_parts.append(self._render_examples(content, context))
            elif block_type == "output_format":
                rendered_parts.append(self._render_output_format(content, context))
            else:
                # 未知区块保留原文
                rendered_parts.append(content.strip())

        # 第三步：如果没有区块，保留原始模板（处理后）
        if not rendered_parts:
            result = template
        else:
            result = "\n\n".join(rendered_parts)

        # 第四步：替换剩余变量
        result = self._inject_variables(result, context)
        return result

    def _process_conditionals(self, template: str, context: "RequestContext") -> str:
        """解析 {#if var}...{/if} 条件，空值时移除区块"""
        pattern = re.compile(r'\{#if\s+(\w+)\}([\s\S]*?)\{/if\}')

        def replacer(match):
            var_name = match.group(1)
            content = match.group(2)
            value = getattr(context, var_name, None)
            if value and (not isinstance(value, str) or value.strip()):
                return content
            return ""

        return pattern.sub(replacer, template)

    def _parse_blocks(self, template: str) -> List[Tuple[str, str]]:
        """解析模板中的所有区块"""
        return self._block_pattern.findall(template)

    def _render_role(self, content: str, context: "RequestContext") -> str:
        return content.strip()

    def _render_rules(self, content: str, context: "RequestContext") -> str:
        """解析 <rule priority="N"> 并按 priority 排序"""
        rules = []
        for match in re.finditer(r'<rule priority="(\d+)">([\s\S]*?)</rule>', content):
            try:
                priority = int(match.group(1))
                rule_text = match.group(2).strip()
                if rule_text:
                    rules.append((priority, rule_text))
            except (ValueError, TypeError):
                rules.append((99, match.group(2).strip()))
        # Also handle rules without priority attribute
        for match in re.finditer(r'<rule>([\s\S]*?)</rule>', content):
            rule_text = match.group(1).strip()
            if rule_text:
                # Check if this rule wasn't already captured with priority
                already_captured = False
                for _, existing_text in rules:
                    if existing_text == rule_text:
                        already_captured = True
                        break
                if not already_captured:
                    rules.append((99, rule_text))
        rules.sort(key=lambda x: x[0])
        return "\n".join(f"- {r[1]}" for r in rules)

    def _render_examples(self, content: str, context: "RequestContext") -> str:
        """从 ExamplesLoader 选取 N 条，注入变量"""
        intent = context.intent or "chat"
        count = context.few_shot_count if context.few_shot_count else 3

        if not context.examples_enabled:
            return ""

        examples = self.examples_loader.get_examples(intent)
        if not examples:
            logger.warning(f"[TemplateRenderer] No examples for intent: {intent}")
            return ""

        selected = examples[:count]
        parts = []
        for i, ex in enumerate(selected, 1):
            input_text = self._inject_variables(ex.get("input", ""), context)
            output_text = self._inject_variables(ex.get("output", ""), context)
            parts.append(f"**示例 {i}**：\n用户：{input_text}\n助手：{output_text}")

        return "\n\n".join(parts)

    def _render_output_format(self, content: str, context: "RequestContext") -> str:
        return f"**输出格式要求**：\n{content.strip()}"

    def _inject_variables(self, text: str, context: "RequestContext") -> str:
        """变量替换

        支持:
        - {user_message}: 原始用户消息
        - {slots}: 格式化的槽位
        - {memories}: 格式化的记忆
        - {tool_results}: 格式化的工具结果
        - {intent}, {output_format} 等上下文字段
        """
        result = text.replace("{user_message}", context.message)
        if context.slots:
            result = result.replace("{slots}", PromptService.format_slots(context.slots))
        if context.memories:
            result = result.replace("{memories}", PromptService.format_memories(context.memories))
        if context.tool_results:
            result = result.replace("{tool_results}", PromptService.format_tool_results(context.tool_results))

        # 处理其他上下文变量（如 intent, output_format 等）
        def replace_context_var(match):
            var_name = match.group(1)
            value = getattr(context, var_name, None)
            if value is None:
                return match.group(0)  # 保留原始占位符
            return str(value)

        result = re.sub(r'\{(\w+)\}', replace_context_var, result)
        return result
