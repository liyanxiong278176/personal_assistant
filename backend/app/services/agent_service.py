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
        response = await self._call_with_tools(messages, destination, num_days, start_date, end_date)

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

【核心要求】
请以**JSON格式**输出行程，description字段要包含详细的推荐理由、交通方式、注意事项、菜品建议等丰富信息。

行程要求：
1. **必须生成完整的{num_days}天行程，JSON中days数组必须恰好包含{num_days}个元素！**
2. **请仔细检查：days数组的长度必须是{num_days}，不能多也不能少！**
3. 每天安排3-5个活动，时间段要具体（如"08:00-11:00"）
4. description字段必须详细：包含推荐理由、交通、注意事项、预约提醒等
5. 推荐具体餐厅名称、菜品建议、人均消费
6. 考虑实时天气、路线合理性
7. 每天设定一个主题

输出格式：
```json
{{
  "destination": "{destination}",
  "overview": "整体行程概述：1-2句话介绍行程亮点和风格",
  "tips": ["预约提醒", "交通建议", "注意事项"],
  "days": [
    {{
      "date": "2026-03-30",
      "theme": "今日主题",
      "summary": "今日亮点和特色介绍",
      "activities": [
        {{
          "time": "08:00-11:00",
          "period": "清晨",
          "activity": "观看升旗仪式",
          "location": "天安门广场",
          "description": "推荐理由：感受庄严时刻。交通：地铁1号线。注意事项：需提前安检，禁带大件行李。",
          "duration": "2小时",
          "cost": "免费"
        }}
      ]
    }}
  ]
}}
```

