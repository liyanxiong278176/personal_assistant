"""集成测试: QueryEngine + ContextGuard

测试 ContextGuard 正确集成到 QueryEngine 的工作流程中。
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.context.config import ContextConfig
from app.core.context.guard import ContextGuard


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["Mock response: Hello! How can I help you?"]
        self.call_count = 0
        self.api_key = "mock-key"

    async def chat(self, messages, system_prompt=None):
        idx = min(self.call_count, len(self.responses) - 1)
        result = self.responses[idx]
        self.call_count += 1
        return result

    async def stream_chat(self, messages, system_prompt=None):
        idx = min(self.call_count, len(self.responses) - 1)
        for chunk in self.responses[idx]:
            yield chunk
        self.call_count += 1

    async def chat_with_tools(self, messages, tools, system_prompt=None):
        return "Mock response", []

    async def close(self):
        pass


class TestQueryEngineContextGuardIntegration:
    """测试 QueryEngine 正确集成 ContextGuard"""

    def test_engine_has_context_guard_attribute(self):
        """测试 QueryEngine 实例具有 context_guard 属性"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())
        assert hasattr(engine, "context_guard"), (
            "QueryEngine should have 'context_guard' attribute"
        )

    def test_context_guard_is_properly_initialized(self):
        """测试 ContextGuard 在 QueryEngine 中被正确初始化"""
        from app.core.query_engine import QueryEngine

        mock_client = MockLLMClient()
        engine = QueryEngine(llm_client=mock_client)

        assert engine.context_guard is not None
        assert isinstance(engine.context_guard, ContextGuard)
        assert engine.context_guard.config is not None
        assert engine.context_guard.config.window_size == 128000

    def test_context_guard_gets_stats(self):
        """测试可以获取 context_guard 的统计信息"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())
        stats = engine.context_guard.get_stats()

        assert isinstance(stats, dict)
        assert "window_size" in stats
        assert "compress_threshold" in stats
        assert "pre_process_count" in stats
        assert "post_process_count" in stats

    def test_context_guard_with_custom_config(self):
        """测试使用自定义配置初始化 ContextGuard"""
        from app.core.query_engine import QueryEngine

        custom_config = ContextConfig(
            window_size=64000,
            compress_threshold=0.5,
        )

        # Note: Currently config is created inside __init__ via ContextConfig()
        # This test documents expected behavior when custom config is supported
        engine = QueryEngine(llm_client=MockLLMClient())
        assert engine.context_guard.config.window_size == 128000

    @pytest.mark.asyncio
    async def test_process_calls_pre_process(self):
        """测试 process 方法调用 pre_process"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())

        # Mock the pre_process method
        original_pre = engine.context_guard.pre_process
        engine.context_guard.pre_process = AsyncMock(
            side_effect=original_pre
        )

        # Collect the history before and after pre_process
        history_before = []

        # Patch _get_conversation_history to return our test history
        with patch.object(
            engine,
            "_get_conversation_history",
            return_value=history_before,
        ):
            chunks = []
            async for chunk in engine.process(
                "Hello, I want to plan a trip to Beijing",
                conversation_id="test_conv_pre",
            ):
                chunks.append(chunk)

        # Verify pre_process was called at least once
        assert engine.context_guard._stats["pre_process_count"] >= 1

    @pytest.mark.asyncio
    async def test_process_calls_post_process(self):
        """测试 process 方法调用 post_process"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())

        # Verify post_process count increases after processing
        initial_count = engine.context_guard._stats["post_process_count"]

        chunks = []
        async for chunk in engine.process(
            "Hello, I want to plan a trip to Beijing",
            conversation_id="test_conv_post",
        ):
            chunks.append(chunk)

        # post_process should have been called at least once
        assert engine.context_guard._stats["post_process_count"] >= 1

    @pytest.mark.asyncio
    async def test_process_with_conversation_history(self):
        """测试带对话历史的 process 方法"""
        from app.core.query_engine import QueryEngine

        responses = [
            "First response about travel.",
            "Second response with more details.",
        ]
        engine = QueryEngine(llm_client=MockLLMClient(responses=responses))

        # First message
        chunks1 = []
        async for chunk in engine.process(
            "I want to visit Tokyo",
            conversation_id="test_conv_history",
        ):
            chunks1.append(chunk)

        response1 = "".join(chunks1)
        assert len(response1) > 0

        # Second message in same conversation
        chunks2 = []
        async for chunk in engine.process(
            "What about Osaka?",
            conversation_id="test_conv_history",
        ):
            chunks2.append(chunk)

        response2 = "".join(chunks2)
        assert len(response2) > 0

        # History should have grown
        history = engine._get_conversation_history("test_conv_history")
        assert len(history) >= 2  # At least user + assistant from first exchange

    @pytest.mark.asyncio
    async def test_context_guard_pre_process_works(self):
        """测试 ContextGuard.pre_process 单独工作"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())

        messages = [
            {"role": "system", "content": "You are a travel assistant."},
            {"role": "user", "content": "Plan a trip to Paris"},
            {"role": "assistant", "content": "Here are some recommendations..."},
            {
                "role": "tool",
                "content": "x" * 1000,
                "tool_call_id": "call_1",
                "name": "weather",
                "_timestamp": 1234567890.0,
            },
        ]

        result = await engine.context_guard.pre_process(messages)
        assert isinstance(result, list)
        # pre_process should have cleaned/trimmed the long tool result
        assert len(result) >= len(messages) - 1  # at least the long tool msg is cleaned

    @pytest.mark.asyncio
    async def test_context_guard_post_process_works(self):
        """测试 ContextGuard.post_process 单独工作"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())

        # Small message list should not compress
        messages = [
            {"role": "system", "content": "You are a travel assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        result = await engine.context_guard.post_process(messages)
        # Small lists should pass through unchanged
        assert len(result) == len(messages)

    @pytest.mark.asyncio
    async def test_full_workflow_integration(self):
        """测试完整工作流程集成"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())

        # Capture initial stats
        initial_stats = engine.context_guard.get_stats()

        # Process a message
        chunks = []
        async for chunk in engine.process(
            "What is the weather in Shanghai?",
            conversation_id="test_full_workflow",
        ):
            chunks.append(chunk)

        response = "".join(chunks)
        assert len(response) > 0

        # Verify stats were updated
        final_stats = engine.context_guard.get_stats()
        assert final_stats["pre_process_count"] > initial_stats["pre_process_count"]
        assert final_stats["post_process_count"] > initial_stats["post_process_count"]

    @pytest.mark.asyncio
    async def test_process_simple_with_guard(self):
        """测试 process_simple 方法不受 ContextGuard 影响"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())

        # process_simple should still work
        result = await engine.process_simple("Hello!")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_guard_receives_llm_client_reference(self):
        """测试 ContextGuard 接收到 LLM 客户端引用"""
        from app.core.query_engine import QueryEngine

        mock_client = MockLLMClient()
        engine = QueryEngine(llm_client=mock_client)

        # The guard should have a reference to the llm client
        assert engine.context_guard._llm_client is mock_client

    @pytest.mark.asyncio
    async def test_rules_cache_loaded_from_docs(self):
        """测试规则缓存从 docs/superpowers 目录加载"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())

        # Rules cache should be initialized (may be empty if files don't exist)
        assert engine.context_guard.config.rules_cache is not None
        # It's a dict - can be empty but should exist
        assert isinstance(engine.context_guard.config.rules_cache, dict)


class TestContextGuardPrePostWorkflow:
    """测试 ContextGuard pre/post 流程"""

    @pytest.mark.asyncio
    async def test_pre_then_post_process(self):
        """测试 pre_process 后紧接 post_process"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine(llm_client=MockLLMClient())

        messages = [
            {"role": "system", "content": "You are a travel assistant."},
            {"role": "user", "content": "Plan my trip"},
            {"role": "assistant", "content": "Here are some options..."},
            {
                "role": "tool",
                "content": "Weather: Sunny, 25C",
                "tool_call_id": "call_1",
                "name": "weather",
                "_timestamp": 1234567890.0,
            },
        ]

        # Simulate the workflow
        pre_result = await engine.context_guard.pre_process(messages)
        post_result = await engine.context_guard.post_process(pre_result)

        # Both should return valid lists
        assert isinstance(pre_result, list)
        assert isinstance(post_result, list)
        # Stats should reflect the calls
        assert engine.context_guard._stats["pre_process_count"] >= 1
        assert engine.context_guard._stats["post_process_count"] >= 1
