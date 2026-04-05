"""子Agent隔离会话管理"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4

from .result import AgentType, AGENT_TOOL_PERMISSIONS


class SubAgentStatus(str, Enum):
    """子Agent状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class SubAgentSession:
    """子Agent隔离会话

    每个子Agent拥有独立的：
    - 会话ID和父子关系
    - 上下文窗口（独立token配额）
    - 工具权限（白名单）
    - 执行状态和时间戳
    """
    session_id: UUID = field(default_factory=uuid4)
    parent_session_id: Optional[UUID] = None
    agent_type: AgentType = AgentType.ROUTE

    # 嵌套控制
    spawn_depth: int = 0
    max_spawn_depth: int = 2

    # 上下文管理
    context_window_size: int = 32000
    context_messages: List[Dict[str, str]] = field(default_factory=list)
    token_count: int = 0

    # 工具权限
    allowed_tools: List[str] = field(default_factory=list)

    # 执行状态
    status: SubAgentStatus = SubAgentStatus.PENDING
    result: Optional[Any] = None
    error: Optional[Exception] = None

    # 超时控制
    timeout: int = 30
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0

    def __post_init__(self):
        if not self.allowed_tools:
            self.allowed_tools = AGENT_TOOL_PERMISSIONS.get(self.agent_type, [])

    @property
    def execution_time(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_running(self) -> bool:
        return self.status == SubAgentStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        return self.status in (SubAgentStatus.COMPLETED, SubAgentStatus.FAILED,
                               SubAgentStatus.TIMEOUT, SubAgentStatus.CANCELLED)

    def can_spawn(self, depth: int = 1) -> bool:
        new_depth = self.spawn_depth + depth
        return new_depth <= self.max_spawn_depth

    def mark_started(self) -> None:
        self.status = SubAgentStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, result: Any) -> None:
        self.status = SubAgentStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def mark_failed(self, error: Exception) -> None:
        self.status = SubAgentStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    def mark_timeout(self) -> None:
        self.status = SubAgentStatus.TIMEOUT
        self.completed_at = datetime.now()

    def add_context_message(self, role: str, content: str) -> None:
        self.context_messages.append({"role": role, "content": content})

    def get_context_summary(self) -> Dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "agent_type": self.agent_type.value,
            "status": self.status.value,
            "message_count": len(self.context_messages),
            "token_count": self.token_count,
            "execution_time": self.execution_time,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "parent_session_id": str(self.parent_session_id) if self.parent_session_id else None,
            "agent_type": self.agent_type.value,
            "spawn_depth": self.spawn_depth,
            "status": self.status.value,
            "execution_time": self.execution_time,
            "retry_count": self.retry_count,
        }
