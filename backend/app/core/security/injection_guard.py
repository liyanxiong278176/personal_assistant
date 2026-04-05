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

    def check(self, message: str) -> PolicyDecision:
        """检查消息是否包含注入攻击

        Args:
            message: 用户消息

        Returns:
            策略决策
        """
        # 1. 检测注入攻击
        if self._injection_regex.search(message):
            logger.warning(f"[Security] Injection detected: {message[:50]}...")
            return PolicyDecision.DENY

        # 2. 检测敏感操作
        for action in self.SENSITIVE_ACTIONS:
            if action in message:
                logger.info(f"[Security] Sensitive action detected: {action}")
                return PolicyDecision.REVIEW

        # 3. 正常消息
        return PolicyDecision.ALLOW

    def sanitize(self, message: str) -> str:
        """清理消息中的潜在注入内容"""
        # 移除HTML标签及其内容
        sanitized = re.sub(r'<[^>]*>.*?</[^>]*>', '', message)
        # 移除自闭合标签及其内容
        sanitized = re.sub(r'<[^>]*/?>.*?(?=<|$)', '', sanitized)
        # 移除独立的HTML标签
        sanitized = re.sub(r'<[^>]*>', '', sanitized)
        # 移除JSON注入尝试
        sanitized = re.sub(r'\{.*?\}', '', sanitized, flags=re.DOTALL)
        return sanitized.strip()
