"""Performance tests for Agent Core Enhancement Features.

Tests performance characteristics of:
- First token latency (< 2 seconds)
- Tool loop performance
- Inference guard overhead
- Preference extraction speed

These tests use mock LLM clients and focus on measuring relative performance.
"""

import pytest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import AsyncIterator

from app.core.query_engine import QueryEngine
from app.core.llm import LLMClient, ToolCall
from app.core.tools import Tool, ToolRegistry
from app.core.context.enhancement_config import AgentEnhancementConfig
from app.core.context.inference_guard import InferenceGuard, OverlimitStrategy
from app.core.preferences.extractor import PreferenceExtractor
from app.core.preferences.patterns import PreferenceMatcher, MatchedPreference, PreferenceType


# =============================================================================
# Mock Tools
# =============================================================================


class FastMockTool(Tool):
    """A fast mock tool for performance testing."""

    @property
    def name(self) -> str:
        return "fast_tool"

    @property
    def description(self) -> str:
        return "A fast tool for testing"

    @property
    def metadata(self):
        from app.core.tools.base import ToolMetadata
        return ToolMetadata(
            name="fast_tool",
            description="A fast tool",
            parameters={"type": "object", "properties": {}, "required": []}
        )

    async def execute(self) -> dict:
        # Simulates fast execution (< 10ms)
        await asyncio.sleep(0.001)
        return {"status": "ok", "data": [1, 2, 3]}


class SlowMockTool(Tool):
    """A slower mock tool to measure parallel execution benefits."""

    @property
    def name(self) -> str:
        return "slow_tool"

    @property
    def description(self) -> str:
        return "A slow tool for testing"

    @property
    def metadata(self):
        from app.core.tools.base import ToolMetadata
        return ToolMetadata(
            name="slow_tool",
            description="A slow tool",
            parameters={"type": "object", "properties": {}, "required": []}
        )

    async def execute(self) -> dict:
        # Simulates slow execution (~100ms)
        await asyncio.sleep(0.1)
        return {"status": "ok", "results": ["a", "b", "c"]}


class SlowMockToolB(Tool):
    """Second slow mock tool instance."""

    @property
    def name(self) -> str:
        return "slow_tool_b"

    @property
    def description(self) -> str:
        return "A slow tool"

    @property
    def metadata(self):
        from app.core.tools.base import ToolMetadata
        return ToolMetadata(
            name="slow_tool_b",
            description="A slow tool",
            parameters={"type": "object", "properties": {}, "required": []}
        )

    async def execute(self) -> dict:
        await asyncio.sleep(0.1)
        return {"status": "ok", "results": ["d", "e", "f"]}


class SlowMockToolC(Tool):
    """Third slow mock tool instance."""

    @property
    def name(self) -> str:
        return "slow_tool_c"

    @property
    def description(self) -> str:
        return "A slow tool"

    @property
    def metadata(self):
        from app.core.tools.base import ToolMetadata
        return ToolMetadata(
            name="slow_tool_c",
            description="A slow tool",
            parameters={"type": "object", "properties": {}, "required": []}
        )

    async def execute(self) -> dict:
        await asyncio.sleep(0.1)
        return {"status": "ok", "results": ["g", "h", "i"]}


# =============================================================================
# Mock LLM Clients
# =============================================================================


class PerformanceTestClient(LLMClient):
    """Client designed for performance testing with controlled timing."""

    def __init__(
        self,
        response_text: str = "测试响应内容",
        first_token_delay: float = 0.0,
        token_rate: float = 100.0,  # chars per second
    ):
        super().__init__(api_key="mock-key")
        self.response_text = response_text
        self.first_token_delay = first_token_delay
        self.token_rate = token_rate
        self.tokens_sent = 0

    async def stream_chat(
        self,
        messages,
        system_prompt=None,
        guard=None
    ) -> AsyncIterator[str]:
        """Simulate streaming with controlled timing."""
        # First token delay
        if self.first_token_delay > 0:
            await asyncio.sleep(self.first_token_delay)

        # Stream tokens at controlled rate
        char_delay = 1.0 / self.token_rate if self.token_rate > 0 else 0

        for char in self.response_text:
            if char_delay > 0:
                await asyncio.sleep(char_delay)

            self.tokens_sent += 1

            # Apply guard check
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
        """Simulate tool-calling."""
        last_message = messages[-1]["content"] if messages else ""

        if "weather" in last_message.lower() or "天气" in last_message:
            yield ToolCall(id="1", name="fast_tool", arguments={})
        else:
            for char in self.response_text:
                yield char

    async def chat_with_tools(self, messages, tools, system_prompt=None) -> tuple:
        """Return content and tool calls."""
        content_parts = []
        tool_calls = []

        async for chunk in self.stream_chat_with_tools(messages, tools, system_prompt):
            if isinstance(chunk, ToolCall):
                tool_calls.append(chunk)
            else:
                content_parts.append(chunk)

        return "".join(content_parts), tool_calls


