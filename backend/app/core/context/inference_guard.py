"""InferenceGuard - 推理中token守卫

在LLM流式输出过程中监控token使用，防止超限。
"""

import logging
from dataclasses import dataclass
from enum import Enum

from ..session.structured_logger import log_event, LogLevel, SessionPhase

logger = logging.getLogger(__name__)


class OverlimitStrategy(Enum):
    """超限策略"""
    TRUNCATE = "truncate"  # 截断返回
    REJECT = "reject"      # 拒绝生成


@dataclass
class TokenStats:
    """Token统计"""
    current_response: int = 0  # 当前响应已用token
    total_budget_used: int = 0  # 总预算已用token


class InferenceGuard:
    """推理中token守卫

    在LLM流式输出过程中监控token使用，防止超限。
    支持两种超限策略：截断（返回已生成内容）或拒绝（不返回任何内容）。
    """

    def __init__(
        self,
        max_tokens_per_response: int = 4000,
        max_total_budget: int = 16000,
        warning_threshold: float = 0.8,
        overlimit_strategy: OverlimitStrategy = OverlimitStrategy.TRUNCATE,
    ):
        self.max_tokens_per_response = max_tokens_per_response
        self.max_total_budget = max_total_budget
        self.warning_threshold = warning_threshold
        self.overlimit_strategy = overlimit_strategy
        self._current_tokens = 0
        self._total_budget_used = 0
        self._warning_sent = False

    def check_before_yield(self, chunk: str) -> tuple[bool, str | None]:
        """在yield每个chunk前检查

        Returns:
            (should_continue, warning_message)
        """
        chunk_tokens = self._estimate_tokens(chunk)
        self._current_tokens += chunk_tokens
        self._total_budget_used += chunk_tokens

        # 检查总预算
        if self._total_budget_used >= self.max_total_budget:
            log_event(
                LogLevel.WARNING,
                SessionPhase.RETRY,
                "总token预算超限",
                current_tokens=self._current_tokens,
                total_budget=self._total_budget_used,
                max_budget=self.max_total_budget
            )
            logger.warning("[InferenceGuard] 总token预算超限")
            return False, self._get_friendly_message("total_budget_exceeded")

        # 检查单次响应限制
        if self._current_tokens >= self.max_tokens_per_response:
            if self.overlimit_strategy == OverlimitStrategy.REJECT:
                log_event(
                    LogLevel.WARNING,
                    SessionPhase.RETRY,
                    "单次响应token超限-REJECT策略",
                    current_tokens=self._current_tokens,
                    max_tokens=self.max_tokens_per_response,
                    strategy="reject"
                )
                return False, self._get_friendly_message("per_response_limit")
            else:  # TRUNCATE
                log_event(
                    LogLevel.WARNING,
                    SessionPhase.RETRY,
                    "单次响应token超限-TRUNCATE策略",
                    current_tokens=self._current_tokens,
                    max_tokens=self.max_tokens_per_response,
                    strategy="truncate"
                )
                return False, self._get_friendly_message("truncated")

        # 检查警告阈值
        if not self._warning_sent:
            if self._current_tokens >= self.max_tokens_per_response * self.warning_threshold:
                self._warning_sent = True
                log_event(
                    LogLevel.INFO,
                    SessionPhase.RETRY,
                    "达到警告阈值",
                    current_tokens=self._current_tokens,
                    threshold=self.max_tokens_per_response * self.warning_threshold
                )
                return True, self._get_friendly_message("warning")

        return True, None

    def reset_response_counter(self) -> None:
        """重置单次响应计数器"""
        self._current_tokens = 0
        self._warning_sent = False

    def reset_all(self) -> None:
        """重置所有计数器（包括总预算）"""
        self._current_tokens = 0
        self._total_budget_used = 0
        self._warning_sent = False

    def _estimate_tokens(self, text: str) -> int:
        """估算文本的token数 - 简化版使用len(text)"""
        return len(text)

    def _get_friendly_message(self, reason: str) -> str:
        """获取停止原因的友好提示"""
        messages = {
            "total_budget_exceeded": "（回复较长，已为您精简展示）",
            "per_response_limit": "（单次回复长度限制，已为您精简展示）",
            "truncated": "（回复较长，已为您精简展示）",
            "warning": None
        }
        return messages.get(reason)

    @property
    def current_tokens(self) -> int:
        return self._current_tokens

    @property
    def total_budget_used(self) -> int:
        return self._total_budget_used


__all__ = ["InferenceGuard", "OverlimitStrategy"]
