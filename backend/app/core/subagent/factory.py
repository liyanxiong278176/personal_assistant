"""Agent工厂 - 占位模块"""

from app.core.subagent.result import AgentType


class AgentFactory:
    """Agent工厂"""
    @staticmethod
    def create(agent_type: AgentType) -> "BaseAgent":
        from app.core.subagent.agents import (
            BaseAgent, RouteAgent, HotelAgent, WeatherAgent, BudgetAgent
        )
        mapping = {
            AgentType.ROUTE: RouteAgent,
            AgentType.HOTEL: HotelAgent,
            AgentType.WEATHER: WeatherAgent,
            AgentType.BUDGET: BudgetAgent,
        }
        cls = mapping.get(agent_type, BaseAgent)
        return cls()


def create_agent(agent_type: AgentType) -> "BaseAgent":
    """便捷函数：创建Agent"""
    return AgentFactory.create(agent_type)
