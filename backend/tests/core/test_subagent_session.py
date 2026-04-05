import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from app.core.subagent.session import SubAgentSession, SubAgentStatus
from app.core.subagent.result import AgentType


def test_session_creation():
    session = SubAgentSession(
        agent_type=AgentType.WEATHER,
        parent_session_id=uuid4()
    )
    assert session.agent_type == AgentType.WEATHER
    assert session.status == SubAgentStatus.PENDING
    assert session.session_id != session.parent_session_id


def test_session_lifecycle():
    session = SubAgentSession(agent_type=AgentType.ROUTE)

    assert session.status == SubAgentStatus.PENDING
    assert not session.is_running
    assert not session.is_completed

    session.mark_started()
    assert session.status == SubAgentStatus.RUNNING
    assert session.is_running
    assert session.started_at is not None

    result = {"routes": ["A->B"]}
    session.mark_completed(result)
    assert session.status == SubAgentStatus.COMPLETED
    assert session.is_completed
    assert session.result == result
    assert session.execution_time is not None


def test_session_failure():
    session = SubAgentSession(agent_type=AgentType.HOTEL)
    session.mark_started()

    error = ValueError("API error")
    session.mark_failed(error)

    assert session.status == SubAgentStatus.FAILED
    assert session.error == error


def test_session_timeout():
    session = SubAgentSession(agent_type=AgentType.BUDGET)
    session.mark_timeout()

    assert session.status == SubAgentStatus.TIMEOUT


def test_can_spawn():
    session = SubAgentSession(
        agent_type=AgentType.ROUTE,
        spawn_depth=0,
        max_spawn_depth=2
    )

    assert session.can_spawn(1) is True
    assert session.can_spawn(2) is True
    assert session.can_spawn(3) is False


def test_context_messages():
    session = SubAgentSession(agent_type=AgentType.WEATHER)

    session.add_context_message("user", "查天气")
    session.add_context_message("assistant", "晴天")

    assert len(session.context_messages) == 2
    assert session.context_messages[0]["role"] == "user"


def test_get_context_summary():
    session = SubAgentSession(agent_type=AgentType.HOTEL)
    summary = session.get_context_summary()

    assert summary["agent_type"] == "hotel"
    assert summary["status"] == "pending"
    assert "session_id" in summary


def test_execution_time():
    session = SubAgentSession(agent_type=AgentType.WEATHER)

    # 初始状态
    assert session.execution_time is None

    # 未完成时
    session.mark_started()
    assert session.execution_time is None  # 还没有完成时间

    # 完成后
    session.mark_completed({})
    assert session.execution_time is not None
    assert isinstance(session.execution_time, float)
