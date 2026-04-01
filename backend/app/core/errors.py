"""Agent Core 错误定义

定义 Agent 系统使用的错误类型、降级级别和降级策略。
"""

from enum import Enum
from typing import Optional


class AgentError(Exception):
    """Agent 基础错误类

    所有 Agent Core 相关错误的基类。
    """

    def __init__(self, message: str, level: Optional["DegradationLevel"] = None, details: Optional[dict] = None):
        self.message = message
        self.level = level
        self.details = details or {}
        super().__init__(message)


class DegradationLevel(Enum):
    """降级级别

    定义不同组件降级时的严重程度。
    """
    LLM_DEGRADED = "llm_degraded"  # LLM 服务不可用
    TOOL_DEGRADED = "tool_degraded"  # 工具调用失败
    MEMORY_DEGRADED = "memory_degraded"  # 记忆服务不可用
    CONTEXT_DEGRADED = "context_degraded"  # 上下文管理失败


class DegradationStrategy:
    """降级策略

    定义不同降级级别下的用户响应消息。
    """

    _MESSAGES = {
        DegradationLevel.LLM_DEGRADED: "抱歉，AI 服务暂时不可用，请稍后再试。",
        DegradationLevel.TOOL_DEGRADED: "抱歉，部分功能暂时无法使用，您可以继续对话。",
        DegradationLevel.MEMORY_DEGRADED: "记忆服务暂时不可用，您的偏好可能不会被保存。",
        DegradationLevel.CONTEXT_DEGRADED: "上下文加载出现问题，建议重新开始对话。",
    }

    @classmethod
    def get_message(cls, level: DegradationLevel) -> str:
        """获取指定降级级别的用户消息

        Args:
            level: 降级级别

        Returns:
            str: 用户友好的错误消息
        """
        return cls._MESSAGES.get(level, "服务暂时不可用，请稍后再试。")
