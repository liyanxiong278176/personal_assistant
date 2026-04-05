"""SubAgent会话状态管理 - 占位模块"""

from enum import Enum


class SubAgentStatus(str, Enum):
    """SubAgent执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubAgentSession:
    """SubAgent会话"""
    def __init__(self, session_id: str, agent_type: str):
        self.session_id = session_id
        self.agent_type = agent_type
        self.status = SubAgentStatus.PENDING