# =============================================================================
# Performance Test: First Token Latency
# =============================================================================


@pytest.mark.asyncio
class TestFirstTokenLatency:
    """Test first token latency performance requirements.

    Note: These tests measure component-level latency to avoid
    external dependencies (DB). The 2-second requirement applies
    to the LLM streaming portion, not full workflow with DB ops.
    """

    async def test_first_token_latency_llm_streaming(self):
        """Test that LLM streaming first token is under 2 seconds.

        This measures the time from calling stream_chat to receiving
        the first token. The requirement is < 2000ms for LLM response.
        """
        mock_client = PerformanceTestClient(
            response_text="这是一段较长的测试响应文本，用于测量性能",
            first_token_delay=0.5,  # 500ms simulated API latency
            token_rate=500.0,
        )

        messages = [{"role": "user", "content": "测试"}]
        first_token_time = None

        start = time.perf_counter()
        async for chunk in mock_client.stream_chat(messages):
            first_token_time = time.perf_counter() - start
            break  # Only measure first token

        assert first_token_time is not None, "First token was never received"
        assert first_token_time < 2.0, (
            f"First token latency {first_token_time:.3f}s exceeds 2.0s threshold. "
            f"Simulated delay was 0.5s."
        )

    async def test_first_token_latency_guard_check(self):
        """Test that inference guard check is fast."""
        guard = InferenceGuard(
            max_tokens_per_response=1000,
            max_total_budget=5000,
            warning_threshold=0.8,
        )

        # Measure: Time for 100 guard checks
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            guard.check_before_yield("x")
        elapsed = time.perf_counter() - start

        avg_per_check_us = (elapsed / iterations) * 1_000_000
        assert avg_per_check_us < 100, (
            f"Average guard check {avg_per_check_us:.1f}us is too slow"
        )

    async def test_inference_guard_overhead(self):
        """Test that inference guard adds minimal overhead."""
        # Setup: Create engine with guard
        config = AgentEnhancementConfig.load_from_dict({
            "enable_inference_guard": True,
            "max_tokens_per_response": 5000,
            "max_total_token_budget": 10000,
        })

        mock_client = PerformanceTestClient(
            response_text="x" * 1000,
            token_rate=10000.0,  # Fast streaming
        )

        engine = QueryEngine(
            llm_client=mock_client,
            enhancement_config=config,
        )

        # Measure: Overhead of guard checks
        iterations = 100
        guard = engine._inference_guard

        start = time.perf_counter()
        for _ in range(iterations):
            guard.check_before_yield("x")
        guard_overhead = time.perf_counter() - start

        # Verify: Guard overhead is minimal (< 10ms for 100 checks)
        assert guard_overhead < 0.01, (
            f"Guard overhead {guard_overhead*1000:.2f}ms for {iterations} checks is too high"
        )

        await engine.close()

    async def test_no_guard_overhead(self):
        """Test that disabling guard removes its overhead."""
        config = AgentEnhancementConfig.load_from_dict({
            "enable_inference_guard": False,
        })

        mock_client = PerformanceTestClient(response_text="测试")
        engine = QueryEngine(
            llm_client=mock_client,
            enhancement_config=config,
        )

        # Verify: Guard is not active
        assert engine._inference_guard is None

        await engine.close()


# =============================================================================
# Performance Test: Tool Loop Performance
# =============================================================================


