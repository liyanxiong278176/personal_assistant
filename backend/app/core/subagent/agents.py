"""Agent实现 - 基类和具体Agent"""

import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from .session import SubAgentSession, SubAgentStatus
from .result import AgentResult, AgentType

logger = logging.getLogger(__name__)
MAX_RETRY_ATTEMPTS = 2
RETRYABLE_ERRORS = (asyncio.TimeoutError, TimeoutError)


class BaseAgent:
    """Agent基类

    所有子Agent继承此类，实现统一的执行流程：
    - 超时控制
    - 重试机制
    - 状态管理
    """
    def __init__(
        self,
        agent_type: AgentType,
        session: SubAgentSession,
        llm_client=None
    ):
        self.agent_type = agent_type
        self.session = session
        self.llm_client = llm_client

    async def execute(self, slots: Dict[str, Any]) -> AgentResult:
        """执行Agent任务（含超时和重试）"""
        self.session.mark_started()
        try:
            result = await asyncio.wait_for(
                self._execute_with_retry(slots),
                timeout=self.session.timeout
            )
            self.session.mark_completed(result)
            return result
        except asyncio.TimeoutError:
            self.session.mark_timeout()
            return AgentResult.from_error(
                self.agent_type,
                TimeoutError(f"执行超时: {self.session.timeout}秒")
            )
        except Exception as e:
            self.session.mark_failed(e)
            return AgentResult.from_error(self.agent_type, e)

    async def _execute_with_retry(self, slots: Dict[str, Any]) -> AgentResult:
        """带重试的执行"""
        retry_count = 0
        last_error = None

        while retry_count <= MAX_RETRY_ATTEMPTS:
            try:
                start_time = asyncio.get_event_loop().time()
                data = await self._execute_impl(slots)
                return AgentResult.from_success(
                    self.agent_type,
                    data,
                    execution_time=asyncio.get_event_loop().time() - start_time,
                    retried=retry_count
                )
            except RETRYABLE_ERRORS as e:
                retry_count += 1
                last_error = e
                self.session.retry_count = retry_count

                if retry_count <= MAX_RETRY_ATTEMPTS:
                    delay = 2 ** retry_count
                    logger.info(
                        f"[{self.agent_type.value}] 重试 {retry_count}/{MAX_RETRY_ATTEMPTS}"
                    )
                    await asyncio.sleep(delay)

        return AgentResult.from_error(
            self.agent_type,
            last_error or Exception("重试耗尽")
        )

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """子类实现具体逻辑"""
        raise NotImplementedError(f"{self.__class__.__name__}._execute_impl")


class RouteAgent(BaseAgent):
    """路线规划Agent"""

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """调用路线规划工具

        TODO: 集成高德地图API
        """
        destinations = slots.get("destinations", [])

        return {
            "destinations": destinations,
            "routes": [
                {"from": d, "to": d, "distance": "0km"}
                for d in destinations
            ],
            "total_distance": f"{len(destinations) * 10}km",
            "estimated_time": f"{len(destinations) * 2}小时"
        }


class HotelAgent(BaseAgent):
    """酒店查询Agent"""

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """查询酒店信息

        TODO: 集成酒店API
        """
        destination = slots.get("destination", "未知")

        return {
            "destination": destination,
            "hotels": [
                {"name": f"{destination}大酒店", "price": 300, "rating": 4.5},
                {"name": f"{destination}宾馆", "price": 200, "rating": 4.0},
            ],
            "price_range": "200-500元/晚"
        }


class WeatherAgent(BaseAgent):
    """天气查询Agent"""

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """查询天气信息

        TODO: 集成天气API
        """
        destination = slots.get("destination", "未知")

        return {
            "destination": destination,
            "current": {"temp": 25, "condition": "晴"},
            "forecast": [
                {"date": "明天", "temp": "20-28°C", "condition": "多云"},
                {"date": "后天", "temp": "18-25°C", "condition": "小雨"},
            ]
        }


class BudgetAgent(BaseAgent):
    """预算计算Agent"""

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """计算旅行预算

        基于其他Agent的结果进行计算
        """
        days = slots.get("days", 3)
        budget_level = slots.get("budget", "comfortable")

        daily_cost = {"economic": 300, "comfortable": 600, "luxury": 1500}
        total = daily_cost.get(budget_level, 600) * days

        return {
            "days": days,
            "budget_level": budget_level,
            "daily_estimate": daily_cost.get(budget_level, 600),
            "total_estimate": total,
            "breakdown": {
                "accommodation": total * 0.4,
                "food": total * 0.3,
                "transport": total * 0.2,
                "tickets": total * 0.1,
            }
        }
