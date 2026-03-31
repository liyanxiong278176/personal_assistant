"""Master orchestrator for multi-agent coordination.

References:
- AI-02: Multi-agent collaboration architecture
- D-08, D-09: Master-Orchestrator pattern with task decomposition
- D-11: Structured message communication between agents
"""

import json
import logging
import re
from datetime import datetime, timedelta, date
from typing import Optional, Tuple

from app.agents.weather_agent import WeatherAgent
from app.agents.map_agent import MapAgent
from app.agents.itinerary_agent import ItineraryAgent
from app.services.memory_service import memory_service
from app.services.preference_service import preference_service
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


def parse_chinese_date(message: str, current_date: Optional[date] = None) -> Tuple[str, str, int]:
    """Parse Chinese date expressions from user message.

    Supports expressions like:
    - "五一" / "五一期间" / "劳动节" -> May 1, current year
    - "国庆" / "国庆节" -> October 1, current year
    - "3月15日" / "3.15" / "3-15" -> March 15, current year
    - "4月5号到4月10号" / "4月5日-4月10日" -> Date range
    - "下个月8号" / "下月8日" -> 8th of next month
    - "月底" / "月末" -> Last day of current month
    - "2026年5月2日" -> Full date with year
    - "周末" / "这个周末" -> upcoming Saturday-Sunday
    - "明天" / "后天" / "大后天"
    - "下周" / "下个月"

    Args:
        message: User message containing date expression
        current_date: Reference date (defaults to today)

    Returns:
        Tuple of (start_date, end_date, num_days) in YYYY-MM-DD format
    """
    if current_date is None:
        current_date = datetime.now().date()

    current_year = current_date.year

    # Priority 1: Try to extract explicit date patterns from message

    # Pattern 1: Full date with year - "2026年5月2日" / "2026-05-02"
    full_date_pattern = r'(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})[日号]?'
    match = re.search(full_date_pattern, message)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            start = date(year, month, day)
            start_date = start.strftime("%Y-%m-%d")
            logger.info(f"[DateParser] Parsed full date -> {start_date}")
            return start_date, start_date, 1
        except ValueError:
            pass  # Invalid date, continue

    # Pattern 2: Date range - "4月5日到4月10日" / "4.5-4.10" / "3月15号-3月20号"
    range_patterns = [
        r'(\d{1,2})[月\.](\d{1,2})[日号]\s*(?:到|至|-|—|~)\s*(\d{1,2})[月\.](\d{1,2})[日号]',
        r'(\d{1,2})[\/\-](\d{1,2})\s*(?:到|至|-|—|~)\s*(\d{1,2})[\/\-](\d{1,2})',
    ]
    for pattern in range_patterns:
        match = re.search(pattern, message)
        if match:
            try:
                m1, d1, m2, d2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
                start = date(current_year, m1, d1)
                end = date(current_year, m2, d2)
                # Handle year wrap-around (e.g., December to January)
                if end < start:
                    end = date(current_year + 1, m2, d2)
                start_date = start.strftime("%Y-%m-%d")
                end_date = end.strftime("%Y-%m-%d")
                num_days = (end - start).days + 1
                logger.info(f"[DateParser] Parsed date range -> {start_date} to {end_date} ({num_days} days)")
                return start_date, end_date, num_days
            except ValueError:
                pass

    # Pattern 3: Month and day - "3月15日" / "3.15" / "3-15"
    month_day_pattern = r'(\d{1,2})[月\.\-](\d{1,2})[日号](?!\s*(?:到|至|-|—|~))'
    match = re.search(month_day_pattern, message)
    if match:
        try:
            month, day = int(match.group(1)), int(match.group(2))
            # If this month has passed, use next year
            target = date(current_year, month, day)
            if target < current_date:
                target = date(current_year + 1, month, day)
            start_date = target.strftime("%Y-%m-%d")
            logger.info(f"[DateParser] Parsed month/day -> {start_date}")
            return start_date, start_date, 1
        except ValueError:
            pass

    # Pattern 4: "下个月8号" / "下月8日"
    next_month_pattern = r'下个?月[份]?(\d{1,2})[日号]'
    match = re.search(next_month_pattern, message)
    if match:
        try:
            day = int(match.group(1))
            if current_date.month == 12:
                next_month = date(current_date.year + 1, 1, day)
            else:
                next_month = date(current_date.year, current_date.month + 1, day)
            start_date = next_month.strftime("%Y-%m-%d")
            logger.info(f"[DateParser] Parsed next month day -> {start_date}")
            return start_date, start_date, 1
        except ValueError:
            pass

    # Pattern 5: "月底" / "月末" - last day of current month
    if "月底" in message or "月末" in message:
        if current_date.month == 12:
            last_day = date(current_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(current_date.year, current_date.month + 1, 1) - timedelta(days=1)
        start_date = last_day.strftime("%Y-%m-%d")
        logger.info(f"[DateParser] Parsed month end -> {start_date}")
        return start_date, start_date, 1

    # Pattern 6: "月初" / "月初" - first day of current/next month
    if "月初" in message:
        if "下个" in message or "下月" in message:
            if current_date.month == 12:
                first_day = date(current_date.year + 1, 1, 1)
            else:
                first_day = date(current_date.year, current_date.month + 1, 1)
        else:
            first_day = date(current_date.year, current_date.month, 1)
        start_date = first_day.strftime("%Y-%m-%d")
        logger.info(f"[DateParser] Parsed month start -> {start_date}")
        return start_date, start_date, 1

    # Pattern 7: "月中" - middle of month (15th)
    if "月中" in message:
        if "下个" in message or "下月" in message:
            if current_date.month == 12:
                mid_month = date(current_date.year + 1, 1, 15)
            else:
                mid_month = date(current_date.year, current_date.month + 1, 15)
        else:
            mid_month = date(current_date.year, current_date.month, 15)
        start_date = mid_month.strftime("%Y-%m-%d")
        logger.info(f"[DateParser] Parsed mid-month -> {start_date}")
        return start_date, start_date, 1

    # Priority 2: Holiday expressions (use current year)
    holidays = {
        "元旦": (1, 1, 1),
        "春节": (2, 17, 7),  # Approximate
        "清明": (4, 4, 3),
        "劳动节": (5, 1, 5),
        "五一": (5, 1, 5),
        "端午": (5, 31, 3),
        "中秋": (9, 25, 3),
        "国庆节": (10, 1, 7),
        "国庆": (10, 1, 7),
    }
    for holiday_name, (month, start_day, days_count) in holidays.items():
        if holiday_name in message:
            try:
                start = date(current_year, month, start_day)
                end = start + timedelta(days=days_count - 1)
                start_date = start.strftime("%Y-%m-%d")
                end_date = end.strftime("%Y-%m-%d")
                logger.info(f"[DateParser] Parsed holiday '{holiday_name}' -> {start_date} to {end_date}")
                return start_date, end_date, days_count
            except ValueError:
                pass  # Invalid date (e.g., Feb 30), continue

    # Priority 3: Relative date expressions
    # Check for "周末" (weekend)
    if "周末" in message or "週末" in message:
        days_until_saturday = (5 - current_date.weekday()) % 7
        if days_until_saturday == 0 and "这个周末" not in message and "本周末" not in message:
            days_until_saturday = 7
        if "下周末" in message or "下週末" in message:
            days_until_saturday += 7

        saturday = current_date + timedelta(days=days_until_saturday)
        sunday = saturday + timedelta(days=1)
        start_date = saturday.strftime("%Y-%m-%d")
        end_date = sunday.strftime("%Y-%m-%d")
        logger.info(f"[DateParser] Parsed weekend -> {start_date} to {end_date}")
        return start_date, end_date, 2

    # Check for weekday expressions like "本周五", "下周三"
    weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 0, "天": 0}
    weekday_pattern = r"(?:本|下)?[週周]([一二三四五六日天])"
    match = re.search(weekday_pattern, message)
    if match:
        weekday_char = match.group(1)
        target_weekday = weekday_map.get(weekday_char, 0)
        days_until = (target_weekday - current_date.weekday()) % 7
        if days_until == 0:
            days_until = 7
        if "下週" in message or "下周" in message:
            days_until += 7

        target_date = current_date + timedelta(days=days_until)
        start_date = target_date.strftime("%Y-%m-%d")
        logger.info(f"[DateParser] Parsed weekday -> {start_date}")
        return start_date, start_date, 1

    # Check for "明天", "后天", "大后天"
    day_offsets = {"大后天": 3, "后天": 2, "明天": 1}
    for expr, offset in day_offsets.items():
        if expr in message:
            target = current_date + timedelta(days=offset)
            start_date = target.strftime("%Y-%m-%d")
            logger.info(f"[DateParser] Parsed '{expr}' -> {start_date}")
            return start_date, start_date, 1

    # Check for "下周" (next week - Monday to Sunday)
    if "下周" in message and "周末" not in message and "週" not in message:
        next_monday = current_date + timedelta(days=(7 - current_date.weekday()))
        next_sunday = next_monday + timedelta(days=6)
        start_date = next_monday.strftime("%Y-%m-%d")
        end_date = next_sunday.strftime("%Y-%m-%d")
        logger.info(f"[DateParser] Parsed 'next week' -> {start_date} to {end_date}")
        return start_date, end_date, 7

    # Check for "下个月" (next month - use 1st to 7th as default 7-day trip)
    if "下个月" in message or "下月" in message:
        if current_date.month == 12:
            next_month = date(current_date.year + 1, 1, 1)
        else:
            next_month = date(current_date.year, current_date.month + 1, 1)
        # Use first week of next month
        start_date = next_month.strftime("%Y-%m-%d")
        end_date = (next_month + timedelta(days=6)).strftime("%Y-%m-%d")
        logger.info(f"[DateParser] Parsed 'next month' -> {start_date} to {end_date}")
        return start_date, end_date, 7

    # Default: return a date 7 days from now (3-day trip)
    default_start = current_date + timedelta(days=7)
    default_end = default_start + timedelta(days=2)
    logger.info(f"[DateParser] No date pattern found, using default (7 days from now)")
    return default_start.strftime("%Y-%m-%d"), default_end.strftime("%Y-%m-%d"), 3