**重要**：
1. days数组必须恰好包含{num_days}个元素！
2. description要详细丰富，包含推荐理由、交通、注意事项等！
3. 必须包含overview字段（整体行程概述）和tips数组（3-5个实用提示）！
4. 直接输出JSON，用```json...```包裹即可。
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
        num_days: int,
        start_date: str,
        end_date: str
    ) -> dict:
        """Call LLM with tool calling support.

        This is a simplified implementation. For full function calling,
        we would use DashScope's function calling API directly.

        Args:
            messages: Conversation messages
            destination: Travel destination
            num_days: Number of travel days
            start_date: Trip start date (YYYY-MM-DD)
            end_date: Trip end date (YYYY-MM-DD)
        """
        from uuid import uuid4

        # Parse the input dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # Check if dates are too far in the future for weather forecast
        days_until_trip = (start - datetime.now()).days
        max_forecast_days = 7  # Most weather APIs support up to 7-15 days

        weather_unavailable = False
        if days_until_trip > max_forecast_days:
            weather_unavailable = True
            logger.warning(f"Trip is {days_until_trip} days away, beyond weather forecast range")

        # For now, use a multi-step approach:
        # 1. Get weather forecast for the destination (if available)
        # 2. Search for attractions
        # 3. Generate itinerary with this context

        try:
            # Step 1: Get weather forecast (only if dates are within range)
            weather_info = {}
            if not weather_unavailable:
                logger.info(f"Fetching weather for {destination}")
                try:
                    weather_result = await get_weather_forecast.ainvoke({"city": destination, "days": min(num_days, max_forecast_days)})
                    weather_info = json.loads(weather_result) if isinstance(weather_result, str) else weather_result
                except Exception as e:
                    logger.warning(f"Weather fetch failed: {e}")
                    weather_unavailable = True

            # Step 2: Search for attractions
            logger.info(f"Searching attractions in {destination}")
            attractions_result = await search_attraction.ainvoke({"city": destination, "attraction_type": "景点"})
            attractions_info = json.loads(attractions_result) if isinstance(attractions_result, str) else attractions_result
            logger.info(f"[ItineraryAgent] Attractions found: {attractions_info.get('count', 0)}")
            if 'attractions' in attractions_info and attractions_info['attractions']:
                top_3 = [a['name'] for a in attractions_info['attractions'][:3]]
                logger.info(f"[ItineraryAgent] Top 3 attractions: {top_3}")

            # Step 3: Build context for LLM
            weather_note = ""
            if weather_unavailable:
                weather_note = f"\n⚠️ 注意：行程日期（{start_date}）超出天气预报范围（{max_forecast_days}天），建议出发前1-3天再次查询准确天气。"

            context = f"""
目的地：{destination}
日期：{start_date} 至 {end_date}（共{num_days}天）{weather_note}
天气信息：{weather_info.get('summary', 'N/A（日期较远，暂无数据）') if not weather_unavailable else '日期较远，暂无天气预报数据'}
推荐景点：{attractions_info.get('summary', 'N/A')}

【重要】请生成恰好{num_days}天的行程，JSON中days数组必须有{num_days}个元素！
"""

            # Debug logging
            logger.info(f"[ItineraryAgent] Full context being passed to LLM:\n{context}")
            logger.info(f"[ItineraryAgent] System prompt length before context: {len(messages[0]['content'])} chars")
            for msg in messages:
                if msg["role"] == "system":
                    msg["content"] += f"\n\n## 实时信息\n{context}"

            # Step 4: Generate itinerary using LLM
            # Add JSON format requirements at the END (most recent instruction)
            system_prompt = messages[0]["content"]
            user_msg = messages[-1]["content"]

            # Add format requirements to user message (most prominent position)
            format_requirements = f"""

## 输出格式要求
请直接以JSON格式输出行程，必须包含以下字段：
- overview: 整体行程概述（1-2句话）
- tips: 实用提示数组（3-5条）
- days数组：每天包含theme（主题）、summary（亮点）、activities列表

示例格式：
{{
  "destination": "{destination}",
  "overview": "行程概述",
  "tips": ["提示1", "提示2"],
  "days": [{{"date": "2026-10-01", "theme": "主题", "summary": "亮点", "activities": [{{"time": "08:00-11:00", "activity": "活动", "location": "地点", "description": "详细说明", "duration": "时长", "cost": "费用"}}]}}]
}}

重要：直接输出JSON，用```json包裹，不要其他文字！
"""

            full_response = ""
            async for chunk in llm_service.stream_chat(
                user_message=user_msg + format_requirements,
                conversation_id=None,
                system_prompt=system_prompt
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
            num_days: Expected number of days (validates and pads if needed)
            weather_info: Weather forecast data
            start_date: Trip start date
            end_date: Trip end date

        Returns:
            Structured itinerary dict with exactly num_days entries
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
                    actual_days = len(parsed.get("days", []))
                    logger.info(f"[Agent] Successfully parsed JSON from code block, {actual_days} days (expected {num_days})")
                    # Normalize the data structure (will validate and pad)
                    return self._normalize_itinerary(parsed, destination, start_date, end_date, weather_info, num_days)
                elif "itinerary" in parsed:
                    # Convert LLM format to our format
                    actual_days = len(parsed.get("itinerary", []))
                    logger.info(f"[Agent] Converting LLM itinerary format, {actual_days} days (expected {num_days})")
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
                    actual_days = len(parsed.get("days", []))
                    logger.info(f"[Agent] Successfully parsed plain JSON, {actual_days} days (expected {num_days})")
                    return self._normalize_itinerary(parsed, destination, start_date, end_date, weather_info, num_days)
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
        weather_info: dict,
        num_days: int = None
    ) -> dict:
        """Normalize parsed itinerary to frontend-expected format.

        Args:
            parsed: Parsed JSON from LLM
            destination: Destination name
            start_date: Trip start date
            end_date: Trip end date
            weather_info: Weather forecast data (may be empty if dates too far)
            num_days: Expected number of days (validates and pads if needed)

        Returns:
            Normalized itinerary dict with exactly num_days entries
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # Calculate expected days if not provided
        if num_days is None:
            num_days = (end - start).days + 1

        forecasts = []
        has_weather = False
        if isinstance(weather_info, dict) and "forecasts" in weather_info:
            forecasts = weather_info["forecasts"]
            if forecasts and len(forecasts) > 0:
                has_weather = True

        parsed_days = parsed.get("days", [])
        actual_days = len(parsed_days)

        # Log warning if day count mismatch
        if actual_days < num_days:
            logger.warning(f"[Agent] LLM returned {actual_days} days, expected {num_days}. Padding with fallback days.")
        elif actual_days > num_days:
            logger.warning(f"[Agent] LLM returned {actual_days} days, expected {num_days}. Truncating to {num_days}.")

        days = []
        for i in range(num_days):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            weather = forecasts[i] if i < len(forecasts) else {}

            # Get day data from parsed response or use fallback
            day = parsed_days[i] if i < actual_days else None

            # Normalize weather data - handle both Amap format and LLM format
            weather_data = {}
            if has_weather and isinstance(weather, dict) and weather:
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
                # Weather not available - show placeholder
                weather_data = {
                    "temp_max": "--",
                    "temp_min": "--",
                    "condition": "暂无预报"
                }

            # Normalize activities - ensure required fields
            if day:
                activities = day.get("activities", [])
                theme = day.get("theme", "")
                summary = day.get("summary", "")
            else:
                # Fallback day
                activities = [
                    {"time": "上午", "activity": f"探索{destination}", "location": "市区", "description": "游览当地著名景点", "duration": "3小时", "cost": "待定"},
                    {"time": "下午", "activity": "品尝当地美食", "location": "特色餐厅", "description": "体验当地特色菜肴", "duration": "2小时", "cost": "约100元/人"},
                    {"time": "晚上", "activity": "夜游城市", "location": "商业区", "description": "欣赏城市夜景", "duration": "2小时", "cost": "待定"}
                ]
                theme = "自由探索"
                summary = ""

            if not isinstance(activities, list):
                activities = []

            # Ensure each activity has required fields
            normalized_activities = []
            for act in activities:
                if isinstance(act, dict):
                    # Extract fields with fallbacks
                    activity_name = act.get("activity", "").strip()
                    location_name = act.get("location", "").strip()

                    # If activity is empty but location exists, use location as activity
                    if not activity_name and location_name:
                        activity_name = location_name
                    # If both are empty, use a default
                    if not activity_name:
                        activity_name = "自由活动"

                    normalized_activities.append({
                        "time": act.get("time", "全天"),
                        "activity": activity_name,
                        "location": location_name,
                        "description": act.get("description", ""),
                        "duration": act.get("duration", "2-3小时"),
                        "cost": act.get("cost", "待定")
                    })

            days.append({
                "date": date,
                "theme": theme,
                "summary": summary,
                "weather": weather_data,
                "activities": normalized_activities
            })

        return {
            "destination": destination,
            "overview": parsed.get("overview", f"为您精心规划的{num_days}天{destination}之旅，涵盖当地精华景点与特色体验。"),
            "tips": parsed.get("tips", [
                "建议提前预订热门景点门票",
                "关注天气变化，合理安排行程",
                "品尝当地特色美食，体验地道文化"
            ]),
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
            num_days: Number of days (validates and pads if needed)
            weather_info: Weather forecast data (may be empty if dates too far)
            start_date: Trip start date
            end_date: Trip end date

        Returns:
            Structured itinerary dict in our format with exactly num_days entries
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        forecasts = []
        has_weather = False
        if isinstance(weather_info, dict) and "forecasts" in weather_info:
            forecasts = weather_info["forecasts"]
            if forecasts and len(forecasts) > 0:
                has_weather = True

        days = []
        llm_itinerary = llm_data.get("itinerary", [])
        actual_days = len(llm_itinerary)

        # Log warning if day count mismatch
        if actual_days < num_days:
            logger.warning(f"[Agent] LLM format has {actual_days} days, expected {num_days}. Padding with fallback days.")
        elif actual_days > num_days:
            logger.warning(f"[Agent] LLM format has {actual_days} days, expected {num_days}. Truncating to {num_days}.")

        for i in range(num_days):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            weather = forecasts[i] if i < len(forecasts) else {}

            # Get day data from LLM response or use fallback
            llm_day = llm_itinerary[i] if i < actual_days else None

            # Normalize weather data
            weather_data = {}
            if has_weather and isinstance(weather, dict) and weather:
                temp_max = weather.get("temp_max") or weather.get("temp_day") or "25"
                temp_min = weather.get("temp_min") or weather.get("temp_night") or "15"
                condition = weather.get("condition") or weather.get("day_weather") or "晴"

                weather_data = {
                    "temp_max": str(temp_max),
                    "temp_min": str(temp_min),
                    "condition": str(condition)
                }
            else:
                # Weather not available
                weather_data = {
                    "temp_max": "--",
                    "temp_min": "--",
                    "condition": "暂无预报"
                }

            # Extract activities from LLM format
            activities = []
            theme = "探索之旅"

            if llm_day:
                theme = llm_day.get("theme", "探索之旅")
                for time_key, time_name in [("morning", "上午"), ("afternoon", "下午"), ("evening", "晚上")]:
                    if time_key in llm_day:
                        time_data = llm_day[time_key]
                        if isinstance(time_data, dict):
                            activity_name = time_data.get("activity", "").strip()
                            location_name = time_data.get("location", "").strip()

                            # Fallback: if activity is empty, use location
                            if not activity_name and location_name:
                                activity_name = location_name
                            if not activity_name:
                                activity_name = f"{time_name}活动"

                            activities.append({
                                "time": time_name,
                                "activity": activity_name,
                                "location": location_name,
                                "description": time_data.get("details", ""),
                                "duration": time_data.get("duration", "2-3小时"),
                                "cost": time_data.get("cost", "待定")
                            })

            # If no activities found (or fallback day), add defaults
            if not activities:
                activities = [
                    {"time": "上午", "activity": f"探索{destination}", "location": "市区", "description": "游览当地景点", "duration": "3小时", "cost": "待定"},
                    {"time": "下午", "activity": "品尝当地美食", "location": "特色餐厅", "description": "体验当地美食", "duration": "2小时", "cost": "约100元/人"},
                    {"time": "晚上", "activity": "夜游城市", "location": "商业区", "description": "欣赏夜景", "duration": "2小时", "cost": "待定"}
                ]

            days.append({
                "date": date,
                "theme": theme,
                "weather": weather_data,
                "activities": activities
            })

        return {
            "destination": destination,
            "overview": llm_data.get("overview", f"为您精心规划的{num_days}天{destination}之旅，涵盖当地精华景点与特色体验。"),
            "tips": llm_data.get("tips", [
                "建议提前预订热门景点门票",
                "关注天气变化，合理安排行程",
                "品尝当地特色美食，体验地道文化"
            ]),
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
            weather_info: Weather forecast data (may be empty if dates too far)
            start_date: Trip start date
            end_date: Trip end date

        Returns:
            Structured itinerary dict
        """
        # Fallback: Generate structured itinerary from text
        start = datetime.strptime(start_date, "%Y-%m-%d")
        days = []

        forecasts = []
        has_weather = False
        if isinstance(weather_info, dict) and "forecasts" in weather_info:
            forecasts = weather_info["forecasts"]
            if forecasts and len(forecasts) > 0:
                has_weather = True

        for i in range(num_days):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            weather = forecasts[i] if i < len(forecasts) else {}

            # Normalize weather data
            weather_data = {}
            if has_weather and isinstance(weather, dict) and weather:
                temp_max = weather.get("temp_max") or weather.get("temp_day") or "25"
                temp_min = weather.get("temp_min") or weather.get("temp_night") or "15"
                condition = weather.get("condition") or weather.get("day_weather") or "晴"

                weather_data = {
                    "temp_max": str(temp_max),
                    "temp_min": str(temp_min),
                    "condition": str(condition)
                }
            else:
                # Weather not available
                weather_data = {
                    "temp_max": "--",
                    "temp_min": "--",
                    "condition": "暂无预报"
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
            "overview": f"为您精心规划的{num_days}天{destination}之旅，涵盖当地精华景点与特色体验。",
            "tips": [
                "建议提前预订热门景点门票",
                "关注天气变化，合理安排行程",
                "品尝当地特色美食，体验地道文化"
            ],
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
