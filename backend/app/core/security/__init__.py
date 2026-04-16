"""安全模块

整合内容:
- InjectionGuard: 原版注入防护
- InjectionGuardEnhanced: 增强版，整合了 SecurityFilter 的优点
  - 特殊令牌转义功能
  - 区分大小写/不区分大小写的注入模式
  - 结构化安全事件日志
"""

from .injection_guard import InjectionGuard, PolicyDecision
from .injection_guard_enhanced import InjectionGuardEnhanced, SecurityEventType

__all__ = [
    "InjectionGuard",
    "InjectionGuardEnhanced",
    "PolicyDecision",
    "SecurityEventType",
]
