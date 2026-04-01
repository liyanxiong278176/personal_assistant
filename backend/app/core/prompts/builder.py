"""提示词构��器"""

import logging
from typing import List, Optional, Callable
from .layers import PromptLayer, PromptLayerDef

logger = logging.getLogger(__name__)


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