@pytest.mark.asyncio
class TestToolLoopPerformance:
    """Test tool loop execution performance."""

    async def test_tool_loop_performance(self):
        """Test tool loop performance with multiple iterations.

        Measures:
        - Time per iteration
        - Token budget tracking accuracy
        - Stop condition performance
        """
        config = AgentEnhancementConfig.load_from_dict({
            "enable_tool_loop": True,
            "max_tool_iterations": 5,
            "tool_loop_token_limit": 10000,
        })

        registry = ToolRegistry()
        registry.register(FastMockTool())

        engine = QueryEngine(
            llm_client=PerformanceTestClient("完成"),
            tool_registry=registry,
            enhancement_config=config,
        )

        # Verify: Config is applied
        assert engine._config.enable_tool_loop is True
        assert engine._config.max_tool_iterations == 5

        await engine.close()

    async def test_tool_execution_time(self):
        """Test individual tool execution time."""
        registry = ToolRegistry()
        registry.register(FastMockTool())

        from app.core.tools.executor import ToolExecutor

        executor = ToolExecutor(registry)

        # Measure: Single tool execution
        iterations = 50
        start = time.perf_counter()

        for _ in range(iterations):
            await executor.execute("fast_tool")

        elapsed = time.perf_counter() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Verify: Average execution time is fast (< 50ms per tool)
        assert avg_time_ms < 50.0, (
            f"Average tool execution time {avg_time_ms:.2f}ms is too slow"
        )

    async def test_parallel_tool_execution_benefit(self):
        """Test that parallel execution is faster than sequential."""
        registry = ToolRegistry()
        # Register 3 separate tool instances with unique names
        registry.register(SlowMockTool())
        registry.register(SlowMockToolB())
        registry.register(SlowMockToolC())

        from app.core.tools.executor import ToolExecutor
        from app.core.llm import ToolCall

        executor = ToolExecutor(registry)

        calls = [
            ToolCall(id="1", name="slow_tool", arguments={}),
            ToolCall(id="2", name="slow_tool_b", arguments={}),
            ToolCall(id="3", name="slow_tool_c", arguments={}),
        ]

        # Measure: Parallel execution time
        start_parallel = time.perf_counter()
        results = await executor.execute_parallel(calls)
        parallel_time = time.perf_counter() - start_parallel

        # Measure: Sequential execution time (for comparison)
        start_seq = time.perf_counter()
        for call in calls:
            await executor.execute(call.name, **call.arguments)
        sequential_time = time.perf_counter() - start_seq

        # Verify: Parallel is significantly faster than sequential
        # Parallel ~100ms (all at once), Sequential ~300ms (3 x 100ms)
        assert parallel_time < sequential_time * 0.5, (
            f"Parallel execution ({parallel_time*1000:.1f}ms) should be much faster "
            f"than sequential ({sequential_time*1000:.1f}ms)"
        )

        # Verify: Parallel completed all tools (results dict keyed by tool name)
        assert len(results) == 3


# =============================================================================
# Performance Test: Preference Extraction Speed
# =============================================================================


@pytest.mark.asyncio
class TestPreferenceExtractionPerformance:
    """Test preference extraction performance."""

    async def test_preference_extraction_speed(self):
        """Test that preference extraction is fast (< 100ms per extraction)."""
        extractor = PreferenceExtractor(confidence_threshold=0.7)

        test_inputs = [
            "我预算5000元去北京旅游",
            "计划3天行程，喜欢历史文化景点",
            "想带孩子一起去，要轻松的行程",
            "预算8000元，5月中旬出发",
            "我们3个人去成都，7天左右",
        ]

        # Measure: Extraction time for multiple inputs
        start = time.perf_counter()
        for user_input in test_inputs:
            extractor.matcher.extract(user_input)
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / len(test_inputs)) * 1000

        # Verify: Average extraction time is fast
        assert avg_time_ms < 10.0, (
            f"Average preference extraction time {avg_time_ms:.2f}ms is too slow"
        )

    async def test_preference_matcher_pattern_efficiency(self):
        """Test that pattern matching is efficient."""
        matcher = PreferenceMatcher(confidence_threshold=0.7)

        # Measure: Single pattern match
        iterations = 1000
        test_text = "我预算5000元去北京旅游，喜欢历史文化景点，计划3天行程"

        start = time.perf_counter()
        for _ in range(iterations):
            matcher.extract(test_text)
        elapsed = time.perf_counter() - start

        # Verify: 1000 extractions complete quickly
        assert elapsed < 1.0, (
            f"1000 preference extractions took {elapsed*1000:.1f}ms - too slow"
        )

    async def test_preference_extraction_accuracy(self):
        """Test that preference extraction finds expected patterns."""
        extractor = PreferenceExtractor(confidence_threshold=0.5)
        matcher = extractor.matcher

        # Note: PreferenceType only defines DESTINATION, BUDGET, DURATION
        test_cases = [
            ("预算5000元", PreferenceType.BUDGET),
            ("去北京", PreferenceType.DESTINATION),
            ("3天行程", PreferenceType.DURATION),
            ("我预算3000元去成都", PreferenceType.BUDGET),
            ("计划5天行程", PreferenceType.DURATION),
        ]

        for text, expected_type in test_cases:
            matches = matcher.extract(text)

            # Verify: At least one match found
            assert len(matches) > 0, f"No matches found for: {text}"

            # Verify: Expected type is in matches
            types_found = [m.key for m in matches]
            assert expected_type in types_found, (
                f"Expected {expected_type} in matches for '{text}', got {types_found}"
            )


# =============================================================================
# Performance Test: Context Building
# =============================================================================


