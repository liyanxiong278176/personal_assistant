"""ContextGuard - 上下文守卫主类

提供统一的前置/后置处理入口，协调 Cleaner、Compressor 和 RuleReinjector。

处理流程:
1. pre_process: 调用 Cleaner 清理过期工具结果
2. post_process: 判断是否需要压缩 → 生成摘要 → 规则重注入
"""

import logging
import time
from typing import Dict, List, Optional

from ..llm.client import LLMClient
from .config import ContextConfig, get_default_config
from .cleaner import ContextCleaner
from .compressor import ContextCompressor
from .reinjector import RuleReinjector
from .tokenizer import TokenEstimator
from .summary import LLMSummaryProvider

logger = logging.getLogger(__name__)

# ============================================================
# 结构化日志宏 - 提供统一的日志格式
# ============================================================
# 格式: [模块] 阶段 | 操作 | conv=X | 详情...


def _log_guard_preprocess(conv_id: str, input_count: int, output_count: int,
                          expired_count: int, trimmed_count: int, cleared_count: int,
                          elapsed_ms: float):
    """ContextGuard 前置清理 - 结构化日志"""
    logger.info(
        f"[CTX_GUARD] 📥 前置清理完成 | conv={conv_id} | "
        f"输入={input_count}条 → 输出={output_count}条 | "
        f"过期={expired_count} 修剪={trimmed_count} 清除={cleared_count} | "
        f"耗时={elapsed_ms:.2f}ms"
    )


def _log_guard_postprocess(conv_id: str, input_count: int, output_count: int,
                            compressed: bool, should_compress: bool,
                            tokens: int, threshold: int,
                            rules_injected: bool, elapsed_ms: float):
    """ContextGuard 后置管理 - 结构化日志"""
    action = "压缩+规则注入" if compressed else "仅规则检查"
    logger.info(
        f"[CTX_GUARD] 📤 后置管理完成 | conv={conv_id} | "
        f"输入={input_count}条 → 输出={output_count}条 | "
        f"操作={action} | "
        f"是否压缩={should_compress}({tokens}≥{threshold}) | "
        f"规则注入={rules_injected} | "
        f"耗时={elapsed_ms:.2f}ms"
    )


def _log_guard_should_compress(conv_id: str, tokens: int, threshold: int,
                               result: bool, message_count: int):
    """ContextGuard 压缩判断 - 结构化日志"""
    ratio = (tokens / threshold * 100) if threshold > 0 else 0
    symbol = "🔴" if result else "🟢"
    logger.info(
        f"[CTX_GUARD] {symbol} 压缩判断 | conv={conv_id} | "
        f"消息={message_count}条 | token={tokens}/{threshold}({ratio:.1f}%) | "
        f"阈值={threshold} | 结果={'需要压缩' if result else '无需压缩'}"
    )


def _log_guard_force_compress(conv_id: str, input_count: int, output_count: int,
                              compressed: bool, rules_injected: bool, elapsed_ms: float):
    """ContextGuard 强制压缩 - 结构化日志"""
    logger.info(
        f"[CTX_GUARD] 💪 强制压缩 | conv={conv_id} | "
        f"输入={input_count}条 → 输出={output_count}条 | "
        f"压缩={compressed} | 规则注入={rules_injected} | "
        f"耗时={elapsed_ms:.2f}ms"
    )


def _log_guard_compress_summary(conv_id: str, original_count: int, summary_tokens: int,
                                 kept_recent: int, result_count: int,
                                 method: str, elapsed_ms: float):
    """ContextGuard 摘要压缩 - 结构化日志"""
    logger.info(
        f"[CTX_GUARD] 📝 摘要压缩 | conv={conv_id} | "
        f"原始={original_count}条 | 摘要token≈{summary_tokens} | "
        f"保留最近={kept_recent}条 | 结果={result_count}条 | "
        f"方式={method} | 耗时={elapsed_ms:.2f}ms"
    )


