"""LangChain tools for weather data retrieval.

References:
- TOOL-04: Agent autonomously calls weather API
- 02-RESEARCH.md: LangChain @tool decorator pattern
- AI-04: Tool calling error handling and retry
- D-16, D-17: Retry with fallback

使用高德地图天气API，与地图API共用同一个key。
"""

import json
import logging
from typing import Literal

from langchain_core.tools import tool

from app.services.weather_service import weather_service
from app.utils.retry import with_retry_and_fallback

logger = logging.getLogger(__name__)


@tool
@with_retry_and_fallback(
    fallback_value='{"error": "天气服务暂时不可用，请稍后再试", "city": "", "condition": "未知", "summary": "暂时无法获取天气信息"}',
    max_attempts=3
)
async def get_weather(
    city: str
) -> str:
    """获取指定城市的实时天气信息.

    用于获取当前天气状况，包括温度、天气状况、湿度、风力等信息。

    Args:
        city: 城市名称，如"北京"、"上海"、"广州"

    Returns:
        JSON格式的天气信息字符串，包含温度、天气状况、湿度等
    """
    logger.info(f"Tool called: get_weather for city={city}")

    result = await weather_service.get_realtime_weather(city)

    if "error" in result:
        return json.dumps({"error": result["error"]}, ensure_ascii=False)

    # Format for LLM consumption - 高德API字段名
    return json.dumps({
        "city": result["city"],
        "current_temp": f"{result['temp']}°C",
        "condition": result["weather"],
        "humidity": f"{result.get('humidity', 'N/A')}%",
        "wind": f"{result.get('wind_direction', '')} {result.get('wind_power', '')}级".strip(),
        "report_time": result.get("report_time", ""),
        "summary": f"当前温度{result['temp']}°C，{result['weather']}，湿度{result.get('humidity', 'N/A')}%"
    }, ensure_ascii=False)


@tool
@with_retry_and_fallback(
    fallback_value='{"error": "天气预报服务暂时不可用，请稍后再试", "city": "", "forecasts": [], "summary": "暂时无法获取天气预报"}',
    max_attempts=3
)
async def get_weather_forecast(
    city: str,
    days: Literal[3, 4] = 3
) -> str:
    """获取指定城市的天气预报.

    用于获取未来几天的天气预报，包括最高/最低温度、天气状况等信息。

    Args:
        city: 城市名称，如"北京"、"上海"、"广州"
        days: 预报天数，可选3天或4天（高德最多支持4天）

    Returns:
        JSON格式的天气预报信息字符串
    """
    logger.info(f"Tool called: get_weather_forecast for city={city}, days={days}")

    result = await weather_service.get_weather_forecast(city, days)

    if "error" in result:
        return json.dumps({"error": result["error"]}, ensure_ascii=False)

    # Format for LLM consumption - 高德API字段名
    forecasts = []
    for day in result["forecasts"]:
        forecasts.append({
            "date": day["date"],
            "week": day.get("week", ""),
            "temp_range": f"{day['temp_min']}~{day['temp_max']}°C",
            "condition_day": day["day_weather"],
            "condition_night": day["night_weather"],
            "wind_day": f"{day.get('wind_direction_day', '')}{day.get('wind_power_day', '')}级".strip(),
            "summary": f"{day['date']} ({day.get('week', '')})：{day['temp_min']}~{day['temp_max']}°C，白天{day['day_weather']}，夜间{day['night_weather']}"
        })

    return json.dumps({
        "city": result["city"],
        "days": result["days"],
        "forecasts": forecasts,
        "summary": "\n".join([f["summary"] for f in forecasts])
    }, ensure_ascii=False)
