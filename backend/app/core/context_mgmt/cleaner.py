"""上下文清理器

提供前置清理功能，用于在上下文管理之前清理过期的工具结果。

清理策略:
1. TTL 检查 - 标记过期的工具结果
2. 软修剪 - 超长结果保留首尾（TRIM_KEEP_CHARS = 1500）
3. 硬清除 - 替换过期结果为占位符

保护规则:
- 保护 user/system 消息不被清除
- 保护以 "## " 开头的规则消息
"""

import logging
import time
from typing import Dict, List, Literal, Set

logger = logging.getLogger(__name__)

# 常量定义
TRIM_KEEP_CHARS = 1500  # 软修剪时保留的首尾字符数
CLEARED_PLACEHOLDER = "[Old result cleared]"  # 硬清除时使用的占位符
TRIM_INDICATOR = "...[trimmed]..."  # 软修剪时插入的指示符

# TTL配置：7天（D1-3 修复：与文档要求一致）
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # 604800秒 = 7天

# 消息长度限制：约2000 tokens（D1-4 修复：与文档要求一致）
# 假设 1 token ≈ 4 字符（中文），2000 tokens ≈ 8000 字符
DEFAULT_MAX_CHARS = 8000


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


def _log_cleaner_soft_trim(role: str, original_len: int, trimmed_len: int):
    """软修剪日志"""
    logger.info(
        f"[CLEANER] ✂️ 软修剪 | role={role} | "
        f"{original_len} → {trimmed_len}字符 | 节省={original_len - trimmed_len}字符"
    )


def _log_cleaner_hard_clear(role: str):
    """硬清除日志"""
    logger.info(
        f"[CLEANER] 🗑️ 硬清除 | role={role} | "
        f"内容已替换为占位符"
    )


def _log_cleaner_protected(role: str, reason: str):
    """保护跳过日志"""
    logger.debug(
        f"[CLEANER] 🛡️ 保护跳过 | role={role} | 原因={reason}"
    )


def _log_cleaner_result(mode: str, input_count: int, output_count: int,
                        expired_count: int, trimmed_count: int, cleared_count: int):
    """清理结果汇总日志"""
    logger.info(
        f"[CLEANER] 📊 清理结果 | mode={mode} | "
        f"输入={input_count}条 → 输出={output_count}条 | "
        f"过期={expired_count} 修剪={trimmed_count} 清除={cleared_count}"
    )


CleanMode = Literal["soft", "hard", "auto"]


