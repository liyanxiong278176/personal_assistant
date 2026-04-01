"""上下文管理器

提供统一的上下文管理接口���集成 Token 估算和压缩功能。

功能:
1. 添加/获取消息
2. 获取当前 token 计数
3. 自动触发压缩
4. 清空上下文
5. 保留/恢复上下文状态
"""

import logging
from copy import deepcopy
from typing import Dict, List, Optional, Union

from .compressor import ContextCompressor
from .tokenizer import TokenEstimator

logger = logging.getLogger(__name__)


class ContextManager:
    """上下文管理器类

    管理对话上下文，提供消息存储、Token 计数和自动压缩功能。
    """

    def __init__(
        self,
        max_tokens: int = ContextCompressor.DEFAULT_MAX_TOKENS,
        compression_threshold: float = ContextCompressor.DEFAULT_COMPRESSION_THRESHOLD,
        keep_recent: int = ContextCompressor.DEFAULT_KEEP_RECENT,
        auto_compress: bool = True,
    ):
        """初始化上下文管理器

        Args:
            max_tokens: 最大允许的 token 数量
            compression_threshold: 压缩触发阈值（0-1 之间）
            keep_recent: 保留的最近消息数量
            auto_compress: 是否自动压缩
        """
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold
        self.keep_recent = keep_recent
        self.auto_compress = auto_compress

        # 消息存储
        self._messages: List[Dict[str, str]] = []

        # 压缩器
        self._compressor = ContextCompressor(
            max_tokens=max_tokens,
            compression_threshold=compression_threshold,
            keep_recent=keep_recent,
        )

        # 压缩历史（用于调试）
        self._compression_history: List[Dict] = []

    def add_message(
        self,
        role: str,
        content: str,
        name: Optional[str] = None,
    ) -> None:
        """添加一条消息

        Args:
            role: 消息角色 (system/user/assistant/tool)
            content: 消息内容
            name: 可选的消息名称
        """
        message: Dict[str, str] = {"role": role, "content": content}

        if name is not None:
            message["name"] = name

        self._messages.append(message)

        # 自动压缩检查
        if self.auto_compress and self._compressor.needs_compaction(self._messages):
            logger.info("Auto-compression triggered")
            self.compress()

    def add_messages(self, messages: List[Dict[str, str]]) -> None:
        """批量添加消息

        Args:
            messages: 消息列表
        """
        for message in messages:
            self._messages.append(message)

        # 自动压缩检查
        if self.auto_compress and self._compressor.needs_compaction(self._messages):
            logger.info("Auto-compression triggered after batch add")
            self.compress()

    def get_messages(
        self,
        include_system: bool = True,
        max_count: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """获取消息列表

        Args:
            include_system: 是否包含 system 消息
            max_count: 最多返回的消息数量（从最新的开始）

        Returns:
            消息列表的副本
        """
        messages = self._messages.copy()

        # 过滤 system 消息
        if not include_system:
            messages = [m for m in messages if m.get("role") != "system"]

        # 限制数量
        if max_count is not None and max_count > 0:
            messages = messages[-max_count:]

        return deepcopy(messages)

    def get_token_count(self) -> int:
        """获取当前消息列表的 token 估算数

        Returns:
            估算的 token 数量
        """
        return TokenEstimator.estimate_messages(self._messages)

    def get_message_count(self) -> int:
        """获取当前消息数量

        Returns:
            消息总数
        """
        return len(self._messages)

    def compress(self, llm_summary: Optional[str] = None) -> List[Dict[str, str]]:
        """手动触发压缩

        Args:
            llm_summary: 可选的 LLM 生成的历史摘要

        Returns:
            压缩后的消息列表
        """
        original_count = len(self._messages)
        original_tokens = self.get_token_count()

        self._messages = self._compressor.compress(self._messages, llm_summary)

        # 记录压缩历史
        self._compression_history.append({
            "original_count": original_count,
            "compressed_count": len(self._messages),
            "original_tokens": original_tokens,
            "compressed_tokens": self.get_token_count(),
            "tokens_saved": original_tokens - self.get_token_count(),
        })

        logger.info(
            f"Manual compression: {original_count} -> {len(self._messages)} messages, "
            f"{original_tokens} -> {self.get_token_count()} tokens"
        )

        return self._messages.copy()

    def compress_with_summary(
        self,
        summary_func: Optional[callable] = None,
    ) -> tuple[List[Dict[str, str]], Optional[str]]:
        """压缩并生成摘要

        Args:
            summary_func: 可选的摘要生成函数

        Returns:
            (压缩后的消息列表, 生成的摘要)
        """
        messages, summary = self._compressor.compress_with_summary(
            self._messages,
            summary_func,
        )
        self._messages = messages

        # 记录压缩历史
        if summary:
            self._compression_history.append({
                "type": "compress_with_summary",
                "compressed_count": len(self._messages),
                "compressed_tokens": self.get_token_count(),
                "summary": summary[:100] + "..." if len(summary) > 100 else summary,
            })

        return messages.copy(), summary

    def clear(self, keep_system: bool = False) -> None:
        """清空消息列表

        Args:
            keep_system: 是否保留 system 消息
        """
        if keep_system:
            self._messages = [m for m in self._messages if m.get("role") == "system"]
        else:
            self._messages = []

        logger.info(f"Context cleared (keep_system={keep_system})")

    def get_stats(self) -> Dict:
        """获取上下文统计信息

        Returns:
            包含详细统计信息的字典
        """
        token_count = self.get_token_count()
        message_count = self.get_message_count()

        # 按角色统计
        role_counts: Dict[str, int] = {}
        for message in self._messages:
            role = message.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "message_count": message_count,
            "token_count": token_count,
            "max_tokens": self.max_tokens,
            "usage_ratio": token_count / self.max_tokens if self.max_tokens > 0 else 0,
            "role_counts": role_counts,
            "compression_count": len(self._compression_history),
            "needs_compression": self._compressor.needs_compaction(self._messages),
        }

    def get_compression_history(self) -> List[Dict]:
        """获取压缩历史记录

        Returns:
            压缩历史列表
        """
        return deepcopy(self._compression_history)

    def export_state(self) -> Dict:
        """导出当前状态

        Returns:
            包含当前状态的字典
        """
        return {
            "messages": deepcopy(self._messages),
            "stats": self.get_stats(),
            "compression_history": self._compression_history,
        }

    def import_state(self, state: Dict) -> None:
        """导入状态

        Args:
            state: 之前导出的状态字典
        """
        self._messages = deepcopy(state.get("messages", []))
        self._compression_history = state.get("compression_history", [])

        logger.info(f"State imported: {len(self._messages)} messages")

    def set_max_tokens(self, max_tokens: int) -> None:
        """设置最大 token 限制

        Args:
            max_tokens: 新的最大 token 数量
        """
        self.max_tokens = max_tokens
        self._compressor.max_tokens = max_tokens

    def set_compression_threshold(self, threshold: float) -> None:
        """设置压缩阈值

        Args:
            threshold: 新的压缩阈值（0-1 之间）
        """
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")

        self.compression_threshold = threshold
        self._compressor.compression_threshold = threshold

    def set_keep_recent(self, keep_recent: int) -> None:
        """设置保留消息数量

        Args:
            keep_recent: 新的保留消息数量
        """
        self.keep_recent = keep_recent
        self._compressor.keep_recent = keep_recent


__all__ = ["ContextManager"]
