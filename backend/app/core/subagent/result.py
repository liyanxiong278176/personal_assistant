"""Agent统一返回格式和工具权限映射"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from enum import Enum


class AgentType(str, Enum):
    """Agent类型"""
    ROUTE = "route"
    HOTEL = "hotel"
    WEATHER = "weather"
    BUDGET = "budget"


# 工具权限映射 - 放在这里避免循环导入
AGENT_TOOL_PERMISSIONS = {
    AgentType.ROUTE: ["search_poi", "get_route", "geocoding"],
    AgentType.HOTEL: ["search_hotel", "get_hotel_detail"],
    AgentType.WEATHER: ["get_weather", "get_forecast"],
    AgentType.BUDGET: ["calculate_budget", "get_price_estimate"],
}


@dataclass
class AgentResult:
    """Agent执行结果统一格式"""
    agent_type: AgentType
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    token_used: int = 0
    retried: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_type": self.agent_type.value,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time": self.execution_time,
            "token_used": self.token_used,
            "retried": self.retried,
        }

    @classmethod
    def from_error(cls, agent_type: AgentType, error: Exception) -> "AgentResult":
        return cls(agent_type=agent_type, success=False, error=str(error))

    @classmethod
    def from_success(cls, agent_type: AgentType, data: Dict[str, Any], **kwargs) -> "AgentResult":
        return cls(agent_type=agent_type, success=True, data=data, **kwargs)
