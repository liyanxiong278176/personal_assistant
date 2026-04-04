"""摘要生成器

提供 LLM 驱动的对话历史摘要生成功能。
支持异步摘要生成和同步降级方案。
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable

from ..llm.client import LLMClient

logger = logging.getLogger(__name__)


# ============================================================
# 结构化日志宏
# ============================================================


def _log_summary_start(message_count: int, total_chars: int):
    """摘要开始日志"""
    logger.info(
        f"[SUMMARY] 📝 开始生成摘要 | "
        f"消息数={message_count} | 总字符≈{total_chars}"
    )


def _log_summary_llm_call(attempt: int, max_retries: int):
    """LLM调用日志"""
    logger.info(
        f"[SUMMARY] 🤖 LLM摘要调用 | 第{attempt}/{max_retries}次尝试"
    )


def _log_summary_fallback(message_count: int, user_count: int,
                          assistant_count: int, tool_count: int):
    """降级摘要日志"""
    logger.info(
        f"[SUMMARY] 📉 使用降级摘要 | "
        f"消息={message_count}条 | "
        f"用户={user_count} 助手={assistant_count} 工具={tool_count}"
    )


def _log_summary_complete(tokens: int, elapsed_ms: float, method: str):
    """摘要完成日志"""
    logger.info(
        f"[SUMMARY] ✅ 摘要生成完成 | "
        f"方法={method} | token≈{tokens} | 耗时={elapsed_ms:.2f}ms"
    )


def _log_summary_no_llm():
    """无LLM日志"""
    logger.info(
        f"[SUMMARY] ⚠️ LLM客户端不可用 | 使用降级方案"
    )


def _log_summary_init(model: str, max_retries: int, timeout: float):
    """初始化日志"""
    logger.info(
        f"[SUMMARY] 🏗️ 初始化 | "
        f"模型={model} | 最大重试={max_retries} | 超时={timeout}s"
    )

# DeepSeek API endpoint (OpenAI compatible)
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 默认摘要系统提示词
DEFAULT_SUMMARY_PROMPT = """请为以下对话历史生成简洁的摘要。
摘要应包含：
1. 主要讨论的话题
2. 用户的关键问题或需求
3. 已提供的重要信息或解决方案
4. 工具调用的结果（如果有）

