"""提示词层级定义"""

from enum import Enum
from typing import Optional, Callable


class PromptLayer(Enum):
    """提示词层级优先级

    数字越小优先级越高（越后应用）
    参考 Claude Code 系统提示分层设计
    """
    OVERRIDE = 0      # 测试/调试用，完全替换
    DEFAULT = 50      # 标准系统提示词
    MEMORY = 75       # 记忆文件层（CLAUDE.md 等）参考 Claude Code memoryMechanicsPrompt
    APPEND = 100      # 总是追加（如工具描述）


class PromptLayerDef:
    """提示词层定义"""

    def __init__(
        self,
        name: str,
        content: str,
        layer: PromptLayer,
        condition: Optional[Callable[[], bool]] = None
    ):
        self.name = name
        self.content = content
        self.layer = layer
        self.condition = condition

    def should_apply(self) -> bool:
        """判断是否应该应用此层"""
        if self.condition is None:
            return True
        return self.condition()