def extract_trip_info(message: str) -> dict:
    """Extract trip information from user message.

    Parses destination, dates, and other trip details.

    Args:
        message: User message

    Returns:
        Dict with destination, start_date, end_date, num_days
    """
    info = {
        "destination": None,
        "start_date": None,
        "end_date": None,
        "num_days": None,
        "preferences": None
    }

    # Extract destination (city name pattern)
    # Match "去/到/在 [city] 旅游/玩/行程"
    dest_patterns = [
        r"(?:去|到|在)([^，。！？\s]{2,6}?)(?:旅游|玩|行程|玩玩|看看)",
        r"(?:去|到|在)([^，。！？\s]{2,6}?)的(?:行程|旅游)",
        r"([^，。！？\s]{2,6}?)(?:旅游|行程|攻略)",
    ]
    for pattern in dest_patterns:
        match = re.search(pattern, message)
        if match:
            info["destination"] = match.group(1).strip()
            logger.info(f"[TripParser] Extracted destination: {info['destination']}")
            break

    # If no destination found, try to find city names
    if not info["destination"]:
        common_cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "重庆", "南京", "苏州", "厦门", "青岛", "大连", "三亚", "桂林", "丽江", "拉萨", "乌鲁木齐"]
        for city in common_cities:
            if city in message:
                info["destination"] = city
                logger.info(f"[TripParser] Found city name: {city}")
                break

    # Parse dates
    start_date, end_date, num_days = parse_chinese_date(message)
    info["start_date"] = start_date
    info["end_date"] = end_date
    info["num_days"] = num_days

    return info


