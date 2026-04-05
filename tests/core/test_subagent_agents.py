import pytest
import asyncio
from app.core.subagent.agents import (
    BaseAgent, RouteAgent, HotelAgent, WeatherAgent, BudgetAgent,
)
from app.core.subagent.session import SubAgentSession
from app.core.subagent.result import AgentType, AGENT_TOOL_PERMISSIONS


@pytest.mark.asyncio
async def test_route_agent():
    session = SubAgentSession(agent_type=AgentType.ROUTE)
    agent = RouteAgent(AgentType.ROUTE, session)

    slots = {"destinations": ["北京", "上海"]}
    result = await agent.execute(slots)

    assert result.success is True
    assert result.data["destinations"] == ["北京", "上海"]


@pytest.mark.asyncio
async def test_hotel_agent():
    session = SubAgentSession(agent_type=AgentType.HOTEL)
    agent = HotelAgent(AgentType.HOTEL, session)

    slots = {"destination": "杭州"}
    result = await agent.execute(slots)

    assert result.success is True
    assert "hotels" in result.data


@pytest.mark.asyncio
async def test_weather_agent():
    session = SubAgentSession(agent_type=AgentType.WEATHER)
    agent = WeatherAgent(AgentType.WEATHER, session)

    slots = {"destination": "成都"}
    result = await agent.execute(slots)

    assert result.success is True
    assert "current" in result.data


@pytest.mark.asyncio
async def test_budget_agent():
    session = SubAgentSession(agent_type=AgentType.BUDGET)
    agent = BudgetAgent(AgentType.BUDGET, session)

    slots = {"days": 5, "budget": "comfortable"}
    result = await agent.execute(slots)

    assert result.success is True
    assert result.data["total_estimate"] == 3000  # 600 * 5


def test_agent_tool_permissions():
    assert AgentType.ROUTE in AGENT_TOOL_PERMISSIONS
    assert "search_poi" in AGENT_TOOL_PERMISSIONS[AgentType.ROUTE]
    assert "get_weather" not in AGENT_TOOL_PERMISSIONS[AgentType.ROUTE]


@pytest.mark.asyncio
async def test_agent_timeout():
    class SlowAgent(BaseAgent):
        async def _execute_impl(self, slots):
            await asyncio.sleep(10)

    session = SubAgentSession(agent_type=AgentType.ROUTE, timeout=1)
    agent = SlowAgent(AgentType.ROUTE, session)

    result = await agent.execute({})

    assert result.success is False
    assert "超时" in result.error
