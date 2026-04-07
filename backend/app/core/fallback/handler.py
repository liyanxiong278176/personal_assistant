"""Unified Fallback Handler

统一的降级处理机制，用于处理 Agent 系统中的各种错误情况。
提供用户友好的错误消息和重试建议。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Any

from app.core.errors import AgentError, DegradationLevel


class FallbackType(Enum):
    """降级类型

    定义 Agent 系统可能遇到的不同类型的降级情况。
    """
    LLM_ERROR = "llm_error"  # LLM 服务错误
    TOOL_ERROR = "tool_error"  # 工具调用错误
    MEMORY_ERROR = "memory_error"  # 记忆服务错误
    NETWORK_ERROR = "network_error"  # 网络连接错误
    GENERIC = "generic"  # 通用错误


@dataclass
class FallbackResponse:
    """降级响应

    包含降级类型、用户消息和重试建议的响应对象。
    """
    type: FallbackType
    message: str
    can_retry: bool = True
    retry_after_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "type": self.type.value,
            "message": self.message,
            "can_retry": self.can_retry,
            "retry_after_seconds": self.retry_after_seconds,
        }


class UnifiedFallbackHandler:
    """统一降级处理器

    根据错误类型和上下文生成适当的降级响应。
    支持自定义消息和默认消息配置。
    """

    DEFAULT_MESSAGES: Dict[FallbackType, str] = {
        FallbackType.LLM_ERROR: "抱歉，AI 服务暂时不可用，请稍后再试。",
        FallbackType.TOOL_ERROR: "抱歉，部分功能暂时无法使用，您可以继续对话。",
        FallbackType.MEMORY_ERROR: "记忆服务暂时不可用，您的偏好可能不会被保存。",
        FallbackType.NETWORK_ERROR: "网络连接出现问题，请检查网络后重试。",
        FallbackType.GENERIC: "服务暂时不可用，请稍后再试。",
    }

    # 重试延迟配置（秒）
    RETRY_DELAYS: Dict[FallbackType, float] = {
        FallbackType.LLM_ERROR: 2.0,
        FallbackType.TOOL_ERROR: 1.0,
        FallbackType.MEMORY_ERROR: 1.5,
        FallbackType.NETWORK_ERROR: 3.0,
        FallbackType.GENERIC: 2.0,
    }

    def __init__(
        self,
        custom_messages: Optional[Dict[FallbackType, str]] = None,
        default_messages: Optional[Dict[FallbackType, str]] = None,
    ):
        """初始化降级处理器

        Args:
            custom_messages: 自定义消息覆盖
            default_messages: 自定义默认消息（如果不提供，使用 DEFAULT_MESSAGES）
        """
        self._messages = (default_messages or self.DEFAULT_MESSAGES).copy()
        if custom_messages:
            self._messages.update(custom_messages)

    def get_fallback(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> FallbackResponse:
        """获取降级响应

        根据错误类型和上下文生成适当的降级响应。

        Args:
            error: 捕获的异常
            context: 额外的上下文信息

        Returns:
            FallbackResponse: 降级响应对象
        """
        fallback_type = self._classify_error(error)
        message = self._messages.get(fallback_type, self.DEFAULT_MESSAGES[FallbackType.GENERIC])

        # 如果是 AgentError 且有自定义消息，使用其消息
        if isinstance(error, AgentError) and error.message:
            message = error.message

        can_retry = True
        retry_after = self.RETRY_DELAYS.get(fallback_type, 2.0)

        # 根据上下文调整响应
        if context:
            can_retry = context.get("can_retry", can_retry)
            if "retry_after" in context:
                retry_after = context["retry_after"]
            if "custom_message" in context:
                message = context["custom_message"]

        return FallbackResponse(
            type=fallback_type,
            message=message,
            can_retry=can_retry,
            retry_after_seconds=retry_after,
        )

    def _classify_error(self, error: Exception) -> FallbackType:
        """分类错误类型

        根据异常类型确定对应的降级类型。

        Args:
            error: 捕获的异常

        Returns:
            FallbackType: 对应的降级类型
        """
        # 检查 AgentError 的降级级别
        if isinstance(error, AgentError):
            if error.level == DegradationLevel.LLM_DEGRADED:
                return FallbackType.LLM_ERROR
            if error.level == DegradationLevel.TOOL_DEGRADED:
                return FallbackType.TOOL_ERROR
            if error.level == DegradationLevel.MEMORY_DEGRADED:
                return FallbackType.MEMORY_ERROR

        # 根据异常类名分类
        error_name = error.__class__.__name__.lower()
        error_module = error.__class__.__module__.lower() if hasattr(error.__class__, "__module__") else ""

        # LLM 相关错误
        if any(name in error_name for name in ["llm", "openai", "anthropic", "completion", "chat"]):
            return FallbackType.LLM_ERROR

        # 工具相关错误
        if any(name in error_name for name in ["tool", "function", "invocation"]):
            return FallbackType.TOOL_ERROR

        # 记忆相关错误
        if any(name in error_name for name in ["memory", "vector", "embedding", "storage"]):
            return FallbackType.MEMORY_ERROR

        # 网络相关错误
        if any(name in error_name for name in ["network", "connection", "timeout", "http", "request"]) or \
           any(name in error_module for name in ["httpx", "aiohttp", "urllib"]):
            return FallbackType.NETWORK_ERROR

        return FallbackType.GENERIC

    def set_message(self, fallback_type: FallbackType, message: str) -> None:
        """设置指定降级类型的消息

        Args:
            fallback_type: 降级类型
            message: 自定义消息
        """
        self._messages[fallback_type] = message

    def get_message(self, fallback_type: FallbackType) -> str:
        """获取指定降级类型的消息

        Args:
            fallback_type: 降级类型

        Returns:
            str: 对应的消息
        """
        return self._messages.get(fallback_type, self.DEFAULT_MESSAGES.get(fallback_type, ""))
