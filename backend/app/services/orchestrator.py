"""Master orchestrator for multi-agent coordination.

References:
- AI-02: Multi-agent collaboration architecture
- D-08, D-09: Master-Orchestrator pattern with task decomposition
- D-11: Structured message communication between agents
"""

import json
import logging
from typing import Optional

from app.agents.weather_agent import WeatherAgent
from app.agents.map_agent import MapAgent
from app.agents.itinerary_agent import ItineraryAgent
from app.services.memory_service import memory_service
from app.services.preference_service import preference_service
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


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

请根据用户的问题，调用合适的专家助手来获取信息，然后给出综合回答。
"""

        # Add user preferences (per PERS-02)
        if preferences:
            prompt += f"\n\n用户偏好：\n{json.dumps(preferences, ensure_ascii=False)}"

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
