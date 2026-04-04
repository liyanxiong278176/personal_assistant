"""ContextGuard - 上下文守卫主类

提供统一的前置/后置处理入口，协调 Cleaner、Compressor 和 RuleReinjector。

处理流程:
1. pre_process: 调用 Cleaner 清理过期工具结果
2. post_process: 判断是否需要压缩 → 生成摘要 → 规则重注入
"""

import logging
from typing import Dict, List, Optional

from ..llm.client import LLMClient
from ..errors import AgentError
from .config import ContextConfig, get_default_config
from .cleaner import ContextCleaner
from .compressor import ContextCompressor
from .reinjector import RuleReinjector
from .tokenizer import TokenEstimator
from .summary import LLMSummaryProvider

logger = logging.getLogger(__name__)


class ContextGuard:
    """上下文守卫 - 统一的前置/后置处理入口

    协调 Cleaner、Compressor 和 RuleReinjector 提供完整的上下文管理能力。

    Attributes:
        config: 上下文配置
        cleaner: 前置清理器
        compressor: 上下文压缩器
        reinjector: 规则重注入器
        _summary_provider: 摘要生成器
    """

    def __init__(
        self,
        config: Optional[ContextConfig] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        """初始化上下文守卫

        Args:
            config: 上下文配置，默认使用 get_default_config()
            llm_client: 可选的 LLM 客户端，用于摘要生成
        """
        self.config = config or get_default_config()
        self.cleaner = ContextCleaner(
            ttl_seconds=self.config.tool_result_ttl_seconds,
            max_result_chars=self.config.max_tool_result_chars,
            protected_roles=set(self.config.protected_message_types),
        )
        self.compressor = ContextCompressor(
            max_tokens=int(self.config.window_size * self.config.compress_threshold),
            compression_threshold=1.0,  # 压缩逻辑由 should_compress 控制
            keep_recent=10,
        )
        self.reinjector = RuleReinjector(self.config)
        self._llm_client = llm_client
        self._summary_provider: Optional[LLMSummaryProvider] = None

        # 统计信息
        self._stats = {
            "pre_process_count": 0,
            "post_process_count": 0,
            "force_compress_count": 0,
            "should_compress_count": 0,
            "compression_triggered_count": 0,
        }

    def _get_summary_provider(self) -> LLMSummaryProvider:
        """获取或创建摘要生成器

        Returns:
            LLMSummaryProvider 实例
        """
        if self._summary_provider is None:
            api_key = None
            if self._llm_client is not None:
                api_key = getattr(self._llm_client, "api_key", None)
            self._summary_provider = LLMSummaryProvider(
                api_key=api_key,
                model=self.config.summary_model,
                max_retries=self.config.max_summary_retries,
            )
        return self._summary_provider

    def should_compress(self, messages: List[Dict]) -> bool:
        """判断是否超过 75% 窗口阈值

        Args:
            messages: 当前消息列表

        Returns:
            True 如果需要压缩，False 否则
        """
        self._stats["should_compress_count"] += 1

        if not messages:
            return False

        current_tokens = TokenEstimator.estimate_messages(messages)
        threshold = self.config.window_size * self.config.compress_threshold

        result = current_tokens >= threshold
        if result:
            logger.debug(
                f"[ContextGuard] Compression needed: {current_tokens} >= {threshold} "
                f"(threshold: {self.config.compress_threshold})"
            )
        return result

    async def pre_process(self, messages: List[Dict]) -> List[Dict]:
        """阶段3: 上下文前置清理

        调用 Cleaner 对消息列表进行清理，包括：
        1. TTL 检查 - 标记过期的工具结果
        2. 软修剪 - 超长结果保留首尾
        3. 硬清除 - 替换过期结果为占位符

        Args:
            messages: 原始消息列表

        Returns:
            清理后的消息列表（新列表，不修改原列表）
        """
        self._stats["pre_process_count"] += 1

        if not messages:
            return []

        # 调用清理器进行自动清理（软修剪 + 硬清除）
        cleaned = self.cleaner.clean(messages, mode="auto")
        logger.debug(f"[ContextGuard] Pre-process: {len(messages)} -> {len(cleaned)} messages")
        return cleaned

    async def post_process(self, messages: List[Dict]) -> List[Dict]:
        """阶段7: 上下文后置管理

        压缩协调和规则重注入：
        1. 判断是否需要压缩
        2. 需要压缩时进行摘要压缩
        3. 规则重注入

        Args:
            messages: 当前消息列表

        Returns:
            处理后的消息列表
        """
        self._stats["post_process_count"] += 1

        if not messages:
            return []

        # 判断是否需要压缩
        if not self.should_compress(messages):
            logger.debug("[ContextGuard] Post-process: no compression needed")
            return messages

        self._stats["compression_triggered_count"] += 1
        logger.info(f"[ContextGuard] Post-process: triggering compression for {len(messages)} messages")

        # 执行压缩
        compressed = await self._compress_messages(messages)

        # 规则重注入
        if self.config.rules_cache:
            compressed = self.reinjector.reinject(compressed, self.config.rules_cache)

        return compressed

    async def force_compress(self, messages: List[Dict]) -> List[Dict]:
        """手动触发压缩（混合模式支持）

        强制对消息列表进行压缩，不检查阈值。

        Args:
            messages: 原始消息列表

        Returns:
            压缩后的消息列表
        """
        self._stats["force_compress_count"] += 1

        if not messages:
            return []

        logger.info(f"[ContextGuard] Force compress: {len(messages)} messages")

        # 使用简单压缩方法
        compressed = self._simple_compress_with_summary(messages)

        # 规则重注入
        if self.config.rules_cache:
            compressed = self.reinjector.reinject(compressed, self.config.rules_cache)

        return compressed

    async def _compress_messages(self, messages: List[Dict]) -> List[Dict]:
        """执行消息压缩

        Args:
            messages: 原始消息列表

        Returns:
            压缩后的消息列表
        """
        # 提取 system 消息
        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]

        if not other_messages:
            return messages

        # 生成摘要
        summary_provider = self._get_summary_provider()
        summary_text = await summary_provider.generate_summary(other_messages)

        # 构建压缩后的消息
        result: List[Dict] = []

        # 添加 system 消息
        result.extend(system_messages)

        # 添加摘要消息
        if summary_text:
            result.append({
                "role": "system",
                "content": f"[历史对话摘要]\n{summary_text}",
                "_compressed": True,
            })

        # 保留最近 40% 的消息（确保对话连贯性）
        keep_count = max(1, int(len(other_messages) * 0.4))
        recent_messages = other_messages[-keep_count:]
        result.extend(recent_messages)

        logger.debug(
            f"[ContextGuard] Compressed: {len(messages)} -> {len(result)} messages "
            f"(kept {keep_count} recent)"
        )
        return result

    def _simple_compress_with_summary(self, messages: List[Dict]) -> List[Dict]:
        """简单压缩方法（无 LLM 调用）

        保留 system 消息 + 简单摘要 + 最近 40% 消息。

        Args:
            messages: 原始消息列表

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return []

        # 提取 system 消息
        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]

        result: List[Dict] = []

        # 添加 system 消息
        result.extend(system_messages)

        if not other_messages:
            return result

        # 生成简单摘要（计数信息）
        user_count = sum(1 for m in other_messages if m.get("role") == "user")
        assistant_count = sum(1 for m in other_messages if m.get("role") == "assistant")
        tool_count = sum(1 for m in other_messages if m.get("role") == "tool")

        summary_text = (
            f"历史对话包含 {user_count} 条用户消息、"
            f"{assistant_count} 条助手回复、{tool_count} 条工具调用。"
            f"这些内容已被压缩以节省上下文空间。"
        )

        # 添加摘要消息
        result.append({
            "role": "system",
            "content": f"[历史对话摘要]\n{summary_text}",
            "_compressed": True,
        })

        # 保留最近 40% 的消息
        keep_count = max(1, int(len(other_messages) * 0.4))
        recent_messages = other_messages[-keep_count:]
        result.extend(recent_messages)

        logger.debug(
            f"[ContextGuard] Simple compress: {len(messages)} -> {len(result)} messages"
        )
        return result

    def get_stats(self) -> Dict:
        """获取处理统计信息

        Returns:
            包含统计信息的字典
        """
        return {
            "window_size": self.config.window_size,
            "compress_threshold": self.config.compress_threshold,
            "pre_process_count": self._stats["pre_process_count"],
            "post_process_count": self._stats["post_process_count"],
            "force_compress_count": self._stats["force_compress_count"],
            "should_compress_count": self._stats["should_compress_count"],
            "compression_triggered_count": self._stats["compression_triggered_count"],
            "sub_components": {
                "cleaner": self.cleaner.get_stats(),
                "compressor": self.compressor.get_compression_stats([]),
                "reinjector_config": {
                    "rules_files": self.config.rules_files,
                    "rules_cache_size": len(self.config.rules_cache),
                    "rules_reinject_window": self.config.rules_reinject_window,
                    "rules_reinject_interval": self.config.rules_reinject_interval,
                },
            },
        }


__all__ = ["ContextGuard"]