class MasterOrchestrator:
    """Main orchestrator that coordinates specialized subagents.

    Per D-09: Main agent decomposes and orchestrates tasks, doesn't call tools directly.
    Per D-11: Agents communicate through structured messages (tool delegation).
    """

    def __init__(self):
        """Initialize orchestrator with subagents."""
        # Initialize subagents (per D-10)
        self.weather_agent = WeatherAgent()
        self.map_agent = MapAgent()
        self.itinerary_agent = ItineraryAgent()

        # Tools available for LLM to call
        # Will be populated by agent_tools module
        self.tools = []

        self.logger = logging.getLogger("orchestrator")

    async def process_request(
        self,
        user_message: str,
        user_id: str,
        conversation_id: str
    ) -> str:
        """Process user request with multi-agent coordination.

        Args:
            user_message: User's message
            user_id: User identifier for preferences and memory
            conversation_id: Conversation identifier

        Returns:
            Response text
        """
        self.logger.info(f"[Orchestrator] Processing request for user={user_id}")

        # Step 1: Retrieve user preferences (per PERS-02)
        preferences = await preference_service.get_or_extract(user_id)

        # Step 2: Retrieve relevant conversation history (per AI-01)
        context_prompt = await memory_service.build_context_prompt(
            user_id=user_id,
            current_message=user_message,
            max_history=3
        )

        # Step 3: Build system prompt with context
        system_prompt = self._build_system_prompt(preferences, context_prompt)

        # Step 4: Process with LLM and tool calling
        response = await self._call_llm_with_tools(
            user_message=user_message,
            system_prompt=system_prompt,
            conversation_id=conversation_id
        )

        # Step 5: Store conversation in memory
        await memory_service.store_message(
            user_id=user_id,
            conversation_id=conversation_id,
            role="user",
            content=user_message
        )
        await memory_service.store_message(
            user_id=user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=response
        )

        return response

    def _build_system_prompt(self, preferences: dict, context: str) -> str:
        """Build context-aware system prompt.

        Args:
            preferences: User preferences
            context: Relevant conversation history

        Returns:
            System prompt string
        """
        prompt = """你是专业的旅游规划助手，可以协调多个专家助手为用户服务。

你可以调用以下专家助手：
1. 天气专家助手 - 获取和解读天气信息
2. 地图专家助手 - 搜索景点、规划路线
3. 行程规划助手 - 生成详细旅游行程

## 日期解析规则

当用户提到以下日期表达时，请自动识别为对应日期：
- "五一"/"劳动节"/"五一期间" → 2026年5月1日-5日
- "国庆"/"国庆节"/"国庆期间" → 2026年10月1日-7日
- "元旦" → 2026年1月1日
- "春节" → 2026年2月17日-23日
- "清明" → 2026年4月4日-6日
- "端午" → 2026年5月31日-6月2日
- "中秋" → 2026年9月25日-27日
- "周末"/"本周末" → 本周六日
- "下周末" → 下周六日
- "明天"/"后天"/"大后天" → 具体日期

## 天气预报限制说明

⚠️ 重要：大多数天气API只支持未来7-15天的预报。

如果用户询问的行程日期超过7天：
1. 明确告知用户"日期较远，暂无准确天气预报"
2. 建议用户"出发前1-3天再次查询天气"
3. 可以提供该季节的典型天气作为参考
4. 仍然可以规划行程（景点、美食等不受天气限制）

示例回复：
"您询问的五一假期（5月1日-5日）距离今天超过7天，天气预报API暂时无法提供准确数据。建议您4月28日左右再查询天气。不过我可以先为您规划行程，北京五一期间通常温度在15-25°C之间，适合旅游..."

请根据用户的问题，调用合适的专家助手来获取信息，然后给出综合回答。
"""

        # Add user preferences prominently (per PERS-02)
        if preferences:
            pref_lines = []
            if preferences.get('budget'):
                budget_map = {'low': '经济型', 'medium': '舒适型', 'high': '豪华型'}
                pref_lines.append(f"预算水平: {budget_map.get(preferences['budget'], preferences['budget'])}")
            if preferences.get('interests'):
                # Translate interest labels to Chinese
                interest_map = {
                    'history': '历史文化',
                    'food': '美食体验',
                    'nature': '自然风光',
                    'shopping': '购物',
                    'art': '艺术展览',
                    'entertainment': '娱乐休闲',
                    'sports': '户外运动',
                    'photography': '摄影打卡'
                }
                translated_interests = [interest_map.get(i, i) for i in preferences['interests']]
                pref_lines.append(f"兴趣偏好: {', '.join(translated_interests)}")
            if preferences.get('style'):
                style_map = {'relaxed': '悠闲放松', 'compact': '紧凑充实', 'adventure': '探索冒险'}
                pref_lines.append(f"旅行风格: {style_map.get(preferences['style'], preferences['style'])}")
            if preferences.get('travelers', 1) > 1:
                pref_lines.append(f"出行人数: {preferences['travelers']}人")

            if pref_lines:
                # 强化偏好指令 - 确保LLM优先考虑偏好
                prompt += """

## 重要：用户个性化偏好

你必须优先推荐符合以下偏好的内容：

"""
                prompt += "\n".join(f"- {p}" for p in pref_lines)
                prompt += """

请根据上述偏好进行推荐，例如：
- 如果用户喜欢"历史文化"，优先推荐博物馆、古迹、文化街区
- 如果用户偏好"悠闲放松"，避免推荐高强度徒步或紧凑行程
- 如果用户预算"经济型"，优先免费景点和经济实惠的选择
- 如果用户是多人出行，考虑适合团体的活动

在回复开头明确说明你如何考虑了这些偏好。
"""

        # Add conversation context (per AI-01)
        if context:
            prompt += f"\n\n{context}"

        return prompt

    async def _call_llm_with_tools(
        self,
        user_message: str,
        system_prompt: str,
        conversation_id: str
    ) -> str:
        """Call LLM with tool calling support.

        Args:
            user_message: User message
            system_prompt: System prompt with context
            conversation_id: Conversation ID

        Returns:
            LLM response
        """
        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        # For now, use direct streaming without function calling
        # (Full function calling can be added later with DashScope)
        full_response = ""
        async for chunk in llm_service.stream_chat(
            user_message=user_message,
            conversation_id=conversation_id
        ):
            full_response += chunk

        return full_response

    async def coordinate_itinerary_generation(
        self,
        destination: str,
        days: int,
        user_id: str,
        conversation_id: str
    ) -> dict:
        """Coordinate multi-agent itinerary generation.

        Demonstrates subagent collaboration:
        1. WeatherAgent gets weather forecast
        2. MapAgent searches for attractions
        3. ItineraryAgent generates itinerary with context

        Args:
            destination: Destination city
            days: Number of days
            user_id: User identifier
            conversation_id: Conversation identifier

        Returns:
            Generated itinerary
        """
        self.logger.info(f"[Orchestrator] Coordinating itinerary for {destination}")

        # Get user preferences
        preferences = await preference_service.get_or_extract(user_id)
        preferences_str = json.dumps(preferences, ensure_ascii=False)

        # Delegate to ItineraryAgent (which internally calls WeatherAgent and MapAgent)
        itinerary = await self.itinerary_agent.generate_itinerary(
            destination=destination,
            days=days,
            preferences=preferences_str,
            user_id=user_id
        )

        return itinerary


# Global orchestrator instance
orchestrator = MasterOrchestrator()
