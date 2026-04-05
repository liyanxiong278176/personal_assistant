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

    所有子Agent继承��类，实现统一的执行流程：
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

        logger.info(
            f"[AGENT:{self.agent_type.value.upper()}] 🚀 开始执行 | "
            f"session={self.session.session_id} | "
            f"slots={list(slots.keys())} | "
            f"timeout={self.session.timeout}s"
        )

        try:
            result = await asyncio.wait_for(
                self._execute_with_retry(slots),
                timeout=self.session.timeout
            )
            self.session.mark_completed(result)

            logger.info(
                f"[AGENT:{self.agent_type.value.upper()}] ✅ 执行成功 | "
                f"session={self.session.session_id} | "
                f"耗时={result.execution_time:.3f}s | "
                f"重试={result.retried}次"
            )
            return result
        except asyncio.TimeoutError:
            self.session.mark_timeout()
            logger.error(
                f"[AGENT:{self.agent_type.value.upper()}] ⏱️ 执行超时 | "
                f"session={self.session.session_id} | "
                f"timeout={self.session.timeout}s"
            )
            return AgentResult.from_error(
                self.agent_type,
                TimeoutError(f"执行超时: {self.session.timeout}秒")
            )
        except Exception as e:
            self.session.mark_failed(e)
            logger.error(
                f"[AGENT:{self.agent_type.value.upper()}] ❌ 执行失败 | "
                f"session={self.session.session_id} | "
                f"error={str(e)}"
            )
            return AgentResult.from_error(self.agent_type, e)

    async def _execute_with_retry(self, slots: Dict[str, Any]) -> AgentResult:
        """带重试的执行"""
        retry_count = 0
        last_error = None

        while retry_count <= MAX_RETRY_ATTEMPTS:
            try:
                start_time = asyncio.get_event_loop().time()
                data = await self._execute_impl(slots)
                elapsed = asyncio.get_event_loop().time() - start_time

                logger.debug(
                    f"[AGENT:{self.agent_type.value.upper()}] 📤 _execute_impl完成 | "
                    f"耗时={elapsed:.3f}s"
                )

                return AgentResult.from_success(
                    self.agent_type,
                    data,
                    execution_time=elapsed,
                    retried=retry_count
                )
            except RETRYABLE_ERRORS as e:
                retry_count += 1
                last_error = e
                self.session.retry_count = retry_count

                if retry_count <= MAX_RETRY_ATTEMPTS:
                    delay = 2 ** retry_count
                    logger.warning(
                        f"[AGENT:{self.agent_type.value.upper()}] 🔄 重试 | "
                        f"次数={retry_count}/{MAX_RETRY_ATTEMPTS} | "
                        f"延迟={delay}s | "
                        f"原因={str(e)}"
                    )
                    await asyncio.sleep(delay)

        logger.error(
            f"[AGENT:{self.agent_type.value.upper()}] ❌ 重试耗尽 | "
            f"最后错误={str(last_error)}"
        )

        return AgentResult.from_error(
            self.agent_type,
            last_error or Exception("重试耗尽")
        )

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """子类实现具体逻辑"""
        raise NotImplementedError(f"{self.__class__.__name__}._execute_impl")


class RouteAgent(BaseAgent):
    """路线规划Agent

    职责：
    - 根据目的地规划旅行路线
    - 计算距离和预估时间
    """

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """调用路线规划工具

        TODO: 集成高德地图API
        """
        destinations = slots.get("destinations", slots.get("destination", []))
        if isinstance(destinations, str):
            destinations = [destinations]

        logger.info(
            f"[ROUTE] 📍 规划路线 | "
            f"目的地={destinations} | "
            f"数量={len(destinations) if isinstance(destinations, list) else 1}"
        )

        result = {
            "destinations": destinations,
            "routes": [
                {"from": d, "to": d, "distance": "10km"}
                for d in (destinations if isinstance(destinations, list) else [destinations])
            ],
            "total_distance": f"{len(destinations) * 10 if isinstance(destinations, list) else 10}km",
            "estimated_time": f"{len(destinations) * 2 if isinstance(destinations, list) else 2}小时"
        }

        logger.debug(f"[ROUTE] 📤 路线规划完成 | 路线数={len(result['routes'])}")
        return result


class HotelAgent(BaseAgent):
    """酒店查询Agent

    职责：
    - 查询目的地酒店信息
    - 返回价格和评分
    """

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """查询酒店信息

        TODO: 集成酒店API
        """
        destination = slots.get("destination", slots.get("destinations", ["未知"])[0] if slots.get("destinations") else "未知")

        logger.info(
            f"[HOTEL] 🏨 查询酒店 | "
            f"目的地={destination}"
        )

        result = {
            "destination": destination,
            "hotels": [
                {"name": f"{destination}大酒店", "price": 300, "rating": 4.5},
                {"name": f"{destination}宾馆", "price": 200, "rating": 4.0},
            ],
            "price_range": "200-500元/晚"
        }

        logger.debug(f"[HOTEL] 📤 酒店查询完成 | 酒店数={len(result['hotels'])}")
        return result


class WeatherAgent(BaseAgent):
    """天气查询Agent

    职责：
    - 查询目的地天气信息
    - 返回当前天气和预报
    """

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """查询天气信息

        TODO: 集成天气API
        """
        destination = slots.get("destination", slots.get("destinations", ["未知"])[0] if slots.get("destinations") else "未知")

        logger.info(
            f"[WEATHER] 🌤️ 查询天气 | "
            f"目的地={destination}"
        )

        result = {
            "destination": destination,
            "current": {"temp": 25, "condition": "晴"},
            "forecast": [
                {"date": "明天", "temp": "20-28°C", "condition": "多云"},
                {"date": "后天", "temp": "18-25°C", "condition": "小雨"},
            ]
        }

        logger.debug(f"[WEATHER] 📤 天气查询完成 | 预报天数={len(result['forecast'])}")
        return result


class BudgetAgent(BaseAgent):
    """预算计算Agent

    职责：
    - 计算旅行总预算
    - 分解各项费用
    """

    async def _execute_impl(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """计算旅行预算

        基于其他Agent的结果进行计算
        """
        days = slots.get("days", 3)
        budget_level = slots.get("budget", "comfortable")

        logger.info(
            f"[BUDGET] 💰 计算预算 | "
            f"天数={days} | "
            f"档次={budget_level}"
        )

        daily_cost = {"economic": 300, "comfortable": 600, "luxury": 1500}
        total = daily_cost.get(budget_level, 600) * days

        result = {
            "days": days,
            "budget_level": budget_level,
            "daily_estimate": daily_cost.get(budget_level, 600),
            "total_estimate": total,
            "breakdown": {
                "accommodation": int(total * 0.4),
                "food": int(total * 0.3),
                "transport": int(total * 0.2),
                "tickets": int(total * 0.1),
            }
        }

        logger.debug(
            f"[BUDGET] 📤 预算计算完成 | "
            f"总计={result['total_estimate']}元"
        )
        return result
