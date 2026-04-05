import asyncio
import logging
from typing import Dict, Tuple, Optional

from .state import ErrorCategory, RecoveryStrategy
from .error_classifier import ErrorClassifier, ErrorClassification
from .structured_logger import SessionPhase, log_event, LogLevel

logger = logging.getLogger(__name__)


class RetryPolicy:
    """重试策略配置"""
    def __init__(
        self,
        max_total_retries: int = 5,
        backoff_base: float = 1.0,
        backoff_max: float = 4.0
    ):
        self.max_total_retries = max_total_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max


class RetryManager:
    """重试管理器

    跟踪重试次数，根据错误分类决定是否继续重试。
    """

    def __init__(
        self,
        error_classifier: ErrorClassifier,
        policy: Optional[RetryPolicy] = None
    ):
        """初始化重试管理器

        Args:
            error_classifier: 异常分类器
            policy: 重试策略配置
        """
        self._classifier = error_classifier
        self._policy = policy or RetryPolicy()
        self._retry_counts: Dict[str, int] = {}  # {conversation_id: count}
        self._last_errors: Dict[str, Exception] = {}  # {conversation_id: last_error}

    def should_retry(self, conversation_id: str, error: Exception) -> Tuple[bool, int]:
        """判断是否应该重试

        Args:
            conversation_id: 会话ID
            error: 发生的异常

        Returns:
            (should_retry, retry_count): (是否重试, 当前重试次数)
        """
        classification = self._classifier.classify(error)
        current_count = self._retry_counts.get(conversation_id, 0)

        # 记录错误
        self._last_errors[conversation_id] = error

        # 检查策略是否允许重试
        if classification.strategy == RecoveryStrategy.FAIL:
            logger.info(f"[RetryManager] 策略=FAIL, 不重试")
            log_event(
                LogLevel.INFO,
                SessionPhase.RETRY,
                "重试策略=FAIL, 不重试",
                conversation_id=conversation_id,
                strategy=classification.strategy.value,
                should_retry=False
            )
            return False, current_count

        if classification.strategy == RecoveryStrategy.SKIP:
            logger.info(f"[RetryManager] 策略=SKIP, 跳过重试")
            log_event(
                LogLevel.INFO,
                SessionPhase.RETRY,
                "重试策略=SKIP, 跳过重试",
                conversation_id=conversation_id,
                strategy=classification.strategy.value,
                should_retry=False
            )
            return False, current_count

        # 检查是否超过最大重试次数
        max_allowed = min(classification.max_retries, self._policy.max_total_retries)
        if current_count >= max_allowed:
            logger.warning(f"[RetryManager] 达到最大重试次数: {current_count} >= {max_allowed}")
            log_event(
                LogLevel.WARNING,
                SessionPhase.RETRY,
                "达到最大重试次数",
                conversation_id=conversation_id,
                current_count=current_count,
                max_allowed=max_allowed,
                should_retry=False
            )
            return False, current_count

        # 可以重试
        self._retry_counts[conversation_id] = current_count + 1
        logger.info(f"[RetryManager] 允许重试: {current_count + 1}/{max_allowed}")
        log_event(
            LogLevel.INFO,
            SessionPhase.RETRY,
            "允许重试",
            conversation_id=conversation_id,
            retry_count=current_count + 1,
            max_allowed=max_allowed,
            strategy=classification.strategy.value,
            should_retry=True
        )
        return True, current_count + 1

    async def apply_backoff(self, retry_count: int) -> None:
        """应用退避延迟

        Args:
            retry_count: 当前重试次数
        """
        if retry_count <= 0:
            return

        delay = min(
            self._policy.backoff_base * (2 ** (retry_count - 1)),
            self._policy.backoff_max
        )
        logger.info(f"[RetryManager] 退避延迟: {delay}s")
        log_event(
            LogLevel.INFO,
            SessionPhase.RETRY,
            f"应用退避延迟: {delay}s",
            retry_count=retry_count,
            delay_seconds=delay
        )
        await asyncio.sleep(delay)

    def reset(self, conversation_id: str) -> None:
        """重置会话的重试状态

        Args:
            conversation_id: 会话ID
        """
        self._retry_counts.pop(conversation_id, None)
        self._last_errors.pop(conversation_id, None)
        logger.debug(f"[RetryManager] 重置重试状态: conv={conversation_id}")
        log_event(
            LogLevel.INFO,
            SessionPhase.RETRY,
            f"重置重试状态",
            conversation_id=conversation_id
        )

    def get_retry_count(self, conversation_id: str) -> int:
        """获取当前重试次数

        Args:
            conversation_id: 会话ID

        Returns:
            当前重试次数
        """
        return self._retry_counts.get(conversation_id, 0)

    def get_last_error(self, conversation_id: str) -> Optional[Exception]:
        """获取最后一次错误

        Args:
            conversation_id: 会话ID

        Returns:
            最后一次发生的异常
        """
        return self._last_errors.get(conversation_id)
