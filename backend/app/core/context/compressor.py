"""上下文压缩器

提供智能的上下文压缩功能，当上下文超过阈值时自动压缩。

压缩策略:
1. 保留最近 N 条消息（短期记忆优先）
2. 对历史消息进行语义摘要（长期记忆压缩）
3. 保留关键信息（系统提示、重要指令等）
"""

import logging
from typing import Dict, List, Optional, Set

from .tokenizer import TokenEstimator

logger = logging.getLogger(__name__)


class ContextCompressor:
    """上下文压缩器类

    当上下文长度超过阈值时，智能压缩消息历史。
    采用多层压缩策略确保关键信息不丢失。
    """

    # 默认配置
    DEFAULT_MAX_TOKENS = 8000  # 最大 token 限制
    DEFAULT_COMPRESSION_THRESHOLD = 0.8  # 80% 时触发压缩
    DEFAULT_KEEP_RECENT = 10  # 保留最近 N 条消息
    DEFAULT_SUMMARY_TOKENS = 500  # 摘要的目标 token 数

    # 保留的消息角色（这些角色的消息优先保留）
    PRESERVED_ROLES: Set[str] = {"system"}

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD,
        keep_recent: int = DEFAULT_KEEP_RECENT,
        summary_tokens: int = DEFAULT_SUMMARY_TOKENS,
    ):
        """初始化上下文压缩器

        Args:
            max_tokens: 最大允许的 token 数量
            compression_threshold: 压缩触发阈值（0-1 之间）
            keep_recent: 保留的最近消息数量
            summary_tokens: 压缩后摘要的目标 token 数
        """
        if not 0 < compression_threshold <= 1:
            raise ValueError("compression_threshold must be between 0 and 1")

        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold
        self.keep_recent = keep_recent
        self.summary_tokens = summary_tokens

    def needs_compaction(self, messages: List[Dict[str, str]]) -> bool:
        """检查是否需要压缩

        Args:
            messages: 当前消息列表

        Returns:
            是否需要压缩
        """
        current_tokens = TokenEstimator.estimate_messages(messages)
        threshold = self.max_tokens * self.compression_threshold

        return current_tokens >= threshold

    def compress(
        self,
        messages: List[Dict[str, str]],
        llm_summary: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """压缩消息列表

        压缩策略:
        1. 保留所有 system 消息
        2. 保留最近 N 条消息
        3. 如果提供了 llm_summary，将其作为压缩上下文插入

        Args:
            messages: 原始消息列表
            llm_summary: 可选的 LLM 生成的历史摘要

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        # 如果不需要压缩，直接返回
        if not self.needs_compaction(messages):
            return messages

        logger.info(
            f"Compressing context: {len(messages)} messages -> ",
            extra={"original_count": len(messages)}
        )

        compressed: List[Dict[str, str]] = []

        # 1. 提取并保留 system 消息
        system_messages = [m for m in messages if m.get("role") == "system"]
        compressed.extend(system_messages)

        # 2. 如果有摘要，添加为上下文消息
        if llm_summary:
            compressed.append({
                "role": "system",
                "content": f"[历史对话摘要]\n{llm_summary}",
            })

        # 3. 提取非 system 消息
        non_system_messages = [m for m in messages if m.get("role") != "system"]

        # 4. 保留最近 N 条消息
        recent_messages = non_system_messages[-self.keep_recent:]
        compressed.extend(recent_messages)

        logger.info(
            f"Compression complete: {len(compressed)} messages kept",
            extra={"compressed_count": len(compressed)}
        )

        return compressed

    def compress_with_summary(
        self,
        messages: List[Dict[str, str]],
        summary_func: Optional[callable] = None,
    ) -> tuple[List[Dict[str, str]], Optional[str]]:
        """压缩消息列表并生成摘要

        Args:
            messages: 原始消息列表
            summary_func: 可选的摘要生成函数，接收消息列表返回摘要文本

        Returns:
            (压缩后的消息列表, 生成的摘要)
        """
        if not messages:
            return messages, None

        # 如果不需要压缩，直接返回
        if not self.needs_compaction(messages):
            return messages, None

        # 提取需要摘要的消息（排除 system 和保留的最近消息）
        system_messages = [m for m in messages if m.get("role") == "system"]
        non_system_messages = [m for m in messages if m.get("role") != "system"]

        messages_to_summarize = non_system_messages[:-self.keep_recent]

        # 生成摘要
        summary = None
        if messages_to_summarize:
            if summary_func:
                try:
                    summary = summary_func(messages_to_summarize)
                except Exception as e:
                    logger.warning(f"Failed to generate summary: {e}")
            else:
                # 简单的文本摘要（计数信息）
                user_count = sum(1 for m in messages_to_summarize if m.get("role") == "user")
                assistant_count = sum(1 for m in messages_to_summarize if m.get("role") == "assistant")
                summary = (
                    f"历史对话包含 {user_count} 条用户消息和 {assistant_count} 条助手回复。"
                    f"这些内容已被压缩以节省上下文空间。"
                )

        return self.compress(messages, llm_summary=summary), summary

    def get_compression_stats(self, messages: List[Dict[str, str]]) -> Dict:
        """获取压缩统计信息

        Args:
            messages: 当前消息列表

        Returns:
            包含统计信息的字典
        """
        current_tokens = TokenEstimator.estimate_messages(messages)
        threshold = self.max_tokens * self.compression_threshold

        return {
            "current_tokens": current_tokens,
            "max_tokens": self.max_tokens,
            "threshold": threshold,
            "needs_compaction": current_tokens >= threshold,
            "usage_ratio": current_tokens / self.max_tokens if self.max_tokens > 0 else 0,
            "message_count": len(messages),
        }


__all__ = ["ContextCompressor"]
