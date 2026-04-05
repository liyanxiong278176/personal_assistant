"""具体Agent实现 - 占位模块"""

from app.core.subagent.result import AgentType


class BaseAgent:
    """Base Agent"""
    def __init__(self, agent_type: AgentType):
        self.agent_type = agent_type


class RouteAgent(BaseAgent):
    """路线规划Agent"""
    def __init__(self):
        super().__init__(AgentType.ROUTE)


class HotelAgent(BaseAgent):
    """酒店推荐Agent"""
    def __init__(self):
        super().__init__(AgentType.HOTEL)


class WeatherAgent(BaseAgent):
    """天气查询Agent"""
    def __init__(self):
        super().__init__(AgentType.WEATHER)


class BudgetAgent(BaseAgent):
    """预算计算Agent"""
    def __init__(self):
        super().__init__(AgentType.BUDGET)
