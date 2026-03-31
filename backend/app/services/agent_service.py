"""Agent service for itinerary generation with tool calling.

References:
- ITIN-01: User inputs destination, dates, preferences -> AI generates detailed daily itinerary
- ITIN-02: AI recommends attractions/activities based on user interests
- ITIN-05: User can modify itinerary, AI adjusts based on feedback
- 02-RESEARCH.md: DashScope function calling with LangChain tools
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from app.tools.weather_tools import get_weather, get_weather_forecast
from app.tools.map_tools import search_attraction, search_poi, plan_route
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class ItineraryAgent:
    """Agent for generating travel itineraries using tool-augmented LLM."""

    def __init__(self):
        self._tools = [
            get_weather,
            get_weather_forecast,
            search_attraction,
            search_poi,
            plan_route
        ]

    def _get_tool_schemas(self) -> list:
        """Get tool schemas for function calling."""
        schemas = []
        for tool in self._tools:
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.args_schema.schema() if tool.args_schema else {}
                }
            })
        return schemas

    async def _call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool by name with arguments.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool result as string
        """
        tool_map = {tool.name: tool for tool in self._tools}
        tool = tool_map.get(tool_name)

        if not tool:
            return f"Error: Tool '{tool_name}' not found"

        try:
            # Convert args to proper types if needed
            if "days" in arguments and tool_name == "get_weather_forecast":
                arguments["days"] = int(arguments["days"])

            result = await tool.ainvoke(arguments)
            return result
        except Exception as e:
            logger.error(f"Tool call error: {tool_name} - {e}")
            return f"Error calling {tool_name}: {str(e)}"

    async def generate_itinerary(
        self,
        destination: str,
        start_date: str,
        end_date: str,
        preferences: Optional[str] = None,
        travelers: int = 1,
        budget: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> dict:
        """Generate a travel itinerary using the agent.

        Args:
            destination: Destination city/region
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            preferences: User preferences and interests
            travelers: Number of travelers
            budget: Budget level
            conversation_id: Conversation ID for context

        Returns:
            Generated itinerary with daily plans
        """
        # Calculate number of days
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        num_days = (end - start).days + 1

        if num_days <= 0:
            raise ValueError("Invalid date range: end_date must be after start_date")

        logger.info(f"Generating itinerary: {destination}, {num_days} days, {travelers} travelers")

        # Build system prompt for itinerary generation
        system_prompt = self._build_itinerary_prompt(
            destination, num_days, preferences, travelers, budget
        )

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add conversation context if available
        if conversation_id:
            try:
                from app.db.postgres import get_context_window
                context = await get_context_window(
                    conversation_id,
                    max_messages=10,
                    max_tokens=2000
                )
                messages.extend(context)
            except Exception as e:
                logger.warning(f"Failed to load context: {e}")

        # Initial user message
        user_message = f"请为我生成一份{num_days}天的{destination}旅游行程计划。"
        if preferences:
            user_message += f"\n\n我的偏好：{preferences}"
        if budget:
            user_message += f"\n\n预算水平：{budget}"

        # 强制要求JSON格式
        user_message += "\n\n【重要】请先给出详细的行程建议，然后在回复的最后必须以```json```代码块格式输出结构化的行程数据。"

        messages.append({"role": "user", "content": user_message})

        # Use function calling with DashScope
        response = await self._call_with_tools(messages, destination, num_days)

        return response

    def _build_itinerary_prompt(
        self,
        destination: str,
        num_days: int,
        preferences: Optional[str],
        travelers: int,
        budget: Optional[str]
    ) -> str:
        """Build system prompt for itinerary generation."""
        prompt = f"""你是一位专业的旅游规划助手。请为用户生成一份详细的{num_days}天{destination}旅游行程。

【重要】输出要求：
1. 先用自然语言给出详细的行程建议（包含景点、美食、交通等实用信息）
2. 在回复的最后，必须以```json```代码块格式输出结构化的行程数据

行程要求：
1. 每天上午、下午、晚上的活动安排要具体
2. 推荐当地特色景点和美食
3. 考虑天气因素和路线合理性
4. 符合用户预算和偏好

输出格式示例（必须在回复最后输出）：
```json
{{
  "destination": "{destination}",
  "days": [
    {{
      "date": "2026-03-30",
      "theme": "老广味道·岭南风情",
      "weather": "晴 18~25°C",
      "activities": [
        {{"time": "上午", "activity": "游览陈家祠", "location": "陈家祠", "description": "岭南建筑瑰宝", "duration": "3小时", "cost": "免费"}},
        {{"time": "中午", "activity": "品尝广式早茶", "location": "泮溪酒家", "description": "正宗广式早茶", "duration": "2小时", "cost": "约80元/人"}},
        {{"time": "下午", "activity": "漫步永庆坊", "location": "永庆坊", "description": "骑楼建筑、非遗小店", "duration": "3小时", "cost": "免费"}},
        {{"time": "晚上", "activity": "荔枝湾涌夜游", "location": "荔枝湾涌", "description": "水乡夜景", "duration": "1.5小时", "cost": "约50元/人"}}
      ]
    }}
  ]
}}
```
"""

        if preferences:
            prompt += f"\n\n用户偏好：{preferences}"

        if budget:
            budget_guide = {
                "low": "经济实惠型（青年旅舍、公共交通、平价餐厅）",
                "medium": "舒适型（三星酒店、打车/地铁混合、中等餐厅）",
                "high": "豪华型（五星酒店、专车接送、高档餐厅）"
            }
            prompt += f"\n\n预算指导：{budget_guide.get(budget, '中等预算')}"

        if travelers > 1:
            prompt += f"\n\n出行人数：{travelers}人（请在安排活动时考虑团体需求）"

        return prompt

    async def _call_with_tools(
        self,
        messages: list,
        destination: str,
        num_days: int
    ) -> dict:
        """Call LLM with tool calling support.

        This is a simplified implementation. For full function calling,
        we would use DashScope's function calling API directly.
        """
        from uuid import uuid4

        # Calculate dates
        start = datetime.now() + timedelta(days=7)
        end = start + timedelta(days=num_days - 1)
        start_date = start.strftime("%Y-%m-%d")
        end_date = end.strftime("%Y-%m-%d")

        # For now, use a multi-step approach:
        # 1. Get weather forecast for the destination
        # 2. Search for attractions
        # 3. Generate itinerary with this context

        try:
            # Step 1: Get weather forecast
            logger.info(f"Fetching weather for {destination}")
            weather_result = await get_weather_forecast.ainvoke({"city": destination, "days": min(num_days, 7)})
            weather_info = json.loads(weather_result) if isinstance(weather_result, str) else weather_result

            # Step 2: Search for attractions
            logger.info(f"Searching attractions in {destination}")
            attractions_result = await search_attraction.ainvoke({"city": destination, "attraction_type": "景点"})
            attractions_info = json.loads(attractions_result) if isinstance(attractions_result, str) else attractions_result

            # Step 3: Build context for LLM
            context = f"""
目的地：{destination}
日期：{start_date} 至 {end_date}
天气信息：{weather_info.get('summary', 'N/A')}
推荐景点：{attractions_info.get('summary', 'N/A')}
"""

            # Update system message with tool results
            for msg in messages:
                if msg["role"] == "system":
                    msg["content"] += f"\n\n## 实时信息\n{context}"

            # Step 4: Generate itinerary using LLM
            full_response = ""
            async for chunk in llm_service.stream_chat(
                user_message=messages[-1]["content"],
                conversation_id=None  # Don't use context here to avoid duplication
            ):
                full_response += chunk

            # Parse the response
            itinerary = self._parse_itinerary_response(full_response, destination, num_days, weather_info, start_date, end_date)

            # Add required fields for frontend
            itinerary["id"] = str(uuid4())
            itinerary["start_date"] = start_date
            itinerary["end_date"] = end_date

            return itinerary

        except Exception as e:
            logger.error(f"Itinerary generation error: {e}")
            raise

    def _parse_itinerary_response(
        self,
        response: str,
        destination: str,
        num_days: int,
        weather_info: dict,
        start_date: str,
        end_date: str
    ) -> dict:
        """Parse LLM response into structured itinerary.

        Args:
            response: LLM response text
            destination: Destination name
            num_days: Number of days
            weather_info: Weather forecast data
            start_date: Trip start date
            end_date: Trip end date

        Returns:
            Structured itinerary dict
        """
        # Try to extract JSON from ```json``` code block
        try:
            # Match ```json ... ``` code block
            json_block_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_block_match:
                json_str = json_block_match.group(1).strip()
                parsed = json.loads(json_str)
                # Handle different JSON formats
                if "days" in parsed:
                    logger.info(f"[Agent] Successfully parsed JSON from code block, {len(parsed['days'])} days")
                    # Normalize the data structure
                    return self._normalize_itinerary(parsed, destination, start_date, end_date, weather_info)
                elif "itinerary" in parsed:
                    # Convert LLM format to our format
                    logger.info(f"[Agent] Converting LLM itinerary format, {len(parsed['itinerary'])} days")
                    return self._convert_llm_format(parsed, destination, num_days, weather_info, start_date, end_date)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[Agent] Failed to parse JSON code block: {e}")

        # Try to extract plain JSON (fallback)
        try:
            # Find JSON object with "days" key
            json_match = re.search(r'\{\s*"destination"[\s\S]*?"days"[\s\S]*?\}', response)
            if json_match:
                parsed = json.loads(json_match.group())
                if "days" in parsed:
                    logger.info(f"[Agent] Successfully parsed plain JSON, {len(parsed['days'])} days")
                    return self._normalize_itinerary(parsed, destination, start_date, end_date, weather_info)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[Agent] Failed to parse plain JSON: {e}")

        # Fallback: Try to extract itinerary from natural language
        logger.info("[Agent] JSON parsing failed, attempting to extract from natural language...")
        return self._extract_from_text(response, destination, num_days, weather_info, start_date, end_date)

    def _normalize_itinerary(
        self,
        parsed: dict,
        destination: str,
        start_date: str,
        end_date: str,
        weather_info: dict
    ) -> dict:
        """Normalize parsed itinerary to frontend-expected format.

        Args:
            parsed: Parsed JSON from LLM
            destination: Destination name
            start_date: Trip start date
            end_date: Trip end date
            weather_info: Weather forecast data

        Returns:
            Normalized itinerary dict
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        forecasts = []
        if isinstance(weather_info, dict) and "forecasts" in weather_info:
            forecasts = weather_info["forecasts"]

        days = []
        for i, day in enumerate(parsed.get("days", [])):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            weather = forecasts[i] if i < len(forecasts) else {}

            # Normalize weather data - handle both Amap format and LLM format
            weather_data = {}
            if isinstance(weather, dict):
                # Amap API format: temp_min, temp_max, day_weather
                temp_max = weather.get("temp_max") or "25"
                temp_min = weather.get("temp_min") or "15"
                condition = weather.get("condition_day") or weather.get("day_weather") or weather.get("condition") or "晴"

                weather_data = {
                    "temp_max": str(temp_max),
                    "temp_min": str(temp_min),
                    "condition": str(condition)
                }
            else:
                # Default weather
                weather_data = {
                    "temp_max": "25",
                    "temp_min": "15",
                    "condition": "晴"
                }

            # Normalize activities - ensure required fields
            activities = day.get("activities", [])
            if not isinstance(activities, list):
                activities = []

            # Ensure each activity has required fields
            normalized_activities = []
            for act in activities:
                if isinstance(act, dict):
                    normalized_activities.append({
                        "time": act.get("time", "全天"),
                        "activity": act.get("activity", ""),
                        "location": act.get("location", ""),
                        "description": act.get("description", ""),
                        "duration": act.get("duration", "2-3小时"),
                        "cost": act.get("cost", "待定")
                    })

            days.append({
                "date": date,
                "theme": day.get("theme", ""),
                "weather": weather_data,
                "activities": normalized_activities
            })

        return {
            "destination": destination,
            "days": days
        }

    def _convert_llm_format(
        self,
        llm_data: dict,
        destination: str,
        num_days: int,
        weather_info: dict,
        start_date: str,
        end_date: str
    ) -> dict:
        """Convert LLM JSON format to our expected format.

        Args:
            llm_data: LLM response JSON (with 'itinerary' key)
            destination: Destination name
            num_days: Number of days
            weather_info: Weather forecast data
            start_date: Trip start date
            end_date: Trip end date

        Returns:
            Structured itinerary dict in our format
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        forecasts = []
        if isinstance(weather_info, dict) and "forecasts" in weather_info:
            forecasts = weather_info["forecasts"]

        days = []
        llm_itinerary = llm_data.get("itinerary", [])

        for i, llm_day in enumerate(llm_itinerary[:num_days]):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            weather = forecasts[i] if i < len(forecasts) else {}

            # Normalize weather data
            weather_data = {}
            if isinstance(weather, dict):
                temp_max = weather.get("temp_max") or weather.get("temp_day") or "25"
                temp_min = weather.get("temp_min") or weather.get("temp_night") or "15"
                condition = weather.get("condition") or weather.get("day_weather") or "晴"

                weather_data = {
                    "temp_max": str(temp_max),
                    "temp_min": str(temp_min),
                    "condition": str(condition)
                }

            # Extract activities from LLM format
            activities = []
            for time_key, time_name in [("morning", "上午"), ("afternoon", "下午"), ("evening", "晚上")]:
                if time_key in llm_day:
                    time_data = llm_day[time_key]
                    if isinstance(time_data, dict):
                        activities.append({
                            "time": time_name,
                            "activity": time_data.get("activity", ""),
                            "location": time_data.get("location", ""),
                            "description": time_data.get("details", ""),
                            "duration": time_data.get("duration", "2-3小时"),
                            "cost": time_data.get("cost", "待定")
                        })

            # If no activities found, add defaults
            if not activities:
                activities = [
                    {"time": "上午", "activity": f"探索{destination}", "location": "市区", "description": "游览当地景点", "duration": "3小时", "cost": "待定"},
                    {"time": "下午", "activity": "品尝当地美食", "location": "特色餐厅", "description": "体验当地美食", "duration": "2小时", "cost": "约100元/人"},
                    {"time": "晚上", "activity": "夜游城市", "location": "商业区", "description": "欣赏夜景", "duration": "2小时", "cost": "待定"}
                ]

            days.append({
                "date": date,
                "theme": llm_day.get("theme", "探索之旅"),
                "weather": weather_data,
                "activities": activities
            })

        return {
            "destination": destination,
            "days": days
        }

    def _extract_from_text(
        self,
        response: str,
        destination: str,
        num_days: int,
        weather_info: dict,
        start_date: str,
        end_date: str
    ) -> dict:
        """Extract itinerary from natural language response.

        Args:
            response: LLM response text (natural language)
            destination: Destination name
            num_days: Number of days
            weather_info: Weather forecast data
            start_date: Trip start date
            end_date: Trip end date

        Returns:
            Structured itinerary dict
        """
        # Fallback: Generate structured itinerary from text
        start = datetime.strptime(start_date, "%Y-%m-%d")
        days = []

        forecasts = []
        if isinstance(weather_info, dict) and "forecasts" in weather_info:
            forecasts = weather_info["forecasts"]

        for i in range(num_days):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            weather = forecasts[i] if i < len(forecasts) else {}

            # Normalize weather data
            weather_data = {}
            if isinstance(weather, dict):
                temp_max = weather.get("temp_max") or weather.get("temp_day") or "25"
                temp_min = weather.get("temp_min") or weather.get("temp_night") or "15"
                condition = weather.get("condition") or weather.get("day_weather") or "晴"

                weather_data = {
                    "temp_max": str(temp_max),
                    "temp_min": str(temp_min),
                    "condition": str(condition)
                }

            days.append({
                "date": date,
                "theme": "探索之旅",
                "weather": weather_data,
                "activities": [
                    {
                        "time": "上午",
                        "activity": f"探索{destination}市区",
                        "location": "市中心",
                        "description": "游览当地著名景点，感受城市文化",
                        "duration": "3小时",
                        "cost": "待定"
                    },
                    {
                        "time": "下午",
                        "activity": "品尝当地美食",
                        "location": "特色餐厅",
                        "description": "体验当地特色菜肴",
                        "duration": "2小时",
                        "cost": "约100元/人"
                    },
                    {
                        "time": "晚上",
                        "activity": "夜游城市",
                        "location": "商业区",
                        "description": "欣赏城市夜景，购物休闲",
                        "duration": "2小时",
                        "cost": "待定"
                    }
                ]
            })

        return {
            "destination": destination,
            "days": days,
            "raw_response": response  # Include raw response for reference
        }

    async def refine_itinerary(
        self,
        itinerary_id: UUID,
        feedback: str,
        conversation_id: Optional[str] = None
    ) -> dict:
        """Refine an existing itinerary based on user feedback.

        Args:
            itinerary_id: ID of itinerary to refine
            feedback: User's modification request
            conversation_id: Conversation ID for context

        Returns:
            Updated itinerary
        """
        # Get existing itinerary
        from app.db.postgres import get_itinerary
        existing = await get_itinerary(itinerary_id)

        if not existing:
            raise ValueError(f"Itinerary {itinerary_id} not found")

        # Build refinement prompt
        prompt = f"""用户希望修改现有的旅游行程。请根据用户的反馈调整行程。

原行程目的地：{existing['destination']}
原日期：{existing['start_date']} 至 {existing['end_date']}
原行程天数：{len(existing['days'])}天

用户反馈：{feedback}

请生成修改后的行程，保持JSON格式。
"""

        # Call LLM with refinement prompt
        full_response = ""
        async for chunk in llm_service.stream_chat(
            user_message=prompt,
            conversation_id=conversation_id
        ):
            full_response += chunk

        # Parse refined itinerary
        refined = self._parse_itinerary_response(
            full_response,
            existing['destination'],
            len(existing['days']),
            {},
            existing['start_date'],
            existing['end_date']
        )

        # Add id to refined itinerary
        refined["id"] = str(itinerary_id)
        refined["start_date"] = existing['start_date']
        refined["end_date"] = existing['end_date']

        # Update in database
        await self._save_refined_itinerary(itinerary_id, refined['days'])

        return refined

    async def _save_refined_itinerary(self, itinerary_id: UUID, days: list) -> None:
        """Save refined itinerary to database."""
        from app.db.postgres import update_itinerary
        await update_itinerary(itinerary_id, days)


# Global agent instance
itinerary_agent = ItineraryAgent()