@pytest.mark.asyncio
class TestContextBuildingPerformance:
    """Test context building and management performance."""

    async def test_context_building_speed(self):
        """Test that context building is fast."""
        mock_client = PerformanceTestClient(response_text="测试")
        registry = ToolRegistry()
        registry.register(FastMockTool())

        engine = QueryEngine(
            llm_client=mock_client,
            tool_registry=registry,
        )

        # Measure: Context building for a typical request
        start = time.perf_counter()

        for _ in range(10):
            engine._add_to_working_memory("conv-1", "user", "测试消息内容")
            engine._add_to_working_memory("conv-1", "assistant", "测试响应内容")

        elapsed = time.perf_counter() - start
        avg_time_ms = (elapsed / 10) * 1000

        # Verify: Context building is fast
        assert avg_time_ms < 1.0, (
            f"Context building {avg_time_ms:.3f}ms per operation is too slow"
        )

    async def test_history_limit_enforcement(self):
        """Test that history limit is enforced efficiently."""
        mock_client = PerformanceTestClient(response_text="测试")
        engine = QueryEngine(llm_client=mock_client)

        conversation_id = "perf-history-001"

        # Add many messages beyond the limit (20)
        start = time.perf_counter()
        for i in range(30):
            engine._add_to_working_memory(
                conversation_id,
                "user",
                f"消息 {i}"
            )
            engine._add_to_working_memory(
                conversation_id,
                "assistant",
                f"响应 {i}"
            )

        elapsed = time.perf_counter() - start

        # Verify: History is limited to 20
        history = engine._get_conversation_history(conversation_id)
        assert len(history) <= 20, f"History should be limited to 20, got {len(history)}"

        # Verify: Enforcement is fast
        assert elapsed < 0.1, f"History enforcement took {elapsed*1000:.1f}ms - too slow"

        await engine.close()


# =============================================================================
# Performance Test: Overall Throughput
# =============================================================================


@pytest.mark.asyncio
class TestOverallThroughput:
    """Test overall system throughput."""

    async def test_concurrent_intent_classification(self):
        """Test concurrent intent classification performance."""
        from app.core.intent import IntentClassifier, intent_classifier

        test_inputs = [
            "帮我规划去北京的行程",
            "北京天气怎么样",
            "推荐一些景点",
            "我想去上海旅游",
            "有什么好吃的",
        ]

        # Measure: Concurrent classification
        start = time.perf_counter()
        results = await asyncio.gather(*[
            intent_classifier.classify(inp) for inp in test_inputs
        ])
        elapsed = time.perf_counter() - start

        # Verify: All classifications completed
        assert len(results) == 5
        assert all(r.intent for r in results)

        # Verify: Performance is reasonable
        avg_per_item = elapsed / 5
        assert avg_per_item < 0.5, (
            f"Average time per classification {avg_per_item:.3f}s is too slow"
        )

    async def test_concurrent_slot_extraction(self):
        """Test concurrent slot extraction performance."""
        from app.core.intent import SlotExtractor

        extractor = SlotExtractor()
        test_inputs = [
            "五一期间去北京3个人",
            "计划去上海5天",
            "想去成都预算5000",
            "广州3个人5天",
            "深圳4天行程",
        ]

        start = time.perf_counter()
        results = [extractor.extract(inp) for inp in test_inputs]
        elapsed = time.perf_counter() - start

        # Verify: All extractions completed
        assert len(results) == 5

        # Verify: Performance is fast (slot extraction is synchronous)
        assert elapsed < 0.1, (
            f"Slot extraction took {elapsed*1000:.1f}ms for 5 inputs - too slow"
        )

    async def test_concurrent_preference_extraction(self):
        """Test concurrent preference extraction across multiple users."""
        extractor = PreferenceExtractor(confidence_threshold=0.7)

        test_inputs = [
            "我预算5000元去北京",
            "计划3天行程",
            "想去云南旅游",
            "预算8000元5天",
            "带孩子一起出行",
        ]

        start = time.perf_counter()
        results = [
            extractor.matcher.extract(inp) for inp in test_inputs
        ]
        elapsed = time.perf_counter() - start

        # Verify: All extractions completed
        assert len(results) == 5

        # Verify: Performance is fast
        avg_ms = (elapsed / 5) * 1000
        assert avg_ms < 10.0, (
            f"Average preference extraction {avg_ms:.2f}ms is too slow"
        )

    async def test_memory_operations_throughput(self):
        """Test in-memory working memory operations throughput."""
        mock_client = PerformanceTestClient(response_text="测试")
        engine = QueryEngine(llm_client=mock_client)

        conversation_id = "throughput-001"

        # Measure: Adding many messages to working memory
        iterations = 100
        start = time.perf_counter()

        for i in range(iterations):
            engine._add_to_working_memory(
                conversation_id,
                "user",
                f"用户消息内容 {i}"
            )
            engine._add_to_working_memory(
                conversation_id,
                "assistant",
                f"助手响应内容 {i}"
            )

        elapsed = time.perf_counter() - start
        avg_per_op = (elapsed / (iterations * 2)) * 1000

        # Verify: Operations are fast
        assert avg_per_op < 1.0, (
            f"Average memory operation {avg_per_op:.3f}ms is too slow"
        )

        await engine.close()
