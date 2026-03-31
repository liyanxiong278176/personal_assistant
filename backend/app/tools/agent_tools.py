"""LangChain tools for subagent delegation.

References:
- AI-02: Multi-agent collaboration via tool delegation
- AI-04: Tool calling error handling and retry
- D-11: Structured message communication between agents
- D-16, D-17: Retry with fallback
- 03-RESEARCH.md: Subagents pattern with @tool decorators
"""

import json
import logging
from typing import Literal, Optional

from langchain_core.tools import tool

from app.utils.retry import with_retry_and_fallback

logger = logging.getLogger(__name__)

# Try to import agent modules - they may not exist yet (Plan 03-03 pending)
try:
    from app.agents.weather_agent import WeatherAgent
    weather_agent = WeatherAgent()
except ImportError:
    logger.warning("WeatherAgent not available - Plan 03-03 pending")
    weather_agent = None

try:
    from app.agents.map_agent import MapAgent
    map_agent = MapAgent()
except ImportError:
    logger.warning("MapAgent not available - Plan 03-03 pending")
    map_agent = None

try:
    from app.agents.itinerary_agent import ItineraryAgent
    itinerary_agent = ItineraryAgent()
except ImportError:
    logger.warning("ItineraryAgent not available - Plan 03-03 pending")
    itinerary_agent = None


@tool
@with_retry_and_fallback(
    fallback_value='{"error": "天气助手暂时无法响应", "weather": {"condition": "未知", "summary": "天气服务暂时不可用"}}',
    max_attempts=3
)
async def delegate_to_weather_agent(
    task: Literal["获取实时天气", "获取天气预报", "interpret_for_travel"],
    city: str,
    days: Optional[int] = None
) -> str:
    """委托给天气专家Agent获取天气信息.

    Per D-11: Structured communication through tool interface.

    Args:
        task: 具体任务类型
            - "获取实时天气": 获取当前天气状况
            - "获取天气预报": 获取未来几天的天气预报
            - "interpret_for_travel": 为旅游规划解读天气
        city: 城市名称，如"北京"、"上海"
        days: 预报天数（3或4天），仅用于天气预报任务

    Returns:
        JSON格式的天气信息字符串
    """
    logger.info(f"[AgentTools] Delegating to WeatherAgent: task={task}, city={city}")

    # Check if agent is available (Plan 03-03)
    if weather_agent is None:
        return json.dumps({
            "error": "天气智能体暂未实现，请等待Plan 03-03完成",
            "task": task,
            "city": city
        }, ensure_ascii=False)

    try:
        if task == "interpret_for_travel":
            result = await weather_agent.interpret_for_travel(city, days or 3)
        else:
            result_data = await weather_agent.get_weather_info(city, days)
            result = json.dumps(result_data, ensure_ascii=False)

        return result

    except Exception as e:
        logger.error(f"[AgentTools] WeatherAgent error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
@with_retry_and_fallback(
    fallback_value='{"error": "地图助手暂时无法响应", "pois": {"summary": "地图服务暂时不可用"}}',
    max_attempts=3
)
async def delegate_to_map_agent(
    task: Literal["搜索景点", "搜索POI", "规划路线", "推荐景点"],
    city: str,
    keywords: Optional[str] = None,
    poi_type: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None
) -> str:
    """委托给地图专家Agent处理地图和POI相关任务.

    Per D-11: Structured communication through tool interface.

    Args:
        task: 任务类型
            - "搜索景点": 搜索旅游景点
            - "搜索POI": 搜索兴趣点（酒店、餐厅等）
            - "规划路线": 规划两点之间的路线
            - "推荐景点": 根据偏好推荐景点
        city: 城市名称
        keywords: 搜索关键词（用于POI搜索）
        poi_type: POI类型（景点、酒店、餐厅等）
        origin: 起点（用于路线规划）
        destination: 终点（用于路线规划）

    Returns:
        JSON格式的地图/POI信息字符串
    """
    logger.info(f"[AgentTools] Delegating to MapAgent: task={task}, city={city}")

    # Check if agent is available (Plan 03-03)
    if map_agent is None:
        return json.dumps({
            "error": "地图智能体暂未实现，请等待Plan 03-03完成",
            "task": task,
            "city": city
        }, ensure_ascii=False)

    try:
        if task == "规划路线":
            if not origin or not destination:
                return json.dumps({"error": "路线规划需要起点和终点"}, ensure_ascii=False)
            result_data = await map_agent.plan_route(origin, destination)
            return json.dumps(result_data, ensure_ascii=False)

        elif task == "推荐景点":
            result = await map_agent.recommend_attractions(city, [keywords] if keywords else None)
            return json.dumps({"summary": result}, ensure_ascii=False)

        else:  # 搜索景点 or 搜索POI
            result_data = await map_agent.search_poi(city, keywords, poi_type or keywords)
            return json.dumps(result_data, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[AgentTools] MapAgent error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
@with_retry_and_fallback(
    fallback_value='{"error": "行程助手暂时无法响应", "destination": "", "days": []}',
    max_attempts=3
)
async def delegate_to_itinerary_agent(
    task: Literal["生成行程", "优化行程"],
    destination: str,
    days: int,
    preferences: Optional[str] = None,
    user_id: Optional[str] = None
) -> str:
    """委托给行程规划Agent生成旅游行程.

    Per D-11: Structured communication through tool interface.

    Args:
        task: 任务类型
            - "生成行程": 根据目的地和天数生成新行程
            - "优化行程": 根据反馈优化现有行程
        destination: 目的地城市
        days: 行程天数
        preferences: 用户偏好描述
        user_id: 用户ID（用于获取个性化偏好）

    Returns:
        JSON格式的行程计划字符串
    """
    logger.info(f"[AgentTools] Delegating to ItineraryAgent: task={task}, destination={destination}")

    # Check if agent is available (Plan 03-03)
    if itinerary_agent is None:
        return json.dumps({
            "error": "行程智能体暂未实现，请等待Plan 03-03完成",
            "task": task,
            "destination": destination,
            "days": days
        }, ensure_ascii=False)

    try:
        if task == "生成行程":
            result = await itinerary_agent.generate_itinerary(
                destination=destination,
                days=days,
                preferences=preferences,
                user_id=user_id
            )
            return json.dumps(result, ensure_ascii=False)

        else:
            return json.dumps({"error": "优化行程功能暂未实现"}, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[AgentTools] ItineraryAgent error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
