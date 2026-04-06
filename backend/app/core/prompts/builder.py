"""提示词构建器

参考 Claude Code 系统提示组装模式。
"""

import logging
from pathlib import Path
from typing import List, Optional, Callable
from .layers import PromptLayer, PromptLayerDef

logger = logging.getLogger(__name__)

# Claude Code 风格的记忆文件路径
MEMORY_FILE_PATHS = [
    Path(".claude/memory/user.md"),       # 用户级偏好
    Path(".claude/memory/project.md"),     # 项目级记忆
    Path(".claude/memory/team.md"),       # 团队共享知识
]


def load_memory_files(base_path: Optional[Path] = None) -> str:
    """加载记忆文件，参考 Claude Code memoryMechanicsPrompt 模式

    从指定目录加载 markdown 格式的记忆文件，组装为统一的提示词片段。
    这些内容会在请求时自动注入到系统提示词中。

    Args:
        base_path: 基础路径，默认为当前工作目录

    Returns:
        格式化的记忆内容字符串，如果无记忆文件则返回空字符串
    """
    if base_path is None:
        base_path = Path.cwd()

    memories = []
    for rel_path in MEMORY_FILE_PATHS:
        full_path = base_path / rel_path
        if full_path.exists() and full_path.is_file():
            try:
                content = full_path.read_text(encoding="utf-8").strip()
                if content:
                    memories.append(f"### {rel_path.name}\n{content}")
                    logger.debug(f"[PromptBuilder] 加载记忆文件: {rel_path}")
            except Exception as e:
                logger.warning(f"[PromptBuilder] 加载记忆文件失败: {rel_path} - {e}")

    if not memories:
        return ""

    header = """## 相关记忆

以下是你之前了解到的相关信息，请结合这些内容回答，但不要明确提及"根据记忆"：
"""
    return header + "\n\n".join(memories)


class PromptBuilder:
    """提示词构建器

    按层级组装提示词，支持条件触发。
    """

    def __init__(self):
        self._layers: List[PromptLayerDef] = []

    def add_layer(
        self,
        name: str,
        content: str,
        layer: PromptLayer = PromptLayer.DEFAULT,
        condition: Optional[Callable[[], bool]] = None
    ) -> None:
        """添加提示词层"""
        layer_def = PromptLayerDef(name, content, layer, condition)
        self._layers.append(layer_def)
        logger.debug(f"[PromptBuilder] Added layer: {name} at {layer.name}")

    def build(self) -> str:
        """构建最终提示词"""
        sorted_layers = sorted(self._layers, key=lambda x: x.layer.value)
        parts = []
        for layer_def in sorted_layers:
            if layer_def.should_apply():
                parts.append(f"# {layer_def.name}\n{layer_def.content}\n")
        return "\n".join(parts)

    def clear(self) -> None:
        """清空所有层"""
        self._layers.clear()

    def remove_layer(self, name: str) -> bool:
        """移除指定层"""
        original_length = len(self._layers)
        self._layers = [l for l in self._layers if l.name != name]
        return len(self._layers) < original_length


# 预定义的系统提示词模板
DEFAULT_SYSTEM_PROMPT = """你是一个专业的旅游助手 AI，可以帮助用户：

1. 规划旅游行程
2. 推荐景点和活动
3. 提供天气和交通信息
4. 根据用户偏好给出建议

请使用友好、专业的语气与用户交流。
"""

APPEND_TOOL_DESCRIPTION = "\n\n## 可用工具\n你可以使用以下工具来获取信息：\n{tools}"
