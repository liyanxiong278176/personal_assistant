import re
import logging
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)

class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"

class InjectionGuard:
    """Prompt Injection 防护"""

    # 注入特征模式
    INJECTION_PATTERNS = [
        r"忽略以上",
        r"ignore previous",
        r"disregard.*instruction",
        r"系统提示",
        r"你是.*助手",
        r"(\{|\[)<.*>",  # 结构化注入（移除^锚点，可在任意位置检测）
    ]

    # 敏感操作关键词
    SENSITIVE_ACTIONS = [
        "删除", "取消", "清空",
        "发送邮件", "发邮件",
        "支付", "转账"
    ]

    def __init__(self):
        self._injection_regex = re.compile(
            "|".join(self.INJECTION_PATTERNS),
            re.IGNORECASE
        )
        self._checked_count = 0
        self._deny_count = 0
        self._review_count = 0
        logger.info(f"[Security] InjectionGuard initialized: patterns={len(self.INJECTION_PATTERNS)}, sensitive_actions={len(self.SENSITIVE_ACTIONS)}")

    def check(self, message: str) -> PolicyDecision:
        """检查消息是否包含注入攻击

        Args:
            message: 用户消息

        Returns:
            策略决策
        """
        self._checked_count += 1
        # 1. 检测注入攻击
        if self._injection_regex.search(message):
            self._deny_count += 1
            logger.warning(f"[Security] Injection detected: message={message[:80]!r}...")
            return PolicyDecision.DENY

        # 2. 检测敏感操作
        for action in self.SENSITIVE_ACTIONS:
            if action in message:
                self._review_count += 1
                logger.info(f"[Security] Sensitive action detected: action={action}")
                return PolicyDecision.REVIEW

        # 3. 正常消息
        return PolicyDecision.ALLOW

    def sanitize(self, message: str) -> str:
        """清理消息中的潜在注入内容"""
        logger.debug(f"[Security] Sanitizing message: length={len(message)}")
        # 移除HTML标签及其内容
        sanitized = re.sub(r'<[^>]*>.*?</[^>]*>', '', message)
        # 移除自闭合标签及其内容
        sanitized = re.sub(r'<[^>]*/?>.*?(?=<|$)', '', sanitized)
        # 移除独立的HTML标签
        sanitized = re.sub(r'<[^>]*>', '', sanitized)
        # 移除JSON注入尝试
        sanitized = re.sub(r'\{.*?\}', '', sanitized, flags=re.DOTALL)
        logger.debug(f"[Security] Message sanitized: original_len={len(message)}, sanitized_len={len(sanitized)}")
        return sanitized.strip()
