"""安全审计日志

记录所有安全相关事件，用于合规审计和问题追踪。

功能:
1. 安全事件记录
2. 敏感操作审计
3. 访问日志追踪
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """安全事件类型"""
    INJECTION_DETECTED = "injection_detected"
    PII_DETECTED = "pii_detected"
    ILLEGAL_CONTENT = "illegal_content"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SESSION_ANOMALY = "session_anomaly"
    TOOL_ABUSE = "tool_abuse"


class SecurityEvent:
    """安全事件"""
    def __init__(
        self,
        event_type: SecurityEventType,
        user_id: str,
        conversation_id: str,
        message_preview: str,
        details: Optional[Dict] = None,
        severity: str = "LOW",
        ip_address: Optional[str] = None,
    ):
        self.event_type = event_type
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.message_preview = message_preview[:200]  # 截断
        self.details = details or {}
        self.severity = severity  # LOW, MEDIUM, HIGH, CRITICAL
        self.ip_address = ip_address
        self.timestamp = datetime.utcnow().isoformat()
        self.event_id = f"{int(time.time() * 1000)}"

    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "message_preview": self.message_preview,
            "details": self.details,
            "severity": self.severity,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class SecurityAuditor:
    """安全审计器

    用法:
        auditor = SecurityAuditor()

        # 记录事件
        auditor.record(
            SecurityEventType.INJECTION_DETECTED,
            user_id="user-123",
            conversation_id="conv-456",
            message_preview=message[:200],
            severity="HIGH"
        )

        # 查询事件
        events = auditor.query(
            event_type=SecurityEventType.INJECTION_DETECTED,
            limit=100
        )
    """

    def __init__(self, max_events: int = 50000):
        self._events: List[SecurityEvent] = []
        self._max_events = max_events
        self._stats: Dict[str, int] = {}

        logger.info(f"[SECURITY_AUDITOR] 初始化完成 | max_events={max_events}")

    def record(
        self,
        event_type: SecurityEventType,
        user_id: str,
        conversation_id: str,
        message_preview: str = "",
        details: Optional[Dict] = None,
        severity: str = "LOW",
        ip_address: Optional[str] = None,
    ) -> SecurityEvent:
        """记录安全事件

        Args:
            event_type: 事件类型
            user_id: 用户ID
            conversation_id: 会话ID
            message_preview: 消息预览
            details: 详细信息
            severity: 严重程度
            ip_address: IP地址

        Returns:
            SecurityEvent: 事件对象
        """
        event = SecurityEvent(
            event_type=event_type,
            user_id=user_id,
            conversation_id=conversation_id,
            message_preview=message_preview,
            details=details,
            severity=severity,
            ip_address=ip_address,
        )

        self._events.append(event)

        # 统计
        key = event_type.value
        self._stats[key] = self._stats.get(key, 0) + 1

        # 清理旧事件
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

        # 日志输出
        severity_symbol = {
            "LOW": "INFO", "MEDIUM": "WARN",
            "HIGH": "ERROR", "CRITICAL": "CRIT"
        }.get(severity, "INFO")

        logger.warning(
            f"[SECURITY_AUDITOR] {severity_symbol} {event_type.value} | "
            f"user={user_id[:8]}... | "
            f"severity={severity}"
        )

        return event

    def query(
        self,
        event_type: Optional[SecurityEventType] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[SecurityEvent]:
        """查询安全事件

        Args:
            event_type: 事件类型过滤
            user_id: 用户ID过滤
            conversation_id: 会话ID过滤
            severity: 严重程度过滤
            since: 起始时间戳
            limit: 返回数量限制

        Returns:
            List[SecurityEvent]: 事件列表
        """
        results = self._events

        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if conversation_id:
            results = [e for e in results if e.conversation_id == conversation_id]
        if severity:
            results = [e for e in results if e.severity == severity]
        if since:
            results = [e for e in results if time.mktime(
                datetime.fromisoformat(e.timestamp).timetuple()
            ) >= since]

        return results[-limit:]

    def get_stats(self) -> Dict:
        """获取审计统计"""
        total = len(self._events)
        by_severity = {}
        for e in self._events:
            by_severity[e.severity] = by_severity.get(e.severity, 0) + 1

        return {
            "total_events": total,
            "by_type": dict(self._stats),
            "by_severity": by_severity,
            "recent_high_severity": sum(
                1 for e in self._events[-1000:]
                if e.severity in ("HIGH", "CRITICAL")
            ),
        }

    def export_events(
        self,
        event_type: Optional[SecurityEventType] = None,
        since: Optional[float] = None,
    ) -> List[Dict]:
        """导出事件（用于合规报告）"""
        events = self.query(event_type=event_type, since=since, limit=100000)
        return [e.to_dict() for e in events]


# 全局审计器实例
_auditor: Optional[SecurityAuditor] = None


def get_security_auditor() -> SecurityAuditor:
    """获取全局安全审计器"""
    global _auditor
    if _auditor is None:
        _auditor = SecurityAuditor()
    return _auditor


__all__ = [
    "SecurityAuditor",
    "SecurityEvent",
    "SecurityEventType",
    "get_security_auditor",
]
