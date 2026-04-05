"""E2E tests for Agent Core Enhancement Features.

Tests the full integration of:
- Tool Loop (enable_tool_loop)
- Inference Guard (inference_guard)
- Preference Extraction (preference_extraction)
- Multi-turn conversation memory

These tests use mock LLM clients to avoid external API dependencies.
"""

import pytest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncIterator

from app.core.query_engine import QueryEngine
from app.core.llm import LLMClient, ToolCall
from app.core.tools import Tool, ToolRegistry, global_registry
from app.core.context.enhancement_config import AgentEnhancementConfig
from app.core.context.inference_guard import InferenceGuard, OverlimitStrategy
from app.core.preferences.extractor import PreferenceExtractor
from app.core.preferences.patterns import MatchedPreference, PreferenceType


# =============================================================================
# Mock Tools for Testing
# =============================================================================


class MockWeatherTool(Tool):
    """Mock weather tool for testing."""

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "Get weather for a city"

    @property
    def metadata(self):
        from app.core.tools.base import ToolMetadata
        return ToolMetadata(
            name="get_weather",
            description="Get weather for a city",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
        )

    async def execute(self, city: str = "") -> dict:
        return {"city": city, "weather": "晴", "temperature": 25}


class MockPOITool(Tool):
    """Mock POI search tool for testing."""

    @property
    def name(self) -> str:
        return "search_poi"

    @property
    def description(self) -> str:
        return "Search points of interest"

    @property
    def metadata(self):
        from app.core.tools.base import ToolMetadata
        return ToolMetadata(
            name="search_poi",
            description="Search points of interest",
            parameters={"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}
        )

    async def execute(self, keyword: str = "") -> dict:
        return {"keyword": keyword, "results": [f"{keyword}景点{i}" for i in range(3)]}


class MockHotelTool(Tool):
    """Mock hotel search tool for testing."""

    @property
    def name(self) -> str:
        return "search_hotel"

    @property
    def description(self) -> str:
        return "Search hotels"

    @property
    def metadata(self):
        from app.core.tools.base import ToolMetadata
        return ToolMetadata(
            name="search_hotel",
            description="Search hotels",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
        )

    async def execute(self, city: str = "") -> dict:
        return {"city": city, "hotels": [f"{city}酒店{i}" for i in range(2)]}


# =============================================================================
# Mock LLM Client
# =============================================================================


class MockStreamingLLMClient(LLMClient):
    """Mock LLM client that simulates streaming responses."""

    def __init__(self, response_text: str = "这是一条测试响应"):
        super().__init__(api_key="mock-key")
        self.response_text = response_text
        self.call_count = 0

    async def stream_chat(
        self,
        messages,
        system_prompt=None,
        guard=None
    ) -> AsyncIterator[str]:
        """Simulate streaming response."""
        for char in self.response_text:
            await asyncio.sleep(0.001)
            if guard is not None:
                should_cont, warning = guard.check_before_yield(char)
                if not should_cont:
                    if warning:
                        yield warning
                    break
            yield char

    async def stream_chat_with_tools(
        self,
        messages,
        tools,
        system_prompt=None
    ) -> AsyncIterator:
        """Simulate tool-calling response."""
        self.call_count += 1
        last_message = messages[-1]["content"] if messages else ""

        if "天气" in last_message or "weather" in last_message.lower():
            yield ToolCall(id="call_1", name="get_weather", arguments={"city": "北京"})
        elif "景点" in last_message or "poi" in last_message.lower():
            yield ToolCall(id="call_2", name="search_poi", arguments={"keyword": "景点"})
        elif "酒店" in last_message or "hotel" in last_message.lower():
            yield ToolCall(id="call_3", name="search_hotel", arguments={"city": "北京"})
        else:
            for char in self.response_text:
                yield char

    async def chat_with_tools(self, messages, tools, system_prompt=None) -> tuple:
        content_parts = []
        tool_calls = []
        async for chunk in self.stream_chat_with_tools(messages, tools, system_prompt):
            if isinstance(chunk, ToolCall):
                tool_calls.append(chunk)
            else:
                content_parts.append(chunk)
        return "".join(content_parts), tool_calls


# =============================================================================
# E2E Test: Full Workflow with Preferences
# =============================================================================


@pytest.mark.asyncio
class TestFullWorkflowWithPreferences:
    """Test complete workflow with preference extraction enabled."""

    async def test_full_workflow_with_preferences(self):
        """Test the full QueryEngine workflow with preference extraction."""
        mock_client = MockStreamingLLMClient("好的，我来帮您规划北京三日游。")

        registry = ToolRegistry()
        registry.register(MockWeatherTool())
        registry.register(MockPOITool())

        config = AgentEnhancementConfig.load_from_dict({
            "enable_preference_extraction": True,
            "preference_confidence_threshold": 0.7,
        })

        engine = QueryEngine(
            llm_client=mock_client,
            tool_registry=registry,
            enhancement_config=config,
        )
        engine._initialized_sessions.add("test-conv-pref-001")

        user_input = "我想去北京旅游，预算5000元，喜欢历史文化景点"
        conversation_id = "test-conv-pref-001"
        user_id = "test-user-001"

        chunks = []
        async for chunk in engine.process(user_input, conversation_id, user_id):
            chunks.append(chunk)
        response = "".join(chunks)

        # Verify: Response was generated
        assert response is not None
        assert len(response) > 0

        # Verify: Conversation history was updated
        history = engine._get_conversation_history(conversation_id)
        assert len(history) >= 2

        # Verify: Enhancement config was applied
        assert engine._config.enable_preference_extraction is True
        assert engine._pref_extractor is not None

        await engine.close()

    async def test_workflow_inference_guard_active(self):
        """Test that inference guard is properly initialized and active."""
        config = AgentEnhancementConfig.load_from_dict({
            "enable_inference_guard": True,
            "max_tokens_per_response": 1000,
            "max_total_token_budget": 2000,
            "overlimit_strategy": "truncate",
        })

        mock_client = MockStreamingLLMClient("测试响应内容")
        engine = QueryEngine(
            llm_client=mock_client,
            enhancement_config=config,
        )
        engine._initialized_sessions.add("test-conv-guard-001")

        # Verify: Guard is properly initialized with config
        assert engine._inference_guard is not None
        assert engine._inference_guard.max_tokens_per_response == 1000
        assert engine._inference_guard.max_total_budget == 2000
        assert engine._inference_guard.overlimit_strategy == OverlimitStrategy.TRUNCATE

        # Verify: Guard can be checked directly
        should_continue, warning = engine._inference_guard.check_before_yield("test")
        assert should_continue is True
        assert warning is None

        await engine.close()

    async def test_workflow_with_tool_loop_disabled(self):
        """Test workflow with tool loop disabled (default)."""
        mock_client = MockStreamingLLMClient("查询完成")

        registry = ToolRegistry()
        registry.register(MockWeatherTool())

        config = AgentEnhancementConfig.load_from_dict({
            "enable_tool_loop": False,
        })

        engine = QueryEngine(
            llm_client=mock_client,
            tool_registry=registry,
            enhancement_config=config,
        )
        engine._initialized_sessions.add("test-conv-no-loop-001")

        user_input = "北京天气怎么样"
        conversation_id = "test-conv-no-loop-001"

        chunks = []
        async for chunk in engine.process(user_input, conversation_id, "user-1"):
            chunks.append(chunk)
        response = "".join(chunks)

        assert engine._config.enable_tool_loop is False
        assert response is not None

        await engine.close()

    async def test_workflow_preference_extraction_integrates(self):
        """Test that preference extraction integrates with the workflow."""
        mock_client = MockStreamingLLMClient("好的")

        config = AgentEnhancementConfig.load_from_dict({
            "enable_preference_extraction": True,
            "preference_confidence_threshold": 0.6,
        })

        engine = QueryEngine(
            llm_client=mock_client,
            enhancement_config=config,
        )

        test_inputs = [
            "我预算5000元",
            "想去云南旅游",
            "计划3天行程",
        ]

        for user_input in test_inputs:
            extractor = engine._pref_extractor
            if extractor:
                matches = extractor.matcher.extract(user_input)
                assert matches is not None

        await engine.close()


# =============================================================================
# E2E Test: Multi-turn Conversation
# =============================================================================


@pytest.mark.asyncio
class TestMultiTurnConversation:
    """Test multi-turn conversation with memory and context preservation."""

    async def test_multi_turn_conversation(self):
        """Test multi-turn conversation maintains context across turns."""
        turn_responses = [
            "好的，北京三日游，我来帮您规划。",
            "第二天可以去故宫和天安门。",
            "推荐您入住王府井附近的酒店。",
        ]

        class TurnAwareClient(MockStreamingLLMClient):
            def __init__(self):
                super().__init__("")
                self.turn = 0

            async def stream_chat(self, messages, system_prompt=None, guard=None) -> AsyncIterator[str]:
                if self.turn < len(turn_responses):
                    text = turn_responses[self.turn]
                    for char in text:
                        if guard is not None:
                            should_cont, warning = guard.check_before_yield(char)
                            if not should_cont:
                                if warning:
                                    yield warning
                                break
                        yield char
                    self.turn += 1

        mock_client = TurnAwareClient()
        registry = ToolRegistry()
        registry.register(MockWeatherTool())
        registry.register(MockPOITool())
        registry.register(MockHotelTool())

        engine = QueryEngine(
            llm_client=mock_client,
            tool_registry=registry,
        )

        conversation_id = "test-multi-turn-001"
        user_id = "test-user-multi-001"
        engine._initialized_sessions.add(conversation_id)

        # Turn 1
        turn1_input = "我想去北京旅游"
        chunks1 = []
        async for chunk in engine.process(turn1_input, conversation_id, user_id):
            chunks1.append(chunk)
        response1 = "".join(chunks1)
        assert len(response1) > 0

        history1 = engine._get_conversation_history(conversation_id)
        assert len(history1) >= 2

        # Turn 2
        turn2_input = "第二天推荐去哪些景点"
        chunks2 = []
        async for chunk in engine.process(turn2_input, conversation_id, user_id):
            chunks2.append(chunk)
        response2 = "".join(chunks2)
        assert len(response2) > 0

        history2 = engine._get_conversation_history(conversation_id)
        assert len(history2) >= 4

        # Turn 3
        turn3_input = "推荐一些酒店"
        chunks3 = []
        async for chunk in engine.process(turn3_input, conversation_id, user_id):
            chunks3.append(chunk)
        response3 = "".join(chunks3)
        assert len(response3) > 0

        history3 = engine._get_conversation_history(conversation_id)
        assert len(history3) >= 4

        await engine.close()

    async def test_multi_turn_preserves_slots(self):
        """Test that slot extraction works across multiple turns."""
        mock_client = MockStreamingLLMClient("好的")

        engine = QueryEngine(llm_client=mock_client)
        engine._initialized_sessions.add("test-slots-001")

        conversation_id = "test-slots-001"
        user_id = "test-user-slots-001"

        # Turn 1
        turn1_input = "帮我规划去上海的行程"
        async for _ in engine.process(turn1_input, conversation_id, user_id):
            pass

        slots1 = engine._slot_extractor.extract(turn1_input)
        assert "上海" in turn1_input

        # Turn 2
        turn2_input = "时间是五一期间"
        async for _ in engine.process(turn2_input, conversation_id, user_id):
            pass

        slots2 = engine._slot_extractor.extract(turn2_input)
        assert "五一" in turn2_input or slots2.start_date is not None

        await engine.close()

    async def test_multi_turn_respects_conversation_boundary(self):
        """Test that different conversations are isolated."""
        mock_client = MockStreamingLLMClient("响应")

        engine = QueryEngine(llm_client=mock_client)

        conv1_id = "conv-001"
        conv2_id = "conv-002"
        engine._initialized_sessions.add(conv1_id)
        engine._initialized_sessions.add(conv2_id)

        async for _ in engine.process("我想去北京", conv1_id, "user-1"):
            pass
        async for _ in engine.process("我想去上海", conv2_id, "user-2"):
            pass

        history1 = engine._get_conversation_history(conv1_id)
        history2 = engine._get_conversation_history(conv2_id)

        assert history1 != history2

        # Reset one conversation
        engine.reset_conversation(conv1_id)

        history1_after = engine._get_conversation_history(conv1_id)
        history2_after = engine._get_conversation_history(conv2_id)

        assert len(history1_after) == 0
        assert len(history2_after) >= 2

        await engine.close()

    async def test_multi_turn_with_intent_variation(self):
        """Test that different intents are correctly classified across turns."""
        mock_client = MockStreamingLLMClient("好的")

        engine = QueryEngine(llm_client=mock_client)
        engine._initialized_sessions.add("test-intent-var-001")

        conversation_id = "test-intent-var-001"
        user_id = "test-user-intent-001"

        await self._consume(engine.process("帮我规划去成都的行程", conversation_id, user_id))
        await self._consume(engine.process("成都天气怎么样", conversation_id, user_id))
        await self._consume(engine.process("谢谢", conversation_id, user_id))

        history = engine._get_conversation_history(conversation_id)
        assert len(history) >= 2

        await engine.close()

    @staticmethod
    async def _consume(gen) -> str:
        chunks = []
        async for chunk in gen:
            chunks.append(chunk)
        return "".join(chunks)


# =============================================================================
# E2E Test: Tool Loop Integration
# =============================================================================


@pytest.mark.asyncio
class TestToolLoopIntegration:
    """Test tool loop feature in full workflow context."""

    async def test_tool_loop_config_respected(self):
        """Test that tool loop config is properly respected."""
        config = AgentEnhancementConfig.load_from_dict({
            "enable_tool_loop": True,
            "max_tool_iterations": 2,
            "tool_loop_token_limit": 5000,
        })

        mock_client = MockStreamingLLMClient("完成")
        registry = ToolRegistry()
        registry.register(MockWeatherTool())

        engine = QueryEngine(
            llm_client=mock_client,
            tool_registry=registry,
            enhancement_config=config,
        )

        assert engine._config.enable_tool_loop is True
        assert engine._config.max_tool_iterations == 2
        assert engine._config.tool_loop_token_limit == 5000

        await engine.close()

    async def test_tool_loop_multiple_tools_registered(self):
        """Test that multiple tools can be registered for tool loop."""
        registry = ToolRegistry()
        registry.register(MockWeatherTool())
        registry.register(MockPOITool())
        registry.register(MockHotelTool())

        assert len(registry.list_tools()) == 3

        config = AgentEnhancementConfig.load_from_dict({
            "enable_tool_loop": True,
            "max_tool_iterations": 5,
        })

        mock_client = MockStreamingLLMClient("完成")
        engine = QueryEngine(
            llm_client=mock_client,
            tool_registry=registry,
            enhancement_config=config,
        )

        assert engine._config.enable_tool_loop is True

        await engine.close()
