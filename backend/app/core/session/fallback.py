import logging
from typing import Dict, Any, Optional

from .state import ErrorCategory
from .structured_logger import SessionPhase, log_event, LogLevel

logger = logging.getLogger(__name__)

# 降级响应模板
FALLBACK_MESSAGES = {
    "weather": "天气查询暂时不可用，基于历史平均数据为您规划行程。",
    "map": "地图功能暂不可用，以下是文字版路线描述。",
    "partial": "部分信息获取失败，已为您生成基于可用信息的行程。",
    "memory": "记忆服务暂不可用，本次对话偏好不会被保存。",
    "llm": "AI服务暂时繁忙，请稍后再试。",
    "default": "服务暂时不可用，请稍后再试。"
}

class FallbackResponse:
    """降级响应"""
    def __init__(
        self,
        should_degrade: bool,
        message: str,
        partial_results: Optional[Dict[str, Any]] = None
    ):
        self.should_degrade = should_degrade
        self.message = message
        self.partial_results = partial_results or {}

class FallbackHandler:
    """降级处理器

    根据错误类型生成降级响应，支持部分结果降级。
    """

    def __init__(self, custom_messages: Optional[Dict[str, str]] = None):
        """初始化降级处理器

        Args:
            custom_messages: 自定义降级消息
        """
        self._messages = {**FALLBACK_MESSAGES, **(custom_messages or {})}
        logger.info("[FallbackHandler] 初始化完成")

    def get_fallback(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> FallbackResponse:
        """获取降级响应

        Args:
            error: 发生的异常
            context: 错误上下文（包含部分结果等）

        Returns:
            FallbackResponse: 降级响应
        """
        error_type = type(error).__name__
        logger.info(f"[FallbackHandler] 生成降级响应: {error_type}")

        # 根据错误类型选择消息
        message_key = "default"
        partial_results = {}

        # 从上下文中提取部分结果
        if context:
            partial_results = context.get("partial_results", {})

            # 根据可用的部分结果调整消息
            if "weather" in partial_results and "map" not in partial_results:
                message_key = "map"
            elif "map" in partial_results and "weather" not in partial_results:
                message_key = "weather"
            elif partial_results:
                message_key = "partial"

        # 特殊错误类型的消息
        if "TimeoutError" in error_type or "ConnectionError" in error_type:
            if "llm" in str(error).lower() or "openai" in str(error).lower():
                message_key = "llm"
        elif "memory" in error_type.lower() or "chroma" in error_type.lower():
            message_key = "memory"

        message = self._messages.get(message_key, self._messages["default"])

        # 记录结构化日志
        log_event(
            LogLevel.INFO,
            SessionPhase.FALLBACK,
            f"生成降级响应: {error_type}",
            error_type=error_type,
            message_key=message_key,
            has_partial_results=bool(partial_results),
            partial_result_keys=list(partial_results.keys()) if partial_results else []
        )

        return FallbackResponse(
            should_degrade=True,
            message=message,
            partial_results=partial_results
        )

    def format_response(self, fallback: FallbackResponse) -> str:
        """格式化降级响应用于输出

        Args:
            fallback: 降级响应对象

        Returns:
            格式化的响应文本
        """
        if fallback.partial_results:
            # 有部分结果时，友好地展示
            parts = [fallback.message]
            if fallback.partial_results.get("weather"):
                parts.append(f"\n\n✓ 已获取天气信息")
            if fallback.partial_results.get("map"):
                parts.append(f"\n\n✓ 已获取路线信息")
            return "".join(parts)

        return fallback.message
