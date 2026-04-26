"""TemplateRenderer - 结构化 Markdown 模板渲染器

解析 <role>/<rules>/<examples>/<output_format> 区块，
处理 {#if}/{/if} 条件注入，{% include %} 共享片段引入，
调用 ExamplesLoader 获取示例。
"""

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, List, Tuple, Any, Dict

if TYPE_CHECKING:
    from app.core.context import RequestContext
    from app.core.prompts.examples_loader import ExamplesLoader

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


# Formatting functions (moved from PromptService to avoid circular import)
def format_slots(slots: Any) -> str:
    """格式化槽位结果为字符串.

    返回格式（不带标题）:
    - 目的地: xxx
    - 日期: xxx

    Args:
        slots: 槽位对象或字典

    Returns:
        格式化的槽位字符串
    """
    parts = []

    # 处理字典类型的 slots
    if isinstance(slots, dict):
        destination = slots.get("destination") or slots.get("destinations")
        if destination:
            if isinstance(destination, list):
                parts.append(f"- 目的地: {', '.join(destination)}")
            else:
                parts.append(f"- 目的地: {destination}")

        if slots.get("start_date"):
            parts.append(f"- 日期: {slots['start_date']}")
            if slots.get("end_date") and slots["end_date"] != slots["start_date"]:
                parts.append(f"  至 {slots['end_date']}")
        if slots.get("days"):
            parts.append(f"- 天数: {slots['days']}")
        if slots.get("travelers"):
            parts.append(f"- 人数: {slots['travelers']}人")
        if slots.get("budget"):
            parts.append(f"- 预算档次: {slots['budget']}")

    # 处理对象类型的 slots
    elif hasattr(slots, "__dict__"):
        if hasattr(slots, "destination") and slots.destination:
            parts.append(f"- 目的地: {slots.destination}")
        if hasattr(slots, "destinations") and slots.destinations:
            parts.append(f"- 目的地: {', '.join(slots.destinations)}")
        if hasattr(slots, "start_date") and slots.start_date:
            parts.append(f"- 日期: {slots.start_date}")
            if hasattr(slots, "end_date") and slots.end_date and slots.end_date != slots.start_date:
                parts.append(f"  至 {slots.end_date}")
        if hasattr(slots, "days") and slots.days:
            parts.append(f"- 天数: {slots.days}")
        if hasattr(slots, "travelers") and slots.travelers:
            parts.append(f"- 人数: {slots.travelers}人")
        if hasattr(slots, "budget") and slots.budget:
            parts.append(f"- 预算档次: {slots.budget}")

    return "\n".join(parts) if parts else "未提取到槽位信息"


def format_memories(memories: List[Any]) -> str:
    """格式化记忆列表为字符串.

    返回格式（不带标题）:
    1. xxx
    2. yyy

    Args:
        memories: 记忆列表

    Returns:
        格式化的记忆字符串
    """
    if not memories:
        return "无相关记忆"

    parts = []
    for i, memory in enumerate(memories[:10], 1):
        if isinstance(memory, dict):
            content = memory.get("content", str(memory))
        elif hasattr(memory, "content"):
            content = memory.content
        else:
            content = str(memory)
        parts.append(f"{i}. {content}")

    return "\n".join(parts) if parts else "无相关记忆"


def format_tool_results(results: Dict[str, Any]) -> str:
    """格式化工具结果为字符串.

    返回格式（不带标题）:
    tool_name: {...}
    tool_name2: ...

    Args:
        results: 工具执行结果字典

    Returns:
        格式化的工具结果字符串
    """
    if not results:
        return "无工具调用结果"

    parts = []
    for tool_name, result in results.items():
        # 错误处理
        if isinstance(result, dict) and "error" in result:
            parts.append(f"{tool_name}: 错误 - {result['error']}")
        elif isinstance(result, dict):
            # 使用 JSON 格式化字典结果
            try:
                result_str = json.dumps(result, ensure_ascii=False)
                parts.append(f"{tool_name}: {result_str}")
            except Exception:
                parts.append(f"{tool_name}: {result}")
        elif isinstance(result, str):
            parts.append(f"{tool_name}: {result}")
        else:
            parts.append(f"{tool_name}: {result}")

    return "\n".join(parts) if parts else "无工具调用结果"


class TemplateRenderer:
    """解析 Markdown 中的 <role>/<rules>/<examples>/<output_format> 区块"""

    def __init__(self, examples_loader: "ExamplesLoader"):
        self.examples_loader = examples_loader
        self._block_pattern = re.compile(r'<(\w+)>([\s\S]*?)</\1>')

    def render(self, template: str, context: "RequestContext") -> str:
        # 第一步：处理 {% include %} 共享片段引入
        template = self._process_includes(template)

        # 第二步：处理条件注入 {#if}...{/if}
        template = self._process_conditionals(template, context)

        # 第三步：就地替换区块标签，保留周围的文本
        def replace_block(match):
            block_type = match.group(1)
            content = match.group(2)
            if block_type == "role":
                return self._render_role(content, context)
            elif block_type == "rules":
                return self._render_rules(content, context)
            elif block_type == "examples":
                return self._render_examples(content, context)
            elif block_type == "output_format":
                return self._render_output_format(content, context)
            else:
                return content.strip()

        result = self._block_pattern.sub(replace_block, template)

        # 第四步：替换剩余变量
        result = self._inject_variables(result, context)
        return result

    def _process_includes(self, template: str, visited: set = None) -> str:
        """处理 {% include "filename" %} 指令，引入共享模板片段"""
        if visited is None:
            visited = set()

        pattern = re.compile(r'\{%\s*include\s+"([^"]+)"\s*%\}')

        def replacer(match):
            filename = match.group(1)
            if filename in visited:
                return ""
            file_path = TEMPLATES_DIR / filename
            try:
                content = file_path.read_text(encoding="utf-8").strip()
                visited.add(filename)
                return self._process_includes(content, visited)
            except FileNotFoundError:
                return ""

        return pattern.sub(replacer, template)

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
            result = result.replace("{slots}", format_slots(context.slots))
        if context.memories:
            result = result.replace("{memories}", format_memories(context.memories))
        if context.tool_results:
            result = result.replace("{tool_results}", format_tool_results(context.tool_results))

        # 处理其他上下文变量（如 intent, output_format 等）
        def replace_context_var(match):
            var_name = match.group(1)
            value = getattr(context, var_name, None)
            if value is None:
                return match.group(0)  # 保留原始占位符
            return str(value)

        result = re.sub(r'\{(\w+)\}', replace_context_var, result)
        return result
