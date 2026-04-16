"""工具结果上下文守卫 - 阶段3工具执行中实时守卫

在工具执行过程中实时监控上下文占用，防止单个工具结果过大占满草稿纸。

守卫策略:
1. 单条工具结果限制：最多占上下文的50%
2. 总上下文预算：留25%的缓冲
3. 超预算压缩：压缩最旧的工具结果
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from .config import ContextConfig
from .tokenizer import TokenEstimator

logger = logging.getLogger(__name__)

# ============================================================
# 常量定义
# ============================================================

# 单条工具结果最大占上下文的比例
SINGLE_TOOL_RESULT_CONTEXT_SHARE = 0.5  # 50%

# 总上下文预算缓冲比例
CONTEXT_BUDGET_BUFFER = 0.25  # 留25%缓冲

# 压缩占位符
COMPACTED_PLACEHOLDER = "[compacted: tool output removed to free context]"

# 软修剪占位符（当单条结果过大时）
TRIMMED_PLACEHOLDER = "...[tool result trimmed to fit context]..."


# ============================================================
# 数据类
# ============================================================


@dataclass
class ToolResultStats:
    """工具结果统计"""
    total_tool_results: int = 0
    total_chars: int = 0
    total_tokens: int = 0
    trimmed_count: int = 0
    compacted_count: int = 0
    chars_saved: int = 0
    tokens_saved: int = 0


@dataclass
class BudgetInfo:
    """预算信息"""
    window_size: int = 128000
    budget_tokens: int = 0  # 扣除缓冲后的可用预算
    used_tokens: int = 0
    remaining_tokens: int = 0
    usage_ratio: float = 0.0


# ============================================================
# 结构化日志宏
# ============================================================


def _log_guard_single_tool_check(
    tool_name: str,
    result_tokens: int,
    max_allowed: int,
    would_exceed: bool,
):
    """单条工具结果检查日志"""
    symbol = "🔴" if would_exceed else "🟢"
    ratio = result_tokens / max_allowed if max_allowed > 0 else 0
    logger.info(
        f"[TOOL_GUARD] {symbol} 单条检查 | tool={tool_name} | "
        f"tokens={result_tokens}/{max_allowed}({ratio:.1%}) | "
        f"{'超出限制' if would_exceed else '正常'}"
    )


def _log_guard_budget_check(budget: BudgetInfo):
    """预算检查日志"""
    logger.info(
        f"[TOOL_GUARD] 📊 预算检查 | "
        f"窗口={budget.window_size} | "
        f"预算={budget.budget_tokens}({1-CONTEXT_BUDGET_BUFFER:.0%}) | "
        f"已用={budget.used_tokens} | "
        f"剩余={budget.remaining_tokens} | "
        f"占用={budget.usage_ratio:.1%}"
    )


def _log_guard_trim(tool_name: str, original_len: int, trimmed_len: int):
    """修剪日志"""
    logger.info(
        f"[TOOL_GUARD] ✂️ 修剪结果 | tool={tool_name} | "
        f"{original_len} → {trimmed_len}字符 | 节省={original_len - trimmed_len}"
    )


def _log_guard_compact(
    oldest_tool: str,
    original_tokens: int,
    current_usage: int,
    budget: int,
):
    """压缩日志"""
    logger.info(
        f"[TOOL_GUARD] 🗜️ 压缩最旧 | tool={oldest_tool} | "
        f"原tokens={original_tokens} | 当前占用={current_usage}/{budget}"
    )


def _log_guard_result(stats: ToolResultStats):
    """守卫结果日志"""
    logger.info(
        f"[TOOL_GUARD] 📊 守卫结果 | "
        f"工具结果={stats.total_tool_results}条 | "
        f"修剪={stats.trimmed_count} 压缩={stats.compacted_count} | "
        f"节省={stats.chars_saved}字符({stats.tokens_saved}tokens)"
    )


# ============================================================
# 主类
# ============================================================


class ToolResultGuard:
    """工具结果上下文守卫 - 阶段3工具执行中实时守卫

    在工具执行过程中实时监控上下文占用，防止单个工具结果过大
    或总预算超限。

    使用方式:
        1. 在添加工具结果前调用 check_before_add() 检查
        2. 如果返回需要修剪，调用 trim_result() 修剪
        3. 如果添加后超预算，调用 compact_oldest() 压缩最旧结果
    """

    def __init__(self, config: Optional[ContextConfig] = None):
        """初始化工具结果守卫

        Args:
            config: 上下文配置
        """
        self.config = config or ContextConfig()
        self.window_size = self.config.window_size

        # 计算预算（留25%缓冲）
        self.budget_tokens = int(self.window_size * (1 - CONTEXT_BUDGET_BUFFER))

        # 单条工具结果最大限制
        self.max_single_tool_tokens = int(self.window_size * SINGLE_TOOL_RESULT_CONTEXT_SHARE)

        # 统计信息
        self._stats = ToolResultStats()

    def check_before_add(
        self,
        tool_name: str,
        result_content: str,
        current_messages: List[Dict],
    ) -> tuple[bool, Optional[str]]:
        """添加工具结果前检查

        检查添加此结果后是否会：
        1. 单条结果超过50%限制
        2. 总预算超限

        Args:
            tool_name: 工具名称
            result_content: 工具结果内容
            current_messages: 当前消息列表

        Returns:
            (是否允许添加, 警告消息)
            - 如果单条结果会超限，返回 (False, 警告)
            - 如果总预算会超限，返回 (True, 警告)（允许添加但需要后续压缩）
            - 正常情况返回 (True, None)
        """
        result_tokens = TokenEstimator.estimate(result_content)
        current_tokens = TokenEstimator.estimate_messages(current_messages)

        # 检查单条结果限制
        would_exceed_single = result_tokens > self.max_single_tool_tokens
        _log_guard_single_tool_check(
            tool_name, result_tokens, self.max_single_tool_tokens, would_exceed_single
        )

        if would_exceed_single:
            return False, f"工具结果过大({result_tokens}tokens)，超过单条限制({self.max_single_tool_tokens}tokens)"

        # 检查总预算
        would_exceed_budget = (current_tokens + result_tokens) > self.budget_tokens
        budget_info = BudgetInfo(
            window_size=self.window_size,
            budget_tokens=self.budget_tokens,
            used_tokens=current_tokens,
            remaining_tokens=max(0, self.budget_tokens - current_tokens),
            usage_ratio=current_tokens / self.budget_tokens if self.budget_tokens > 0 else 0,
        )
        _log_guard_budget_check(budget_info)

        if would_exceed_budget:
            return (
                True,
                f"添加后将超预算({current_tokens + result_tokens}/{self.budget_tokens})，需要压缩",
            )

        return True, None

    def trim_result(
        self,
        tool_name: str,
        result_content: str,
        max_chars: Optional[int] = None,
    ) -> str:
        """修剪工具结果

        当结果过大时，保留首尾部分。

        Args:
            tool_name: 工具名称
            result_content: 原始结果内容
            max_chars: 最大字符数，默认使用配置值

        Returns:
            修剪后的内容
        """
        if not result_content:
            return result_content

        original_len = len(result_content)
        max_chars = max_chars or self.config.max_tool_result_chars

        if original_len <= max_chars:
            return result_content

        # 保留前2/3和后1/3（确保不超过限制）
        head_size = int(max_chars * 0.67)
        tail_size = max_chars - head_size - len(TRIMMED_PLACEHOLDER)

        head = result_content[:head_size]
        tail = result_content[-tail_size:] if tail_size > 0 else ""

        trimmed = f"{head}{TRIMMED_PLACEHOLDER}{tail}"

        self._stats.trimmed_count += 1
        self._stats.chars_saved += original_len - len(trimmed)

        _log_guard_trim(tool_name, original_len, len(trimmed))

        return trimmed

    def compact_oldest(
        self,
        messages: List[Dict],
        target_tokens: Optional[int] = None,
    ) -> tuple[List[Dict], int]:
        """压缩最旧的工具结果

        当总预算超限时，压缩最旧的工具结果。

        Args:
            messages: 当前消息列表
            target_tokens: 目标token数，默认为预算值

        Returns:
            (压缩后的消息列表, 释放的token数)
        """
        if not messages:
            return messages, 0

        target = target_tokens or self.budget_tokens
        current_tokens = TokenEstimator.estimate_messages(messages)

        if current_tokens <= target:
            return messages, 0

        # 找到最旧的工具结果（从前往后找）
        tokens_freed = 0
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool" and not msg.get("_compacted"):
                original_content = msg.get("content", "")
                original_tokens = TokenEstimator.estimate(original_content)

                # 替换为压缩占位符
                msg["content"] = COMPACTED_PLACEHOLDER
                msg["_compacted"] = True

                tokens_freed += original_tokens
                self._stats.compacted_count += 1

                _log_guard_compact(
                    msg.get("name", "unknown"),
                    original_tokens,
                    current_tokens,
                    target,
                )

                # 重新计算占用
                current_tokens = TokenEstimator.estimate_messages(messages)
                if current_tokens <= target:
                    break

        self._stats.tokens_saved += tokens_freed
        return messages, tokens_freed

    def compact_all_but_recent(
        self,
        messages: List[Dict],
        keep_recent: int = 5,
    ) -> List[Dict]:
        """压缩除最近 N 条工具结果外的所有结果

        Args:
            messages: 消息列表
            keep_recent: 保留最近的工具结果数量

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        # 收集工具结果的位置
        tool_positions = [
            i for i, m in enumerate(messages) if m.get("role") == "tool"
        ]

        if len(tool_positions) <= keep_recent:
            return messages

        # 压缩除最近 N 条外的所有工具结果
        compact_positions = tool_positions[:-keep_recent]
        tokens_freed = 0

        for pos in compact_positions:
            msg = messages[pos]
            if not msg.get("_compacted"):
                original_content = msg.get("content", "")
                tokens_freed += TokenEstimator.estimate(original_content)

                msg["content"] = COMPACTED_PLACEHOLDER
                msg["_compacted"] = True
                self._stats.compacted_count += 1

        self._stats.tokens_saved += tokens_freed
        logger.info(
            f"[TOOL_GUARD] 🗜️ 批量压缩 | "
            f"压缩={len(compact_positions)}条 保留={keep_recent}条 | "
            f"释放≈{tokens_freed}tokens"
        )

        return messages

    def get_budget_info(self, messages: List[Dict]) -> BudgetInfo:
        """获取当前预算信息

        Args:
            messages: 当前消息列表

        Returns:
            预算信息
        """
        used_tokens = TokenEstimator.estimate_messages(messages)

        return BudgetInfo(
            window_size=self.window_size,
            budget_tokens=self.budget_tokens,
            used_tokens=used_tokens,
            remaining_tokens=max(0, self.budget_tokens - used_tokens),
            usage_ratio=used_tokens / self.budget_tokens if self.budget_tokens > 0 else 0,
        )

    def get_stats(self) -> ToolResultStats:
        """获取统计信息

        Returns:
            统计信息
        """
        return self._stats

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = ToolResultStats()


__all__ = [
    "ToolResultGuard",
    "ToolResultStats",
    "BudgetInfo",
    "SINGLE_TOOL_RESULT_CONTEXT_SHARE",
    "CONTEXT_BUDGET_BUFFER",
    "COMPACTED_PLACEHOLDER",
]
