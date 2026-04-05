import pytest
from app.core.subagent.result import AgentResult, AgentType, AGENT_TOOL_PERMISSIONS


def test_agent_result_creation():
    result = AgentResult(
        agent_type=AgentType.WEATHER,
        success=True,
        data={"temp": 25},
        execution_time=1.5
    )
    assert result.agent_type == AgentType.WEATHER
    assert result.success is True


def test_agent_result_from_error():
    error = ValueError("test error")
    result = AgentResult.from_error(AgentType.HOTEL, error)
    assert result.success is False
    assert result.error == "test error"


def test_agent_result_from_success():
    result = AgentResult.from_success(
        AgentType.ROUTE,
        {"distance": "10km"},
        execution_time=2.0
    )
    assert result.success is True
    assert result.data == {"distance": "10km"}


def test_agent_result_to_dict():
    result = AgentResult(
        agent_type=AgentType.BUDGET,
        success=True,
        data={"total": 5000}
    )
    d = result.to_dict()
    assert d["agent_type"] == "budget"
    assert d["success"] is True


def test_agent_tool_permissions():
    assert AgentType.ROUTE in AGENT_TOOL_PERMISSIONS
    assert "search_poi" in AGENT_TOOL_PERMISSIONS[AgentType.ROUTE]
    assert "get_weather" not in AGENT_TOOL_PERMISSIONS[AgentType.ROUTE]