摘要应该简洁明了，便于后续对���参考。"""


class LLMSummaryProvider:
    """LLM 摘要生成器

    使用 LLM 生成对话历史的智能摘要。
    当 LLM 不可用时，自动降级到简单的计数摘要。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
        max_retries: int = 3,
        max_chars_per_message: int = 500,
        timeout: float = 30.0,
    ):
        """初始化摘要生成器

        Args:
            api_key: DeepSeek API key，如果为 None 则从环境变量读取
            model: 使用的模型名称
            max_retries: 最大重试次数
            max_chars_per_message: 每条消息的最大字符数（超过会截断）
            timeout: API 请求超时时间（秒）
        """
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.max_chars_per_message = max_chars_per_message
        self.timeout = timeout
        self._llm_client: Optional[LLMClient] = None
        _log_summary_init(model, max_retries, timeout)

    def _get_llm_client(self) -> Optional[LLMClient]:
        """获取或创建 LLM 客户端

        Returns:
            LLMClient 实例，如果 API key 不可用则返回 None
        """
        if self._llm_client is None:
            if self.api_key:
                self._llm_client = LLMClient(
                    api_key=self.api_key,
                    model=self.model,
                    max_retries=self.max_retries,
                    timeout=self.timeout,
                )
            else:
                logger.warning("[LLMSummaryProvider] No API key available")
        return self._llm_client

    def _format_messages_for_summary(self, messages: List[Dict[str, str]]) -> str:
        """格式化消息用于摘要输入

        将消息列表转换为文本格式，每条消息限制在 max_chars_per_message 以内。
        默认排除 system 消息，因为它们通常是持久性指令。

        Args:
            messages: 原始消息列表

        Returns:
            格式化后的文本
        """
        if not messages:
            return ""

        formatted_parts = []

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # 跳过 system 消息（持久性指令）
            if role == "system":
                continue

            # 截断过长的内容
            if len(content) > self.max_chars_per_message:
                content = content[: self.max_chars_per_message] + "..."

            # 处理工具消息的特殊格式
            if role == "tool":
                tool_name = msg.get("name", "unknown_tool")
                formatted_parts.append(f"tool[{tool_name}]: {content}")
            else:
                formatted_parts.append(f"{role}: {content}")

        return "\n".join(formatted_parts)

    def _fallback_summary(self, messages: List[Dict[str, str]]) -> str:
        """生成降级摘要（简单的计数摘要）

        当 LLM 不可用时使用。

        Args:
            messages: 消息列表

        Returns:
            简单的计数摘要
        """
        if not messages:
            return "No conversation history."

        # 统计各角色的消息数量
        role_counts: Dict[str, int] = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        # 构建摘要文本
        parts = []
        if role_counts.get("user", 0) > 0:
            parts.append(f"{role_counts['user']} user message(s)")
        if role_counts.get("assistant", 0) > 0:
            parts.append(f"{role_counts['assistant']} assistant message(s)")
        if role_counts.get("tool", 0) > 0:
            parts.append(f"{role_counts['tool']} tool invocation(s)")

        if not parts:
            return "Empty conversation history."

        summary = "Conversation history contains " + ", ".join(parts) + "."
        return summary

    async def generate_summary(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """异步生成摘要

        使用 LLM 生成智能摘要，失败时降级到简单计数摘要。

        Args:
            messages: 要摘要的消息列表
            system_prompt: 可选的自定义系统提示词

        Returns:
            生成的摘要文本
        """
        if not messages:
            return "No conversation history."

        total_chars = sum(len(m.get("content", "")) for m in messages)
        _log_summary_start(len(messages), total_chars)
        start_time = time.perf_counter()

        # 获取 LLM 客户端
        llm_client = self._get_llm_client()
        if llm_client is None:
            _log_summary_no_llm()
            return self._fallback_summary(messages)

        # 格式化消息
        formatted_text = self._format_messages_for_summary(messages)
        if not formatted_text:
            result = self._fallback_summary(messages)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            _log_summary_fallback(len(messages), 0, 0, 0)
            _log_summary_complete(0, elapsed_ms, "降级计数(无格式化内容)")
            return result

        # 构建摘要请求消息
        summary_messages = [
            {
                "role": "user",
                "content": f"{system_prompt or DEFAULT_SUMMARY_PROMPT}\n\n对话历史：\n{formatted_text}",
            }
        ]

        # 尝试使用 LLM 生成摘要
        for attempt in range(self.max_retries):
            _log_summary_llm_call(attempt + 1, self.max_retries)
            try:
                summary = await llm_client.chat(
                    messages=summary_messages,
                    system_prompt=None,  # 系统提示已包含在用户消息中
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                tokens = len(summary) // 4  # 粗略估算
                _log_summary_complete(tokens, elapsed_ms, "LLM摘要")
                return summary

            except Exception as e:
                logger.warning(
                    f"[SUMMARY] ❌ LLM摘要失败 | 第{attempt + 1}/{self.max_retries}次 | 错误={e}"
                )
                if attempt < self.max_retries - 1:
                    # 指数退避
                    await asyncio.sleep(2**attempt)
                continue

        # 所有重试都失败，使用降级方案
        result = self._fallback_summary(messages)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _log_summary_complete(0, elapsed_ms, "降级计数(重试耗尽)")

        # 统计降级摘要的内容
        user_count = sum(1 for m in messages if m.get("role") == "user")
        assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
        tool_count = sum(1 for m in messages if m.get("role") == "tool")
        _log_summary_fallback(len(messages), user_count, assistant_count, tool_count)

        return result

    def create_summary_func(self) -> Callable[[List[Dict[str, str]]], str]:
        """创建同步的摘要函数

        返回一个同步函数，该函数使用降级摘要（计数）方案。
        用于需要同步接口的场景。

        Returns:
            同步摘要函数
        """

        def sync_summary_func(messages: List[Dict[str, str]]) -> str:
            """同步摘要函数（降级方案）

            Args:
                messages: 要摘要的消息列表

            Returns:
                摘要文本
            """
            return self._fallback_summary(messages)

        return sync_summary_func


def create_summary_provider(
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    max_retries: int = 3,
    max_chars_per_message: int = 500,
    timeout: float = 30.0,
) -> LLMSummaryProvider:
    """工厂函数：创建摘要生成器

    Args:
        api_key: DeepSeek API key
        model: 使用的模型名称
        max_retries: 最大重试次数
        max_chars_per_message: 每条消息的最大字符数
        timeout: API 请求超时时间（秒）

    Returns:
        LLMSummaryProvider 实例
    """
    return LLMSummaryProvider(
        api_key=api_key,
        model=model,
        max_retries=max_retries,
        max_chars_per_message=max_chars_per_message,
        timeout=timeout,
    )


__all__ = [
    "LLMSummaryProvider",
    "create_summary_provider",
    "DEFAULT_SUMMARY_PROMPT",
]