class ContextCleaner:
    """上下文清理器类

    提供前置清理功能，用于在上下文管理之前清理过期的工具结���。
    """

    def __init__(
        self,
        ttl_seconds: int = None,
        max_result_chars: int = None,
        protected_roles: Set[str] | None = None,
    ):
        """初始化上下文清理器

        Args:
            ttl_seconds: 工具结果的生存时间（秒），默认 7天（604800秒）
            max_result_chars: 单条消息的最大字符数，默认 8000（约2000 tokens）
            protected_roles: 受保护的消息角色集合，默认 {"user", "system"}
        """
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL_SECONDS
        self.max_result_chars = max_result_chars if max_result_chars is not None else DEFAULT_MAX_CHARS
        self.protected_roles = (
            set(protected_roles) if protected_roles else {"user", "system"}
        )

    def clean(
        self,
        messages: List[Dict[str, str]],
        mode: CleanMode = "auto",
    ) -> List[Dict[str, str]]:
        """清理消息列表

        Args:
            messages: 原始消息列表
            mode: 清理模式
                - "soft": 软修剪，只修剪过长的内容
                - "hard": 硬清除，清除过期的工具结果
                - "auto": 自动模式，根据消息内容决定

        Returns:
            清理后的消息列表（新列表，不修改原列表）

        Raises:
            ValueError: 当 mode 不是有效值时
        """
        if mode not in ("soft", "hard", "auto"):
            raise ValueError(
                f"Invalid clean mode: {mode}. Must be 'soft', 'hard', or 'auto'"
            )

        if not messages:
            return []

        # 复制消息列表以避免修改原列表
        cleaned = [msg.copy() for msg in messages]

        if mode == "soft":
            cleaned = self._soft_clean(cleaned)
        elif mode == "hard":
            cleaned = self._hard_clean(cleaned)
        else:  # auto
            cleaned = self._auto_clean(cleaned)

        # 统计清理结果
        expired_count = sum(1 for m in cleaned if m.get("_expired"))
        trimmed_count = sum(1 for m in cleaned if m.get("_trimmed"))
        cleared_count = sum(1 for m in cleaned if m.get("_cleared"))

        _log_cleaner_result(mode, len(messages), len(cleaned),
                           expired_count, trimmed_count, cleared_count)
        return cleaned

    def _soft_clean(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """软清理：修剪过长的工具结果

        Args:
            messages: 消息列表

        Returns:
            修剪后的消息列表
        """
        trimmed_count = 0
        for message in messages:
            role = message.get("role", "unknown")
            if self._is_protected(message):
                _log_cleaner_protected(role, "受保护角色/规则")
                continue

            content = message.get("content")
            if content and isinstance(content, str):
                trimmed = self._soft_trim(content)
                if trimmed != content:
                    message["content"] = trimmed
                    message["_trimmed"] = True
                    trimmed_count += 1
                    _log_cleaner_soft_trim(role, len(content), len(trimmed))

        return messages

    def _hard_clean(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """硬清理：清除过期的工具结果

        Args:
            messages: 消息列表

        Returns:
            清除后的消息列表
        """
        cleared_count = 0
        for message in messages:
            role = message.get("role", "unknown")
            if self._is_protected(message):
                _log_cleaner_protected(role, "受保护角色/规则")
                continue

            if self._check_ttl(message):
                cleared = self._hard_clear(message)
                message["content"] = cleared["content"]
                message["_cleared"] = True
                cleared_count += 1
                _log_cleaner_hard_clear(role)

        return messages

    def _auto_clean(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """自动清理：结合软修剪和硬清除

        Args:
            messages: 消息列表

        Returns:
            清理后的消息列表
        """
        # 先进行软修剪
        result = self._soft_clean(messages)
        # 再进行硬清除
        result = self._hard_clean(result)
        return result

    def _check_ttl(self, message: Dict[str, str]) -> bool:
        """检查消息是否过期（D3-2 修复：扩展到所有消息类型）

        Args:
            message: 消息字典

        Returns:
            True 如果消息已过期，False 否则
        """
        role = message.get("role", "unknown")

        # D3-2 修复：不同角色使用不同的TTL
        # - tool消息: 使用配置的TTL（默认7天）
        # - user/assistant消息: 也使用相同TTL（历史上下文过期）
        # - system消息: 永不过期
        if role == "system":
            return False

        # 没有时间戳的消息视为新鲜（向后兼容）
        timestamp = message.get("_timestamp")
        if timestamp is None:
            # 对于user/assistant消息，检查是否有其他时间标识
            # 如果都没有，视为不过期
            return False

        # 检查是否过期
        current_time = time.time()
        age = current_time - timestamp
        is_expired = age >= self.ttl_seconds

        if is_expired:
            _log_cleaner_ttl_check(
                role,
                is_expired, age, self.ttl_seconds
            )

        return is_expired

    def _soft_trim(self, content: str) -> str:
        """软修剪：超长内容保留首尾

        Args:
            content: 原始内容

        Returns:
            修剪后的内容
        """
        if not content or len(content) <= self.max_result_chars:
            return content

        # 计算保留的字符数
        keep_chars = TRIM_KEEP_CHARS
        if keep_chars * 2 >= self.max_result_chars:
            # 如果保留字符数超过限制，调整它
            keep_chars = self.max_result_chars // 2 - 10

        # 保留首尾
        prefix = content[:keep_chars]
        suffix = content[-keep_chars:]

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

    def _is_protected(self, message: Dict[str, str]) -> bool:
        """检查消息是否受保护

        受保护的条件：
        1. 角色在 protected_roles 中
        2. 内容以 "## " 开头（规则消息）

        Args:
            message: 消息字典

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

        return False

    def get_stats(self) -> Dict:
        """获取清理器统计信息

        Returns:
            包含配置信息的字典
        """
        return {
            "ttl_seconds": self.ttl_seconds,
            "max_result_chars": self.max_result_chars,
            "protected_roles": list(self.protected_roles),
            "trim_keep_chars": TRIM_KEEP_CHARS,
            "cleared_placeholder": CLEARED_PLACEHOLDER,
        }


__all__ = [
    "ContextCleaner",
    "TRIM_KEEP_CHARS",
    "CLEARED_PLACEHOLDER",
    "CleanMode",
]
