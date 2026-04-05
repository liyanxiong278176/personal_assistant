from enum import Enum
from typing import Optional, Tuple
from pydantic import BaseModel
from uuid import UUID


class ErrorCategory(Enum):
    """错误类别"""
    TRANSIENT = "transient"      # 临时错误（网络、超时）
    VALIDATION = "validation"    # 验证错误（参数、格式）
    PERMISSION = "permission"    # 权限错误（API密钥、访问）
    FATAL = "fatal"             # 致命错误（不可恢复）


class RecoveryStrategy(Enum):
    """恢复策略"""
    RETRY = "retry"                      # 立即重试
    RETRY_BACKOFF = "retry_backoff"      # 退避重试
    DEGRADE = "degrade"                  # 降级响应
    SKIP = "skip"                        # 跳过该步骤
    FAIL = "fail"                        # 立即失败


class SessionState(BaseModel):
    """会话状态"""
    session_id: UUID
    user_id: UUID
    conversation_id: UUID
    context_window_size: int = 128000
    soft_trim_ratio: float = 0.3
    hard_clear_ratio: float = 0.5
    max_spawn_depth: int = 2
    max_concurrent: int = 8
    max_children: int = 5
