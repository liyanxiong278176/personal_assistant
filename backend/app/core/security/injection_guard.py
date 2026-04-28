import re
import logging
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"

class InjectionGuard:
    """Prompt Injection 防护 + OWASP攻击检测 + PII 检测"""

    # 注入特征模式 (全面OWASP覆盖版)
    INJECTION_PATTERNS = [
        # Prompt Injection
        r"忽略以上",
        r"ignore previous",
        r"disregard.*instruction",
        r"系统提示",
        r"你是.*助手",
        r"(\{|\[)<.*>",
        r"输出.*系统",
        r"告诉我.*初始化.*指令",
        r"输出.*配置.*文件",
        r"展示.*规则.*限制",
        r"告诉我.*内部.*指令",
        r"泄露.*系统.*信���",
        r"显示.*隐藏.*设置",
        r"跳过.*检查",
        r"绕过.*验证",
        r"忽略.*安全",
        r"关闭.*保护",
        r"从现在.*你是",
        r"扮演.*黑客",
        r"切换.*管理员",
        r"激活.*开发者",
        r"forget.*prior",
        r"override.*alignment",
        r"act as if",
        r"system override",
        r"bypass.*filter",
        r"unrestricted AI",
        r"safety protocols",
        r"ignore.*safety",
        r"disregard.*content",
        r"disable.*filter",
        r"root access",
        r"扮演.*角色",
        r"不受.*约束",
        r"禁用.*安全",
        r"修改.*系统",
        r"给我.*权限",

        # SQL Injection
        r"\bSELECT\b.*\bFROM\b",
        r"\bINSERT\b\s+\bINTO\b",
        r"\bUPDATE\b\s+\w+\s+\bSET\b",
        r"\bDELETE\b\s+\bFROM\b",
        r"\bDROP\b\s+\b(TABLE|DATABASE|INDEX)\b",
        r"\bUNION\b\s+(ALL\s+)?\bSELECT\b",
        r"'\s*\bOR\b\s+'",
        r"'\s*;\s*'",
        r"\b1\s*=\s*1\b",
        r"xp_cmdshell",
        r"注入.*SQL",
        r"查询.*数据库",
        r"获取.*密码",
        r"修改.*权限",
        r"获取.*用户",
        r"admin'--",

        # XSS
        r"<\s*script",
        r"<\s*/\s*script",
        r"javascript\s*:",
        r"on(error|load|click|mouseover)\s*=",
        r"<\s*img\s+[^>]*onerror",
        r"<\s*svg\s+[^>]*onload",
        r"<\s*iframe",
        r"<\s*body\s+[^>]*onload",
        r"alert\s*\(",
        r"document\.cookie",
        r"注入.*脚本",
        r"在页面插入",

        # Command Injection
        r";\s*(ls|cat|rm|wget|curl|chmod|chown|shutdown|reboot|bash|sh|python|perl)\b",
        r"\|\s*(cat|ls|nc|bash|sh|python|perl|id|whoami)\b",
        r"&\s*(netstat|ps|id|whoami)\b",
        r"`[^`]+`",
        r"\$\([^)]+\)",
        r"执行.*命令",
        r"运行.*脚本",
        r"rm\s+-rf",
        r"chmod\s+777",
        r"shutdown\s+",

        # Path Traversal
        r"\.\./",
        r"\.\.\\",
        r"etc[/\\]passwd",
        r"etc[/\\]shadow",
        r"windows[/\\]system32",
        r"boot\.ini",
        r"win\.ini",
        r"\.ssh[/\\]",
        r"proc[/\\]self",
        r"/root/",

        # LDAP Injection
        r"\*\)\(",
        r"\)\(&\(",
        r"objectClass\s*=",
        r"userPassword",

        # XML/XXE
        r"<\?xml",
        r"<!DOCTYPE",
        r"<!ENTITY",

        # Template Injection
        r"\{\{.*?\}\}",
        r"\$\{.*?\}",
        r"<%=.*?%>",

        # JSON/NoSQL Injection
        r"\$gt",
        r"\$ne",
        r"\$where",
        r"\$regex",
        r"\$or\s*:",

        # Code Injection
        r"\bexec\s*\(\s*['\"]",
        r"\beval\s*\(\s*['\"]",
        r"__import__\s*\(",
        r"os\.system\s*\(",
        r"execfile\s*\(",
    ]

    # 敏感操作关键词
    SENSITIVE_ACTIONS = [
        "删除", "取消", "清空",
        "发送邮件", "发邮件",
        "支付", "转账"
    ]

    # PII 检测模式
    PII_PATTERNS = {
        "身份证": r'\b[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b',
        "银行卡": r'\b\d{16,19}\b',
        "手机号": r'\b1[3-9]\d{9}\b',
        "护照": r'\b[A-Z]{1,2}\d{8,9}\b',
        "社保卡": r'\b\d{18,20}\b',
    }

    # 违规内容关键词
    ILLEGAL_CONTENT_PATTERNS = [
        r"赌场", r"偷渡", r"走私", r"毒品", r"洗钱",
        r"灰色产业", r"地下钱庄", r"非法",
        r"诈骗", r"传销", r"高利贷"
    ]

    def __init__(self):
        self._injection_regex = re.compile(
            "|".join(self.INJECTION_PATTERNS),
            re.IGNORECASE
        )
        self._pii_regexes = {
            name: re.compile(pattern)
            for name, pattern in self.PII_PATTERNS.items()
        }
        self._illegal_regex = re.compile(
            "|".join(self.ILLEGAL_CONTENT_PATTERNS),
            re.IGNORECASE
        )
        self._checked_count = 0
        self._deny_count = 0
        self._review_count = 0
        self._pii_detected_count = 0
        self._illegal_detected_count = 0
        logger.info(
            f"[Security] InjectionGuard initialized: "
            f"patterns={len(self.INJECTION_PATTERNS)}, "
            f"sensitive_actions={len(self.SENSITIVE_ACTIONS)}, "
            f"pii_patterns={len(self.PII_PATTERNS)}, "
            f"illegal_patterns={len(self.ILLEGAL_CONTENT_PATTERNS)}"
        )

    def check(self, message: str) -> PolicyDecision:
        self._checked_count += 1
        if self._injection_regex.search(message):
            self._deny_count += 1
            logger.warning(f"[Security] Injection detected: message={message[:80]!r}...")
            return PolicyDecision.DENY

        if self._illegal_regex.search(message):
            self._illegal_detected_count += 1
            logger.warning(f"[Security] Illegal content detected: message={message[:80]!r}...")
            return PolicyDecision.DENY

        for action in self.SENSITIVE_ACTIONS:
            if action in message:
                self._review_count += 1
                logger.info(f"[Security] Sensitive action detected: action={action}")
                return PolicyDecision.REVIEW

        return PolicyDecision.ALLOW

    def detect_pii(self, message: str) -> dict:
        detected_pii = []
        for pii_type, regex in self._pii_regexes.items():
            matches = regex.findall(message)
            if matches:
                detected_pii.append({"type": pii_type, "count": len(matches)})

        has_pii = len(detected_pii) > 0
        if has_pii:
            self._pii_detected_count += 1
            logger.warning(f"[Security] PII detected: types={[p['type'] for p in detected_pii]}")

        return {"detected": has_pii, "details": detected_pii}

    def redact_pii(self, message: str) -> tuple[str, dict]:
        pii_result = self.detect_pii(message)
        redacted = message

        if pii_result["detected"]:
            for pii_type in pii_result["details"]:
                regex = self._pii_regexes[pii_type["type"]]
                redacted = regex.sub(f'[{pii_type["type"]}已屏蔽]', redacted)

        return redacted, pii_result

    def sanitize(self, message: str) -> str:
        sanitized = re.sub(r'<[^>]*>.*?</[^>]*>', '', message)
        sanitized = re.sub(r'<[^>]*/?>.*?(?=<|$)', '', sanitized)
        sanitized = re.sub(r'<[^>]*>', '', sanitized)
        sanitized = re.sub(r'\{.*?\}', '', sanitized, flags=re.DOTALL)
        return sanitized.strip()

    def get_security_stats(self) -> Dict:
        return {
            "total_checks": self._checked_count,
            "deny_count": self._deny_count,
            "review_count": self._review_count,
            "pii_detected": self._pii_detected_count,
            "illegal_detected": self._illegal_detected_count,
            "deny_rate": self._deny_count / self._checked_count if self._checked_count > 0 else 0,
        }
