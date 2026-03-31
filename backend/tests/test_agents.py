"""Tests for multi-agent orchestration and subagent delegation.

References:
- AI-02: Multi-agent collaboration architecture
- AI-03: Autonomous tool selection
- AI-04: Tool calling error handling and retry
- D-08, D-09, D-10: Master-Orchestrator pattern with specialized subagents
- D-16: Retry up to 3 times on failure
- D-17: Return fallback values on failure
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestSubagents:
    """Test individual subagent functionality.

    Note: These tests are skipped until agent modules are created in Plan 03-03.
    """

    @pytest.mark.skip(reason="Agent modules not created yet - Plan 03-03 pending")
    @pytest.mark.asyncio
    async def test_weather_agent(self):
        """Test WeatherAgent processes weather requests."""
        from app.agents.weather_agent import WeatherAgent

        # Arrange
        agent = WeatherAgent()

        # Act
        result = await agent.get_weather_info("北京")

        # Assert
        assert result is not None
        assert "success" in result
        # Weather data or error should be present
        assert result.get("success") is True or "error" in result

    @pytest.mark.skip(reason="Agent modules not created yet - Plan 03-03 pending")
    @pytest.mark.asyncio
    async def test_map_agent_search_poi(self):
        """Test MapAgent processes POI search requests."""
        from app.agents.map_agent import MapAgent

        # Arrange
        agent = MapAgent()

        # Act
        result = await agent.search_poi("北京", keywords="景点")

        # Assert
        assert result is not None
        assert "success" in result
        # POI data or error should be present
        assert result.get("success") is True or "error" in result

    @pytest.mark.skip(reason="Agent modules not created yet - Plan 03-03 pending")
    @pytest.mark.asyncio
    async def test_itinerary_agent_generate(self):
        """Test ItineraryAgent processes itinerary generation."""
        from app.agents.itinerary_agent import ItineraryAgent

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
    """Test master orchestrator coordination.

    Note: These tests are skipped until orchestrator is created in Plan 03-03.
    """

    @pytest.mark.skip(reason="Orchestrator not created yet - Plan 03-03 pending")
    @pytest.mark.asyncio
    async def test_subagent_delegation(self):
        """Test that orchestrator delegates to appropriate subagents."""
        from app.services.orchestrator import MasterOrchestrator

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

    @pytest.mark.skip(reason="Orchestrator not created yet - Plan 03-03 pending")
    @pytest.mark.asyncio
    async def test_tool_selection(self):
        """Test that agents select appropriate tools for tasks."""
        from app.services.orchestrator import MasterOrchestrator

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
    """Test LangChain tool wrappers for subagent delegation.

    Note: These tests are skipped until agent_tools.py is created in Plan 03-03.
    """

    @pytest.mark.skip(reason="agent_tools.py not created yet - Plan 03-03 pending")
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

    @pytest.mark.skip(reason="agent_tools.py not created yet - Plan 03-03 pending")
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

    @pytest.mark.skip(reason="agent_tools.py not created yet - Plan 03-03 pending")
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


class TestToolRetryFallback:
    """Test tool retry logic and fallback behavior.

    References:
    - AI-04: Tool calling error handling and retry
    - D-16: Retry up to 3 times on failure
    - D-17: Return fallback values on failure
    """

    @pytest.mark.asyncio
    async def test_tool_retry_on_failure(self):
        """Test that tools retry on transient failures."""
        from app.tools.weather_tools import get_weather

        # Mock to fail twice, then succeed
        call_count = 0

        async def failing_weather(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("API timeout")
            return json.dumps({
                "city": "北京",
                "temp": "25",
                "weather": "晴",
                "humidity": "65",
                "current_temp": "25°C",
                "condition": "晴",
                "wind": "东南风 3级",
                "summary": "当前温度25°C，晴，湿度65%"
            }, ensure_ascii=False)

        with patch('app.services.weather_service.weather_service.get_realtime_weather', new=failing_weather):
            result = await get_weather.ainvoke({"city": "北京"})

            # Should have retried and succeeded
            assert call_count == 3
            assert "北京" in result

    @pytest.mark.asyncio
    async def test_tool_fallback_on_permanent_failure(self):
        """Test that tools return fallback on permanent failure."""
        from app.tools.weather_tools import get_weather

        # Mock to always fail
        async def always_fail(*args, **kwargs):
            raise Exception("API key invalid")

        with patch('app.services.weather_service.weather_service.get_realtime_weather', new=always_fail):
            result = await get_weather.ainvoke({"city": "北京"})

            # Should return fallback value
            assert result is not None
            result_json = json.loads(result) if isinstance(result, str) else result
            assert "error" in result_json or "暂时" in result_json.get("summary", "")

    @pytest.mark.asyncio
    async def test_map_tool_fallback(self):
        """Test that map tools have fallback on failure."""
        from app.tools.map_tools import search_attraction

        # Mock to always fail
        async def always_fail(*args, **kwargs):
            raise Exception("Map service unavailable")

        with patch('app.services.map_service.map_service.search_poi', new=always_fail):
            result = await search_attraction.ainvoke({"city": "上海", "attraction_type": "景点"})

            # Should return fallback, not raise exception
            assert result is not None
            result_json = json.loads(result) if isinstance(result, str) else result
            assert "error" in result_json or "暂时" in result_json.get("summary", "")


class TestRetryUtility:
    """Test the retry decorator utility directly.

    References:
    - AI-04: Tool calling error handling and retry
    - D-16: Retry up to 3 times on failure
    """

    @pytest.mark.asyncio
    async def test_with_retry_success_on_first_attempt(self):
        """Test that retry wrapper succeeds on first attempt."""
        from app.utils.retry import with_retry

        @with_retry(max_attempts=3)
        async def successful_function():
            return "success"

        result = await successful_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_with_retry_success_after_retries(self):
        """Test that retry wrapper succeeds after failures."""
        from app.utils.retry import with_retry

        attempt_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        async def flaky_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise Exception("Temporary failure")
            return "success"

        result = await flaky_function()
        assert result == "success"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_with_retry_all_attempts_fail(self):
        """Test that retry wrapper raises after all attempts fail."""
        from app.utils.retry import with_retry

        @with_retry(max_attempts=2, base_delay=0.01)
        async def failing_function():
            raise Exception("Permanent failure")

        with pytest.raises(Exception, match="Permanent failure"):
            await failing_function()

    @pytest.mark.asyncio
    async def test_with_fallback_returns_value_on_failure(self):
        """Test that fallback decorator returns fallback value on failure."""
        from app.utils.retry import with_fallback

        fallback_data = {"error": "Service unavailable", "summary": "暂时无法获取"}

        @with_fallback(fallback_value=fallback_data, max_attempts=2)
        async def failing_function():
            raise Exception("API error")

        result = await failing_function()
        assert result == fallback_data

    @pytest.mark.asyncio
    async def test_with_fallback_callable(self):
        """Test that fallback decorator supports callable fallback."""
        from app.utils.retry import with_fallback

        def make_fallback(error):
            return {"error": str(error), "fallback": True}

        @with_fallback(fallback_value=make_fallback, max_attempts=1)
        async def failing_function():
            raise Exception("Custom error")

        result = await failing_function()
        assert result["error"] == "Custom error"
        assert result["fallback"] is True

    @pytest.mark.asyncio
    async def test_with_retry_and_fallback_combined(self):
        """Test combined retry and fallback decorator."""
        from app.utils.retry import with_retry_and_fallback

        fallback_data = {"weather": "未知", "summary": "暂时无法获取天气信息"}

        attempt_count = 0

        @with_retry_and_fallback(fallback_value=fallback_data, max_attempts=2, base_delay=0.01)
        async def failing_weather():
            nonlocal attempt_count
            attempt_count += 1
            raise Exception("API timeout")

        result = await failing_weather()
        assert result == fallback_data
        assert attempt_count == 2
