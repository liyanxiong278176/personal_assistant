"""上下文清理器 - 阶段2前置清理

提供前置清理功能，用于在上下文管理之前清理过期的工具结果。

清理策略:
1. TTL 检查 - 标记过期的工具结果（默认5分钟）
2. 上下文占用比例计算 - 计算当前草稿纸占用情况
3. 软修剪 - 占用>30% + 单条>4000字符触发，保留首尾各1500字符
4. 硬清除 - 软修剪后仍>50%触发，替换为占位符

保护规则:
- 保护 user/system/image 消息不被清除
- 保护以 "## " 开头的规则消息
- 保护 bootstrap 阶段消息
- 保护最后 N 条助手消息之后的工具结果
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Set

from .config import ContextConfig
from .tokenizer import TokenEstimator

logger = logging.getLogger(__name__)

# ============================================================
# 常量定义
# ============================================================

# 软修剪配置
HEAD_CHARS = 1500  # 保留头部字符数
TAIL_CHARS = 1500  # 保留尾部字符数
TRIM_INDICATOR = "...[trimmed]..."  # 软修剪指示符

# 硬清除配置
CLEARED_PLACEHOLDER = "[Old tool result content cleared]"

# 保护配置
LAST_N_ASSISTANT_MESSAGES = 3  # 保护最后 N 条助手消息之后的工具结果

# ============================================================
# 数据类
# ============================================================


@dataclass
class CleanStats:
    """清理统计信息"""
    input_count: int = 0
    output_count: int = 0
    expired_count: int = 0
    soft_trimmed_count: int = 0
    hard_cleared_count: int = 0
    protected_skipped_count: int = 0
    context_usage_before: float = 0.0  # 占用比例
    context_usage_after: float = 0.0
    total_chars_saved: int = 0


@dataclass
class ContextUsageInfo:
    """上下文占用信息"""
    total_tokens: int = 0
    window_size: int = 128000
    usage_ratio: float = 0.0
    char_count: int = 0


# ============================================================
# 结构化日志宏
# ============================================================


def _log_cleaner_ttl_check(role: str, expired: bool, age_seconds: float, ttl: int):
    """TTL检查日志"""
    symbol = "⏰" if expired else "✓"
    logger.debug(
        f"[CLEANER] {symbol} TTL检查 | role={role} | "
        f"过期={expired} | 存活={age_seconds:.1f}s/{ttl}s"
    )


def _log_cleaner_soft_trim(role: str, original_len: int, trimmed_len: int, usage_ratio: float):
    """软修剪日志"""
    logger.info(
        f"[CLEANER] ✂️ 软修剪 | role={role} | "
        f"{original_len} → {trimmed_len}字符 | "
        f"占用={usage_ratio:.1%} | 节省={original_len - trimmed_len}字符"
    )


def _log_cleaner_hard_clear(role: str, usage_ratio: float):
    """硬清除日志"""
    logger.info(
        f"[CLEANER] 🗑️ 硬清除 | role={role} | "
        f"占用={usage_ratio:.1%} | 内容已替换为占位符"
    )


def _log_cleaner_protected(role: str, reason: str):
    """保护跳过日志"""
    logger.debug(
        f"[CLEANER] 🛡️ 保护跳过 | role={role} | 原因={reason}"
    )


def _log_cleaner_context_usage(usage: ContextUsageInfo):
    """上下文占用日志"""
    logger.info(
        f"[CLEANER] 📊 上下文占用 | "
        f"tokens={usage.total_tokens}/{usage.window_size} | "
        f"比例={usage.usage_ratio:.1%} | 字符={usage.char_count}"
    )


def _log_cleaner_result(stats: CleanStats):
    """清理结果汇总日志"""
    logger.info(
        f"[CLEANER] 📊 清理结果 | "
        f"输入={stats.input_count}条 → 输出={stats.output_count}条 | "
        f"过期={stats.expired_count} 软修剪={stats.soft_trimmed_count} "
        f"硬清除={stats.hard_cleared_count} 保护={stats.protected_skipped_count} | "
        f"占用: {stats.context_usage_before:.1%} → {stats.context_usage_after:.1%} | "
        f"节省={stats.total_chars_saved}字符"
    )


CleanMode = Literal["soft", "hard", "auto"]


# ============================================================
# 主类
# ============================================================


class ContextCleaner:
    """上下文清理器类 - 阶段2前置清理

    提供前置清理功能，用于在上下文管理之前清理过期的工具结果。
    实现软硬修剪结合的策略，根据上下文占用比例动态调整清理强度。
    """

    def __init__(
        self,
        config: Optional[ContextConfig] = None,
        protected_roles: Optional[Set[str]] = None,
    ):
        """初始化上下文清理器

        Args:
            config: 上下文配置，默认使用 get_default_config()
            protected_roles: 受保护的消息角色集合，默认 {"user", "system", "image"}
        """
        self.config = config or ContextConfig()
        self.protected_roles = (
            set(protected_roles) if protected_roles else {"user", "system", "image"}
        )

        # 从配置获取参数
        self.ttl_seconds = self.config.tool_result_ttl_seconds  # 默认300秒(5分钟)
        self.max_tool_result_chars = self.config.max_tool_result_chars  # 默认4000字符
        self.soft_trim_ratio = self.config.soft_trim_ratio  # 默认0.3 (30%)
        self.hard_clear_ratio = self.config.hard_clear_ratio  # 默认0.5 (50%)
        self.window_size = self.config.window_size  # 默认128000

        # bootstrap 消息标记（通过 _bootstrap 标识）
        self._bootstrap_found = False
        self._last_assistant_position = -1

    def clean(
        self,
        messages: List[Dict[str, str]],
        mode: CleanMode = "auto",
    ) -> tuple[List[Dict[str, str]], CleanStats]:
        """清理消息列表

        Args:
            messages: 原始消息列表
            mode: 清理模式
                - "soft": 软修剪，只修剪过长的内容
                - "hard": 硬清除，清除过期的工具结果
                - "auto": 自动模式，根据上下文占用决定

        Returns:
            (清理后的消息列表, 清理统计信息)
        """
        if mode not in ("soft", "hard", "auto"):
            raise ValueError(
                f"Invalid clean mode: {mode}. Must be 'soft', 'hard', or 'auto'"
            )

        if not messages:
            return [], CleanStats()

        # 复制消息列表以避免修改原列表
        cleaned = [msg.copy() for msg in messages]

        # 计算初始上下文占用
        usage_before = self._calculate_context_usage(cleaned)
        _log_cleaner_context_usage(usage_before)

        stats = CleanStats(
            input_count=len(messages),
            context_usage_before=usage_before.usage_ratio,
        )

        # 扫描最后 N 条助手消息位置
        self._scan_last_assistant_position(cleaned)

        if mode == "soft":
            cleaned, stats = self._soft_clean_with_ratio(cleaned, usage_before, stats)
        elif mode == "hard":
            cleaned, stats = self._hard_clean_with_ratio(cleaned, usage_before, stats)
        else:  # auto
            # 根据上下文占用自动决定清理策略
            cleaned, stats = self._auto_clean_with_ratio(cleaned, usage_before, stats)

        # 计算最终上下文占用
        usage_after = self._calculate_context_usage(cleaned)
        stats.output_count = len(cleaned)
        stats.context_usage_after = usage_after.usage_ratio

        _log_cleaner_result(stats)
        return cleaned, stats

    def _soft_clean_with_ratio(
        self,
        messages: List[Dict[str, str]],
        usage: ContextUsageInfo,
        stats: CleanStats,
    ) -> tuple[List[Dict[str, str]], CleanStats]:
        """软清理：根据上下文占用比例修剪过长的工具结果

        触发条件：上下文占用 > soft_trim_ratio 且单条工具结果 > max_tool_result_chars

        Args:
            messages: 消息列表
            usage: 上下文占用信息
            stats: 统计信息

        Returns:
            (清理后的消息列表, 更新后的统计信息)
        """
        should_trim = usage.usage_ratio > self.soft_trim_ratio

        for i, message in enumerate(messages):
            role = message.get("role", "unknown")

            if self._is_protected(message, i):
                stats.protected_skipped_count += 1
                _log_cleaner_protected(role, "受保护角色/位置")
                continue

            content = message.get("content")
            if content and isinstance(content, str):
                content_len = len(content)

                # 检查是否需要修剪
                needs_trim = should_trim and content_len > self.max_tool_result_chars

                if needs_trim:
                    trimmed = self._soft_trim(content)
                    if trimmed != content:
                        message["content"] = trimmed
                        message["_trimmed"] = True
                        stats.soft_trimmed_count += 1
                        stats.total_chars_saved += content_len - len(trimmed)
                        _log_cleaner_soft_trim(role, content_len, len(trimmed), usage.usage_ratio)

        return messages, stats

    def _hard_clean_with_ratio(
        self,
        messages: List[Dict[str, str]],
        usage: ContextUsageInfo,
        stats: CleanStats,
    ) -> tuple[List[Dict[str, str]], CleanStats]:
        """硬清理：根据上下文占用比例清除过期的工具结果

        触发条件：软修剪后上下文占用仍 > hard_clear_ratio

        Args:
            messages: 消息列表
            usage: 上下文占用信息
            stats: 统计信息

        Returns:
            (清理后的消息列表, 更新后的统计信息)
        """
        should_clear = usage.usage_ratio > self.hard_clear_ratio

        for i, message in enumerate(messages):
            role = message.get("role", "unknown")

            if self._is_protected(message, i):
                stats.protected_skipped_count += 1
                continue

            if should_clear and self._check_ttl(message):
                original_len = len(message.get("content", ""))
                cleared = self._hard_clear(message)
                message["content"] = cleared["content"]
                message["_cleared"] = True
                stats.hard_cleared_count += 1
                stats.total_chars_saved += original_len
                _log_cleaner_hard_clear(role, usage.usage_ratio)

        return messages, stats

    def _auto_clean_with_ratio(
        self,
        messages: List[Dict[str, str]],
        usage: ContextUsageInfo,
        stats: CleanStats,
    ) -> tuple[List[Dict[str, str]], CleanStats]:
        """自动清理：结合软修剪和硬清除

        策略：
        1. 先进行软修剪（占用>30%触发）
        2. 重新计算占用
        3. 如果仍>50%，进行硬清除

        Args:
            messages: 消息列表
            usage: 上下文占用信息
            stats: 统计信息

        Returns:
            (清理后的消息列表, 更新后的统计信息)
        """
        # 阶段1：软修剪
        if usage.usage_ratio > self.soft_trim_ratio:
            messages, stats = self._soft_clean_with_ratio(messages, usage, stats)

            # 重新计算占用
            usage_after_soft = self._calculate_context_usage(messages)

            # 阶段2：如果仍超过硬清除阈值，进行硬清除
            if usage_after_soft.usage_ratio > self.hard_clear_ratio:
                messages, stats = self._hard_clean_with_ratio(messages, usage_after_soft, stats)
        else:
            # 即使不触发软修剪，也检查TTL过期
            for i, message in enumerate(messages):
                if not self._is_protected(message, i) and self._check_ttl(message):
                    original_len = len(message.get("content", ""))
                    message["content"] = CLEARED_PLACEHOLDER
                    message["_cleared"] = True
                    stats.expired_count += 1
                    stats.hard_cleared_count += 1
                    stats.total_chars_saved += original_len

        return messages, stats

    def _scan_last_assistant_position(self, messages: List[Dict[str, str]]) -> None:
        """扫描最后 N 条助手消息的位置

        Args:
            messages: 消息列表
        """
        self._last_assistant_position = -1
        count = 0

        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                count += 1
                if count >= LAST_N_ASSISTANT_MESSAGES:
                    self._last_assistant_position = i
                    break

    def _calculate_context_usage(self, messages: List[Dict[str, str]]) -> ContextUsageInfo:
        """计算上下文占用信息

        Args:
            messages: 消息列表

        Returns:
            上下文占用信息
        """
        total_tokens = TokenEstimator.estimate_messages(messages)
        char_count = sum(len(m.get("content", "")) for m in messages)

        return ContextUsageInfo(
            total_tokens=total_tokens,
            window_size=self.window_size,
            usage_ratio=total_tokens / self.window_size if self.window_size > 0 else 0,
            char_count=char_count,
        )

    def _check_ttl(self, message: Dict[str, str]) -> bool:
        """检查消息是否过期

        Args:
            message: 消息字典

        Returns:
            True 如果消息已过期，False 否则
        """
        role = message.get("role", "unknown")

        # system 消息永不过期
        if role == "system":
            return False

        # 检查时间戳
        timestamp = message.get("_timestamp")
        if timestamp is None:
            return False

        # 检查是否过期
        current_time = time.time()
        age = current_time - timestamp
        is_expired = age >= self.ttl_seconds

        if is_expired:
            _log_cleaner_ttl_check(role, is_expired, age, self.ttl_seconds)

        return is_expired

    def _soft_trim(self, content: str) -> str:
        """软修剪：超长内容保留首尾

        Args:
            content: 原始内容

        Returns:
            修剪后的内容
        """
        if not content or len(content) <= self.max_tool_result_chars:
            return content

        # 保留首尾
        prefix = content[:HEAD_CHARS]
        suffix = content[-TAIL_CHARS:]

        return f"{prefix}{TRIM_INDICATOR}{suffix}"

    def _hard_clear(self, message: Dict[str, str]) -> Dict[str, str]:
        """硬清除：替换过期结果为占位符

        Args:
            message: 原始消息

        Returns:
            清除后的消息
        """
        cleared = message.copy()
        cleared["content"] = CLEARED_PLACEHOLDER
        return cleared

    def _is_protected(self, message: Dict[str, str], position: int) -> bool:
        """检查消息是否受保护

        受保护的条件：
        1. 角色在 protected_roles 中
        2. 内容以 "## " 开头（规则消息）
        3. 标记为 _bootstrap 的消息
        4. 在最后 N 条助手消息之后的工具结果

        Args:
            message: 消息字典
            position: 消息在列表中的位置

        Returns:
            True 如果消息受保护，False 否则
        """
        # 检查角色保护
        if message.get("role") in self.protected_roles:
            return True

        # 检查规则消息保护（以 ## 开头）
        content = message.get("content", "")
        if isinstance(content, str) and content.startswith("## "):
            return True

        # 检查 bootstrap 消息保护
        if message.get("_bootstrap"):
            return True

        # 检查最后 N 条助手消息之后的工具结果
        if self._last_assistant_position >= 0 and position > self._last_assistant_position:
            if message.get("role") == "tool":
                return True

        return False

    def get_stats(self) -> Dict:
        """获取清理器配置信息

        Returns:
            包含配置信息的字典
        """
        return {
            "ttl_seconds": self.ttl_seconds,
            "max_tool_result_chars": self.max_tool_result_chars,
            "soft_trim_ratio": self.soft_trim_ratio,
            "hard_clear_ratio": self.hard_clear_ratio,
            "window_size": self.window_size,
            "protected_roles": list(self.protected_roles),
            "head_chars": HEAD_CHARS,
            "tail_chars": TAIL_CHARS,
            "last_n_assistant_messages": LAST_N_ASSISTANT_MESSAGES,
        }


__all__ = [
    "ContextCleaner",
    "CleanStats",
    "ContextUsageInfo",
    "HEAD_CHARS",
    "TAIL_CHARS",
    "TRIM_INDICATOR",
    "CLEARED_PLACEHOLDER",
    "CleanMode",
]