def _log_guard_init(config: ContextConfig, has_llm: bool, rules_count: int):
    """ContextGuard 初始化 - 结构化日志"""
    logger.info(
        f"[CTX_GUARD] 🏗️ 初始化完成 | "
        f"窗口={config.window_size} | 压缩阈值={config.compress_threshold} | "
        f"TTL={config.tool_result_ttl_seconds}s | "
        f"LLM={'已配置' if has_llm else '未配置'} | "
        f"规则缓存={rules_count}个文件"
    )


def _log_guard_stats(conv_id: str, stats: Dict):
    """ContextGuard 统计信息 - 结构化日志"""
    logger.info(
        f"[CTX_GUARD] 📊 统计 | conv={conv_id} | "
        f"前置={stats.get('pre_process_count',0)} | "
        f"后置={stats.get('post_process_count',0)} | "
        f"压缩触发={stats.get('compression_triggered_count',0)} | "
        f"强制压缩={stats.get('force_compress_count',0)}"
    )


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
        self._last_conv_id: str = "unknown"

        # 统计信息
        self._stats = {
            "pre_process_count": 0,
            "post_process_count": 0,
            "force_compress_count": 0,
            "should_compress_count": 0,
            "compression_triggered_count": 0,
            "total_expired_cleaned": 0,
            "total_trimmed": 0,
            "total_cleared": 0,
            "total_compressed": 0,
            "total_rules_injected": 0,
        }

        _log_guard_init(
            self.config,
            llm_client is not None,
            len(self.config.rules_cache)
        )

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
        """判断是否超过压缩阈值

        Args:
            messages: 当前消息列表

        Returns:
            True 如果需要压缩，False 否则
        """
        self._stats["should_compress_count"] += 1

        if not messages:
            return False

        current_tokens = TokenEstimator.estimate_messages(messages)
        threshold = int(self.config.window_size * self.config.compress_threshold)

        result = current_tokens >= threshold
        _log_guard_should_compress(
            self._last_conv_id, current_tokens, threshold,
            result, len(messages)
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
        start_time = time.perf_counter()

        if not messages:
            return []

        # 调用清理器进行自动清理（软修剪 + 硬清除）
        cleaned = self.cleaner.clean(messages, mode="auto")

        # 获取清理统计
        cleaner_stats = self.cleaner.get_stats()
        expired_count = sum(
            1 for m in cleaned if m.get("_expired")
        )
        trimmed_count = sum(
            1 for m in cleaned if m.get("_trimmed")
        )
        cleared_count = sum(
            1 for m in cleaned if m.get("_cleared")
        )

        self._stats["total_expired_cleaned"] += expired_count
        self._stats["total_trimmed"] += trimmed_count
        self._stats["total_cleared"] += cleared_count

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _log_guard_preprocess(
            self._last_conv_id,
            len(messages), len(cleaned),
            expired_count, trimmed_count, cleared_count,
            elapsed_ms
        )
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
        start_time = time.perf_counter()

        if not messages:
            return []

        # 判断是否需要压缩
        current_tokens = TokenEstimator.estimate_messages(messages)
        threshold = int(self.config.window_size * self.config.compress_threshold)
        should_comp = current_tokens >= threshold

        result = list(messages)
        compressed = False
        rules_injected = False

        if should_comp:
            self._stats["compression_triggered_count"] += 1
            self._stats["total_compressed"] += 1

            # 执行压缩
            result = await self._compress_messages(result)
            compressed = len(result) < len(messages)

        # 规则重注入
        if self.config.rules_cache:
            before_reinject = len(result)
            result = self.reinjector.reinject(result, self.config.rules_cache)
            rules_injected = len(result) > before_reinject
            if rules_injected:
                self._stats["total_rules_injected"] += 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _log_guard_postprocess(
            self._last_conv_id,
            len(messages), len(result),
            compressed, should_comp,
            current_tokens, threshold,
            rules_injected, elapsed_ms
        )
        return result

    async def force_compress(self, messages: List[Dict]) -> List[Dict]:
        """手动触发压缩（混合模式支持）

        强制对消息列表进行压缩，不检查阈值。

        Args:
            messages: 原始消息列表

        Returns:
            压缩后的消息列表
        """
        self._stats["force_compress_count"] += 1
        start_time = time.perf_counter()

        if not messages:
            return []

        # 使用简单压缩方法
        compressed = self._simple_compress_with_summary(messages)

        # 规则重注入
        rules_injected = False
        if self.config.rules_cache:
            before_reinject = len(compressed)
            compressed = self.reinjector.reinject(compressed, self.config.rules_cache)
            rules_injected = len(compressed) > before_reinject

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _log_guard_force_compress(
            self._last_conv_id,
            len(messages), len(compressed),
            len(compressed) < len(messages), rules_injected,
            elapsed_ms
        )
        return compressed

    async def _compress_messages(self, messages: List[Dict]) -> List[Dict]:
        """执行消息压缩（LLM驱动）

        Args:
            messages: 原始消息列表

        Returns:
            压缩后的消息列表
        """
        start_time = time.perf_counter()
        original_count = len(messages)

        # 提取 system 消息
        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]

        if not other_messages:
            return messages

        # 生成摘要
        summary_provider = self._get_summary_provider()
        summary_text = await summary_provider.generate_summary(other_messages)
        summary_tokens = TokenEstimator.count_tokens(summary_text)

        # 构建压缩后的消息
        result: List[Dict] = []
        result.extend(system_messages)

        if summary_text:
            result.append(
                {
                    "role": "system",
                    "content": f"[历史对话摘要]\n{summary_text}",
                    "_compressed": True,
                }
            )

        keep_count = max(1, int(len(other_messages) * 0.4))
        recent_messages = other_messages[-keep_count:]
        result.extend(recent_messages)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _log_guard_compress_summary(
            self._last_conv_id,
            original_count, summary_tokens,
            keep_count, len(result),
            "LLM摘要", elapsed_ms
        )
        return result

    def _simple_compress_with_summary(self, messages: List[Dict]) -> List[Dict]:
        """简单压缩方法（无 LLM 调用，降级方案）

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

        result.append(
            {
                "role": "system",
                "content": f"[历史对话摘要]\n{summary_text}",
                "_compressed": True,
            }
        )

        keep_count = max(1, int(len(other_messages) * 0.4))
        recent_messages = other_messages[-keep_count:]
        result.extend(recent_messages)

        _log_guard_compress_summary(
            self._last_conv_id,
            len(messages), 0,
            keep_count, len(result),
            "降级计数摘要", 0
        )
        return result

    def get_stats(self) -> Dict:
        """获取处理统计信息

        Returns:
            包含统计信息的字典
        """
        stats = {
            "window_size": self.config.window_size,
            "compress_threshold": self.config.compress_threshold,
            "pre_process_count": self._stats["pre_process_count"],
            "post_process_count": self._stats["post_process_count"],
            "force_compress_count": self._stats["force_compress_count"],
            "should_compress_count": self._stats["should_compress_count"],
            "compression_triggered_count": self._stats["compression_triggered_count"],
            "total_expired_cleaned": self._stats["total_expired_cleaned"],
            "total_trimmed": self._stats["total_trimmed"],
            "total_cleared": self._stats["total_cleared"],
            "total_compressed": self._stats["total_compressed"],
            "total_rules_injected": self._stats["total_rules_injected"],
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
        _log_guard_stats(self._last_conv_id, stats)
        return stats

    def set_conv_id(self, conv_id: str):
        """设置当前会话ID（用于日志记录）

        Args:
            conv_id: 会话ID
        """
        self._last_conv_id = conv_id


__all__ = ["ContextGuard"]
