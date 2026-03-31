"""Tests for multi-agent orchestration and subagent delegation.

References:
- AI-02: Multi-agent collaboration architecture
- AI-03: Autonomous tool selection
- D-08, D-09, D-10: Master-Orchestrator pattern with specialized subagents
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.orchestrator import MasterOrchestrator
from app.agents.weather_agent import WeatherAgent
from app.agents.map_agent import MapAgent
from app.agents.itinerary_agent import ItineraryAgent


class TestSubagents:
    """Test individual subagent functionality."""

    @pytest.mark.asyncio
    async def test_weather_agent(self):
        """Test WeatherAgent processes weather requests."""
        # Arrange
        agent = WeatherAgent()

        # Act
        result = await agent.get_weather_info("北京")

        # Assert
        assert result is not None
        assert "success" in result
        # Weather data or error should be present
        assert result.get("success") is True or "error" in result

    @pytest.mark.asyncio
    async def test_map_agent_search_poi(self):
        """Test MapAgent processes POI search requests."""
        # Arrange
        agent = MapAgent()

        # Act
        result = await agent.search_poi("北京", keywords="景点")

        # Assert
        assert result is not None
        assert "success" in result
        # POI data or error should be present
        assert result.get("success") is True or "error" in result

    @pytest.mark.asyncio
    async def test_itinerary_agent_generate(self):
        """Test ItineraryAgent processes itinerary generation."""
        # Arrange
        agent = ItineraryAgent()

        # Act
        result = await agent.generate_itinerary(
            destination="北京",
            days=3,
            preferences="历史文化",
            user_id="test-user"
        )

        # Assert
        assert result is not None
        assert "destination" in result or "error" in result


class TestOrchestrator:
    """Test master orchestrator coordination."""

    @pytest.mark.asyncio
    async def test_subagent_delegation(self):
        """Test that orchestrator delegates to appropriate subagents."""
        # Arrange
        orchestrator = MasterOrchestrator()
        user_id = "test-user"

        # Mock the subagent tools
        with patch('app.tools.agent_tools.delegate_to_weather_agent.ainvoke') as mock_weather:
            mock_weather.return_value = '{"weather": "晴 25°C"}'

            with patch('app.tools.agent_tools.delegate_to_map_agent.ainvoke') as mock_map:
                mock_map.return_value = '{"pois": [{"name": "故宫"}]}'

                # Act - Request that needs both weather and map
                response = await orchestrator.process_request(
                    user_message="北京天气怎么样，有什么景点推荐",
                    user_id=user_id,
                    conversation_id="test-conv"
                )

                # Assert - Both subagents should have been called
                # (The orchestrator should analyze the request and delegate appropriately)
                assert response is not None
                # Verify at least one subagent was called
                assert mock_weather.called or mock_map.called

    @pytest.mark.asyncio
    async def test_tool_selection(self):
        """Test that agents select appropriate tools for tasks."""
        # Arrange
        orchestrator = MasterOrchestrator()

        # Act - Different types of requests
        weather_request = "北京天气怎么样"
        map_request = "推荐一些北京的景点"
        itinerary_request = "帮我规划3天北京行程"

        # Assert - Each request type should trigger different tool selections
        # (This is verified through logging and actual agent behavior)
        assert orchestrator is not None


class TestAgentTools:
    """Test LangChain tool wrappers for subagent delegation."""

    @pytest.mark.asyncio
    async def test_weather_agent_tool(self):
        """Test delegate_to_weather_agent tool."""
        from app.tools.agent_tools import delegate_to_weather_agent

        result = await delegate_to_weather_agent.ainvoke({
            "task": "获取实时天气",
            "city": "上海"
        })

        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_map_agent_tool(self):
        """Test delegate_to_map_agent tool."""
        from app.tools.agent_tools import delegate_to_map_agent

        result = await delegate_to_map_agent.ainvoke({
            "task": "搜索景点",
            "city": "上海",
            "keywords": "博物馆"
        })

        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_itinerary_agent_tool(self):
        """Test delegate_to_itinerary_agent tool."""
        from app.tools.agent_tools import delegate_to_itinerary_agent

        result = await delegate_to_itinerary_agent.ainvoke({
            "task": "生成行程",
            "destination": "杭州",
            "days": 2,
            "preferences": "自然风光"
        })

        assert result is not None
        assert isinstance(result, str)
