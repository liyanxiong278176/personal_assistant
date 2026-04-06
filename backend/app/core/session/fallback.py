import logging
from typing import Dict, Any, Optional, List

from .state import ErrorCategory
from .structured_logger import SessionPhase, log_event, LogLevel

logger = logging.getLogger(__name__)

# UC7-1 修复: 三层降级策略

# 降级响应模板
FALLBACK_MESSAGES = {
    "weather": "天气查询暂时不可用，基于历史平均数据为您规划行程。",
    "map": "地图功能暂不可用，以下是文字版路线描述。",
    "partial": "部分信息获取失败，已为您生成基于可用信息的行程。",
    "memory": "记忆服务暂不可用，本次对话偏好不会被保存。",
    "llm": "AI服务暂时繁忙，请稍后再试。",
    # UC7-1 修复: 三层降级消息
    "degrade_llm_partial": "AI服务响应受限，以下是基于已知信息的简要回答。",
    "degrade_llm_minimal": "AI服务暂时不可用，以下是您可能感兴趣的信息。",
    "degrade_all_tools_failed": "服务暂时不可用，请稍后再试。",
    "default": "服务暂时不可用，请稍后再试。"
}

# 旅行知识兜底库
TRAVEL_KNOWLEDGE_BASE = {
    "常见目的地": [
        "成都：推荐景点有宽窄巷子、锦里、大熊猫基地",
        "重庆：推荐景点有解放碑、洪崖洞、武隆天坑",
        "杭州：推荐景点有西湖、灵隐寺、宋城",
        "云南：推荐景点有丽江古城、大理古城、香格里拉",
    ],
    "旅行建议": [
        "提前查看天气预报，合理安排衣物",
        "热门景点建议提前预约门票",
        "品尝当地美食是旅行的重要体验",
    ],
    "注意事项": [
        "保管好个人财物和证件",
        "提前了解当地文化和习俗",
        "保持手机电量充足",
    ]
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

    UC7-1 修复: 三层降级策略
    - L1: 功能降级（部分工具失败，返回基于已知信息的回答）
    - L2: 数据降级（所有工具失败，返回预设知识库内容）
    - L3: 兜底响应（完全不可用，返回友好提示）
    """

    def __init__(self, custom_messages: Optional[Dict[str, str]] = None):
        """初始化降级处理器

        Args:
            custom_messages: 自定义降级消息
        """
        self._messages = {**FALLBACK_MESSAGES, **(custom_messages or {})}
        logger.info("[FallbackHandler] 初始化完成 | 三层降级策略已启用")

    def get_degradation_level(
        self,
        error: Exception,
        partial_results: Optional[Dict[str, Any]] = None
    ) -> int:
        """UC7-1修复: 确定降级级别

        Returns:
            1=L1功能降级, 2=L2数据降级, 3=L3兜底
        """
        error_type = type(error).__name__
        error_msg = str(error).lower()

        # L3: LLM完全不可用
        if any(kw in error_msg for kw in ["llm", "openai", "api_key", "rate limit", "quota"]):
            return 3

        # L2: 所有工具都失败
        if partial_results and not partial_results.get("available_tools"):
            return 2

        # L1: 部分工具失败
        if partial_results and partial_results.get("failed_tools"):
            return 1

        return 1  # 默认L1

    def get_fallback(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> FallbackResponse:
        """获取降级响应

        UC7-1 修复: 三层降级策略

        Args:
            error: 发生的异常
            context: 错误上下文（包含部分结果等）

        Returns:
            FallbackResponse: 降级响应
        """
        error_type = type(error).__name__
        partial_results = context.get("partial_results", {}) if context else {}

        # UC7-1修复: 确定降级级别
        degradation_level = self.get_degradation_level(error, partial_results)

        # 根据降级级别生成消息
        if degradation_level == 1:
            # L1: 功能降级
            message_key = "partial"
            message = self._messages.get(message_key)
        elif degradation_level == 2:
            # L2: 数据降级，返回旅行知识库
            message_key = "degrade_llm_partial"
            message = self._messages.get(message_key)
            # 添加旅行知识库内容
            knowledge = self._get_travel_knowledge(context)
            message = f"{message}\n\n{knowledge}"
        else:
            # L3: 兜底响应
            message_key = "degrade_all_tools_failed"
            message = self._messages.get(message_key)

        logger.info(
            f"[FallbackHandler] 生成降级响应 | "
            f"level={degradation_level} | message_key={message_key}"
        )

        # 记录结构化日志
        log_event(
            LogLevel.INFO,
            SessionPhase.FALLBACK,
            f"生成降级响应: {error_type}",
            error_type=error_type,
            message_key=message_key,
            degradation_level=degradation_level,
            has_partial_results=bool(partial_results),
            partial_result_keys=list(partial_results.keys()) if partial_results else []
        )

        return FallbackResponse(
            should_degrade=True,
            message=message,
            partial_results=partial_results
        )

    def _get_travel_knowledge(self, context: Optional[Dict[str, Any]]) -> str:
        """UC7-1 修复: 从旅行知识库中获取相关内容"""
        parts = ["📚 **以下是一些旅行建议：**"]

        for category, tips in TRAVEL_KNOWLEDGE_BASE.items():
            parts.append(f"\n**{category}:**")
            for tip in tips[:3]:  # 最多3条
                parts.append(f"- {tip}")

        return "\n".join(parts)

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
