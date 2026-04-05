import asyncio
import logging
from typing import Dict, Tuple, Optional

from .state import ErrorCategory, RecoveryStrategy

logger = logging.getLogger(__name__)

# 预设分类规则
# 注: 在 Python 3.11+ 中 TimeoutError 是 asyncio.TimeoutError 的别名（同一 class 对象），
# 因此只需一个 key 即可同时匹配两者。RETRY_BACKOFF 更适合超时类错误。
PRESET_RULES = {
    # 临时错误 - 可重试
    TimeoutError: (ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY_BACKOFF, 3),
    ConnectionError: (ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY, 3),

    # 验证错误 - 降级处理
    ValueError: (ErrorCategory.VALIDATION, RecoveryStrategy.DEGRADE, 0),

    # 权限错误 - 立即失败
    PermissionError: (ErrorCategory.PERMISSION, RecoveryStrategy.FAIL, 0),
}


class ErrorClassification:
    """错误分类结果"""

    def __init__(
        self,
        category: ErrorCategory,
        strategy: RecoveryStrategy,
        max_retries: int,
    ):
        self.category = category
        self.strategy = strategy
        self.max_retries = max_retries


class ErrorClassifier:
    """异常分类器

    根据异常类型决定恢复策略和最大重试次数。
    支持预定义规则 + 可配置覆盖。
    """

    def __init__(
        self,
        custom_rules: Optional[Dict[str, Tuple[ErrorCategory, RecoveryStrategy, int]]] = None
    ):
        """初始化分类器

        Args:
            custom_rules: 自定义规则 {异常类型名: (类别, 策略, 最大重试)}
        """
        self._preset_rules = dict(PRESET_RULES)
        self._custom_rules = custom_rules or {}
        logger.info(
            f"[ErrorClassifier] 初始化完成 | 预设规则={len(self._preset_rules)}, "
            f"自定义={len(self._custom_rules)}"
        )

    def classify(self, error: Exception) -> ErrorClassification:
        """分类异常

        Args:
            error: 异常实例

        Returns:
            ErrorClassification: 分类结果
        """
        error_type = type(error)
        error_name = error_type.__name__

        # 检查自定义规则
        if error_name in self._custom_rules:
            category, strategy, max_retries = self._custom_rules[error_name]
            return ErrorClassification(category, strategy, max_retries)

        # 检查预设规则（包括父类）
        for rule_type, (category, strategy, max_retries) in self._preset_rules.items():
            if isinstance(error, rule_type):
                logger.debug(
                    f"[ErrorClassifier] 分类: {error_name} -> {category.value}/{strategy.value}"
                )
                return ErrorClassification(category, strategy, max_retries)

        # 默认：临时错误，重试1次
        logger.warning(
            f"[ErrorClassifier] 未知异常类型: {error_name}, 使用默认分类"
        )
        return ErrorClassification(ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY, 1)
