"""Weather specialist agent.

References:
- D-10: WeatherAgent for weather information and interpretation
- AI-03: Autonomous tool selection based on task
"""

import json
from app.agents.base import BaseAgent, AgentResponse
from app.tools.weather_tools import get_weather, get_weather_forecast


class WeatherAgent(BaseAgent):
    """Agent specializing in weather information tasks.

    Per D-10: Handles weather information retrieval and interpretation.
    """

    def __init__(self):
        super().__init__("WeatherAgent")
        self.tools = {
            "get_weather": get_weather,
            "get_weather_forecast": get_weather_forecast
        }

    async def get_weather_info(self, city: str, days: int = None) -> dict:
        """Get weather information for a city.

        Per AI-03: Select appropriate tool based on request parameters.

        Args:
            city: City name
            days: If provided, get forecast (3 or 4 days)

        Returns:
            Weather information dict
        """
        self._log_request("get_weather_info", city=city, days=days)

        try:
            # Select tool based on request (per AI-03)
            if days:
                result = await self.tools["get_weather_forecast"].ainvoke({
                    "city": city,
                    "days": days if days in [3, 4] else 3
                })
            else:
                result = await self.tools["get_weather"].ainvoke({"city": city})

            # Parse JSON result
            weather_data = json.loads(result) if isinstance(result, str) else result

            self._log_response("get_weather_info", True, city=city)
            return {
                "success": True,
                "weather": weather_data
            }

        except Exception as e:
            self.logger.error(f"[WeatherAgent] Error: {e}")
            self._log_response("get_weather_info", False, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "weather": {"condition": "暂时无法获取天气信息"}
            }

    async def interpret_for_travel(self, city: str, days: int = 3) -> str:
        """Interpret weather for travel planning.

        Args:
            city: City name
            days: Number of days for forecast

        Returns:
            Travel-oriented weather summary
        """
        self._log_request("interpret_for_travel", city=city, days=days)

        weather_info = await self.get_weather_info(city, days)

        if not weather_info["success"]:
            return f"抱歉，无法获取{city}的天气信息。"

        data = weather_info["weather"]

        # Build travel-friendly summary
        if "forecasts" in data:
            summaries = [f.get("summary", "") for f in data["forecasts"]]
            return f"{city}天气预报：\n" + "\n".join(summaries)
        else:
            return f"{city}当前天气：{data.get('summary', data.get('condition', ''))}"
