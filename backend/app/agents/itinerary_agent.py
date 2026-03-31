"""Itinerary generation specialist agent.

References:
- D-10: ItineraryAgent for itinerary generation and optimization
- 03-RESEARCH.md: Refactor existing ItineraryAgent into subagent
"""

import json
import logging
from datetime import datetime, timedelta
from app.agents.base import BaseAgent
from app.services.llm_service import llm_service
from app.tools.weather_tools import get_weather_forecast
from app.tools.map_tools import search_attraction


logger = logging.getLogger(__name__)


class ItineraryAgent(BaseAgent):
    """Agent specializing in itinerary generation.

    Per D-10: Handles itinerary generation and optimization.
    """

    def __init__(self):
        super().__init__("ItineraryAgent")

    async def generate_itinerary(
        self,
        destination: str,
        days: int,
        preferences: str = None,
        user_id: str = None
    ) -> dict:
        """Generate a travel itinerary.

        Args:
            destination: Destination city
            days: Number of days
            preferences: User preferences
            user_id: User ID for context

        Returns:
            Generated itinerary
        """
        self._log_request("generate_itinerary", destination=destination, days=days)

        try:
            # Get weather context
            weather_result = await get_weather_forecast.ainvoke({
                "city": destination,
                "days": min(days, 4)
            })
            weather_info = json.loads(weather_result) if isinstance(weather_result, str) else weather_result

            # Get attraction context
            attractions_result = await search_attraction.ainvoke({
                "city": destination,
                "attraction_type": "景点"
            })
            attractions_info = json.loads(attractions_result) if isinstance(attractions_result, str) else attractions_result

            # Build prompt
            prompt = self._build_itinerary_prompt(
                destination, days, preferences, weather_info, attractions_info
            )

            # Generate with LLM
            full_response = ""
            async for chunk in llm_service.stream_chat(
                user_message=prompt,
                conversation_id=None
            ):
                full_response += chunk

            # Parse response
            itinerary = self._parse_itinerary_response(
                full_response, destination, days, weather_info
            )

            self._log_response("generate_itinerary", True)
            return itinerary

        except Exception as e:
            logger.error(f"[ItineraryAgent] Error: {e}")
            return {
                "destination": destination,
                "days": self._fallback_itinerary(destination, days, {})
            }

    def _build_itinerary_prompt(
        self,
        destination: str,
        days: int,
        preferences: str,
        weather_info: dict,
        attractions_info: dict
    ) -> str:
        """Build itinerary generation prompt."""
        prompt = f"""请生成一份{days}天的{destination}旅游行程。

天气信息：{weather_info.get('summary', 'N/A')}
推荐景点：{attractions_info.get('summary', 'N/A')}
"""

        if preferences:
            prompt += f"\n用户偏好：{preferences}"

        prompt += """

请以JSON格式输出行程，格式如下：
```json
{
  "destination": "城市名",
  "days": [
    {
      "date": "2026-03-30",
      "theme": "主题",
      "weather": "天气信息",
      "activities": [
        {"time": "上午", "activity": "活动", "location": "地点", "description": "描述", "duration": "时长", "cost": "费用"}
      ]
    }
  ]
}
```
"""
        return prompt

    def _parse_itinerary_response(
        self,
        response: str,
        destination: str,
        days: int,
        weather_info: dict
    ) -> dict:
        """Parse LLM response into structured itinerary."""
        import re

        # Try to extract JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if "days" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        # Fallback
        return {
            "destination": destination,
            "days": self._fallback_itinerary(destination, days, weather_info)
        }

    def _fallback_itinerary(self, destination: str, days: int, weather_info: dict) -> list:
        """Generate fallback itinerary."""
        itinerary_days = []
        start = datetime.now()

        for i in range(days):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            itinerary_days.append({
                "date": date,
                "theme": "探索之旅",
                "weather": weather_info.get("forecasts", [{}])[i].get("temp_range", "N/A") if weather_info.get("forecasts") else "N/A",
                "activities": [
                    {"time": "上午", "activity": f"游览{destination}", "location": "市区", "description": "探索城市景点", "duration": "3小时", "cost": "待定"},
                    {"time": "下午", "activity": "品尝美食", "location": "特色餐厅", "description": "体验当地美食", "duration": "2小时", "cost": "约100元/人"},
                    {"time": "晚上", "activity": "夜游", "location": "商业区", "description": "欣赏夜景", "duration": "2小时", "cost": "待定"}
                ]
            })

        return itinerary_days
