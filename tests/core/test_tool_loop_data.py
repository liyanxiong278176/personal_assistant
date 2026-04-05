"""测试工具循环数据结构和 chat_with_tool_loop 方法

测试 ToolResult、ToolCallResult 数据结构以及工具循环逻辑。
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.llm import LLMClient, ToolCall, ToolResult, ToolCallResult


# ============ Test ToolResult Dataclass ============


class TestToolResult:
    """测试 ToolResult 数据类"""

    def test_tool_result_creation(self):
        """测试 ToolResult 基本创建"""
        result = ToolResult(success=True, data={"temp": 25})

        assert result.success is True
        assert result.data == {"temp": 25}
        assert result.error is None
        assert result.execution_time_ms == 0

    def test_tool_result_with_error(self):
        """测试带错误的 ToolResult"""
        result = ToolResult(
            success=False,
            data=None,
            error="API timeout",
            execution_time_ms=5000,
        )

        assert result.success is False
        assert result.data is None
        assert result.error == "API timeout"
        assert result.execution_time_ms == 5000

    def test_tool_result_defaults(self):
        """测试 ToolResult 默认值"""
        result = ToolResult(success=True, data="some data")

        assert result.error is None
        assert result.execution_time_ms == 0


# ============ Test ToolCallResult Dataclass ============


class TestToolCallResult:
    """测试 ToolCallResult 数据类"""

    def test_tool_call_result_creation(self):
        """测试 ToolCallResult 基本创建"""
        tc = ToolCall(id="call_1", name="get_weather", arguments={"city": "Beijing"})
        tr = ToolResult(success=True, data={"weather": "sunny"})

        result = ToolCallResult(
            iteration=1,
            content="The weather in Beijing is sunny.",
            tool_calls=[tc],
            tool_results={"call_1": tr},
            tokens_used=100,
            total_tokens=100,
            should_continue=True,
        )

        assert result.iteration == 1
        assert result.content == "The weather in Beijing is sunny."
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_weather"
        assert result.tool_results["call_1"].success is True
        assert result.tokens_used == 100
        assert result.total_tokens == 100
        assert result.should_continue is True
        assert result.stop_reason is None

    def test_tool_call_result_stop_reason(self):
        """测试带 stop_reason 的 ToolCallResult"""
        result = ToolCallResult(
            iteration=5,
            content="",
            tool_calls=[],
            tool_results={},
            tokens_used=0,
            total_tokens=500,
            should_continue=False,
            stop_reason="max_iterations_reached",
        )

        assert result.should_continue is False
        assert result.stop_reason == "max_iterations_reached"

    def test_tool_call_result_no_tool_calls(self):
        """测试无工具调用的 ToolCallResult"""
        result = ToolCallResult(
            iteration=1,
            content="Here is the answer.",
            tool_calls=[],
            tool_results={},
            tokens_used=50,
            total_tokens=50,
            should_continue=False,
            stop_reason="no_tool_calls",
        )

        assert result.stop_reason == "no_tool_calls"
        assert len(result.tool_calls) == 0
        assert len(result.tool_results) == 0


# ============ Test LLMClient Tool Call Classes ============


class TestToolCall:
    """测试 ToolCall 类"""

    def test_tool_call_creation(self):
        """测试 ToolCall 创建"""
        tc = ToolCall(
            id="call_123",
            name="search_hotels",
            arguments={"city": "Shanghai", "budget": 500},
        )

        assert tc.id == "call_123"
        assert tc.name == "search_hotels"
        assert tc.arguments == {"city": "Shanghai", "budget": 500}

    def test_tool_call_repr(self):
        """测试 ToolCall repr"""
        tc = ToolCall(id="call_1", name="get_weather", arguments={"city": "Beijing"})
        repr_str = repr(tc)

        assert "call_1" in repr_str
        assert "get_weather" in repr_str


# ============ Test LLMClient Basic Properties ============


class TestLLMClientBasic:
    """测试 LLMClient 基础功能"""

    def test_client_init_no_api_key(self):
        """测试无 API key 时客户端初始化"""
        with patch.dict("os.environ", {}, clear=True):
            client = LLMClient()
            assert client.api_key is None
            assert client.model == "deepseek-chat"
            assert client.max_retries == 3

    def test_client_init_with_api_key(self):
        """测试带 API key 的客户端初始化"""
        client = LLMClient(api_key="test_key_123")
        assert client.api_key == "test_key_123"

    def test_client_init_custom_params(self):
        """测试自定义参数的客户端初始化"""
        client = LLMClient(
            api_key="test_key",
            model="deepseek-coder",
            max_retries=5,
            timeout=30.0,
        )
        assert client.model == "deepseek-coder"
        assert client.max_retries == 5
        assert client.timeout == 30.0

    def test_format_tools_for_api(self):
        """测试工具格式化为 API 格式"""
        client = LLMClient(api_key="test")
        tools = [
            {
                "name": "get_weather",
                "description": "Get weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"}
                    },
                    "required": ["city"],
                },
            }
        ]

        formatted = client._format_tools_for_api(tools)

        assert len(formatted) == 1
        assert formatted[0]["type"] == "function"
        assert formatted[0]["function"]["name"] == "get_weather"
        assert formatted[0]["function"]["description"] == "Get weather for a city"
        assert "properties" in formatted[0]["function"]["parameters"]

    def test_format_tools_with_defaults(self):
        """测试工具格式化默认值"""
        client = LLMClient(api_key="test")
        tools = [{"name": "simple_tool"}]

        formatted = client._format_tools_for_api(tools)

        assert formatted[0]["function"]["description"] == ""
        assert formatted[0]["function"]["parameters"]["type"] == "object"
        assert formatted[0]["function"]["parameters"]["properties"] == {}
        assert formatted[0]["function"]["parameters"]["required"] == []


# ============ Test chat_with_tool_loop ============


class TestChatWithToolLoop:
    """测试 chat_with_tool_loop 工具循环方法"""

    @pytest.fixture
    def client(self):
        """创建无 API key 的测试客户端"""
        with patch.dict("os.environ", {}, clear=True):
            return LLMClient(api_key=None)

    @pytest.mark.asyncio
    async def test_tool_loop_no_api_key(self, client):
        """测试无 API key 时工具循环降级"""
        messages = [{"role": "user", "content": "What's the weather?"}]
        tools = [{"name": "get_weather", "description": "Get weather"}]

        results = []
        async for result in client.chat_with_tool_loop(
            messages, tools, lambda tc: ToolResult(success=True, data={})
        ):
            results.append(result)

        assert len(results) == 1
        assert results[0].should_continue is False
        assert "AI 服务暂时不可用" in results[0].content

    @pytest.mark.asyncio
    async def test_tool_loop_stops_on_no_api_key_messages_unchanged(self, client):
        """测试无 API key 时原始消息不被修改"""
        messages = [{"role": "user", "content": "Hello"}]
        tools = [{"name": "tool1"}]

        async for _ in client.chat_with_tool_loop(
            messages, tools, lambda tc: ToolResult(success=True, data={})
        ):
            pass

        # 原始消息列表不应被修改
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_tool_loop_max_iterations(self, client):
        """测试达到最大迭代次数时停止"""
        # Use a counter-based mock that always yields tool calls until max iterations
        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            yield ToolCall(id="call_1", name="fake_tool", arguments={})

        with patch.object(
            client, "stream_chat_with_tools", side_effect=mock_stream
        ):
            async def fake_executor(tc):
                return ToolResult(success=True, data={"result": "ok"})

            results = []
            async for result in client.chat_with_tool_loop(
                [{"role": "user", "content": "test"}],
                [{"name": "fake_tool"}],
                fake_executor,
                max_iterations=3,
            ):
                results.append(result)

        assert len(results) == 4
        # First 3 are intermediate iterations with tool calls
        for i in range(3):
            assert results[i].should_continue is True
            assert results[i].stop_reason is None
        # Final result is max_iterations_reached
        assert results[3].stop_reason == "max_iterations_reached"
        assert results[3].should_continue is False

    @pytest.mark.asyncio
    async def test_tool_loop_stop_event(self, client):
        """测试 stop_event 触发时停止"""
        stop_event = asyncio.Event()
        stop_event.set()  # 立即停止

        results = []
        async for result in client.chat_with_tool_loop(
            [{"role": "user", "content": "test"}],
            [{"name": "tool"}],
            lambda tc: ToolResult(success=True, data={}),
            stop_event=stop_event,
        ):
            results.append(result)

        assert len(results) == 1
        assert results[0].stop_reason == "stop_event_set"
        assert results[0].should_continue is False

    @pytest.mark.asyncio
    async def test_tool_loop_stops_when_no_tool_calls(self, client):
        """测试没有工具调用时停止"""
        async def mock_stream(*args, **kwargs):
            yield "This is a normal response with no tool calls."

        with patch.object(
            client, "stream_chat_with_tools", side_effect=mock_stream
        ):
            results = []
            async for result in client.chat_with_tool_loop(
                [{"role": "user", "content": "test"}],
                [{"name": "tool"}],
                lambda tc: ToolResult(success=True, data={}),
                max_iterations=3,
            ):
                results.append(result)

        assert len(results) == 1
        assert results[0].stop_reason == "no_tool_calls"
        assert results[0].content == "This is a normal response with no tool calls."
        assert results[0].should_continue is False

    @pytest.mark.asyncio
    async def test_tool_loop_executes_tools(self, client):
        """测试工具循环正确执行工具"""
        # First call yields tool call, second call yields text (ends loop)
        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield ToolCall(id="call_1", name="get_weather", arguments={"city": "Beijing"})
            else:
                yield "Weather retrieved successfully."

        with patch.object(
            client, "stream_chat_with_tools", side_effect=mock_stream
        ):
            executed = []

            async def executor(tc):
                executed.append(tc)
                return ToolResult(success=True, data={"weather": "sunny"})

            results = []
            async for result in client.chat_with_tool_loop(
                [{"role": "user", "content": "test"}],
                [{"name": "get_weather"}],
                executor,
            ):
                results.append(result)

            # First iteration has tool call, second has no tool call
            assert len(results) == 2
            assert results[0].should_continue is True
            assert results[0].stop_reason is None
            assert results[1].stop_reason == "no_tool_calls"
            assert len(executed) == 1
            assert executed[0].name == "get_weather"
            assert executed[0].arguments == {"city": "Beijing"}
            assert "call_1" in results[0].tool_results
            assert results[0].tool_results["call_1"].success is True
            assert results[0].tool_results["call_1"].data == {"weather": "sunny"}

    @pytest.mark.asyncio
    async def test_tool_loop_handles_tool_exception(self, client):
        """测试工具执行异常时正确处理"""
        # First call yields tool call, second call yields text (loop ends after tool fails)
        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield ToolCall(id="call_err", name="failing_tool", arguments={})
            else:
                yield "Attempted to call failing tool."

        with patch.object(
            client, "stream_chat_with_tools", side_effect=mock_stream
        ):

            async def failing_executor(tc):
                raise RuntimeError("Tool execution failed")

            results = []
            async for result in client.chat_with_tool_loop(
                [{"role": "user", "content": "test"}],
                [{"name": "failing_tool"}],
                failing_executor,
            ):
                results.append(result)

            assert len(results) == 2
            # First result: tool was called but failed
            tr = results[0].tool_results.get("call_err")
            assert tr is not None
            assert tr.success is False
            assert "Tool execution failed" in tr.error
            # Second result: no tool call, loop ends
            assert results[1].stop_reason == "no_tool_calls"

    @pytest.mark.asyncio
    async def test_tool_loop_messages_accumulation(self, client):
        """测试消息累积"""
        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield ToolCall(id="call_1", name="tool_a", arguments={})
            else:
                yield "Final answer after tool execution."

        with patch.object(
            client, "stream_chat_with_tools", side_effect=mock_stream
        ):

            async def executor(tc):
                return ToolResult(success=True, data={"executed": tc.name})

            results = []
            async for result in client.chat_with_tool_loop(
                [{"role": "user", "content": "initial"}],
                [{"name": "tool_a"}],
                executor,
            ):
                results.append(result)

            # 第一次迭代有工具调用，第二次迭代没有
            assert len(results) == 2
            assert results[0].should_continue is True
            assert results[0].stop_reason is None
            assert results[1].should_continue is False
            assert results[1].stop_reason == "no_tool_calls"

    @pytest.mark.asyncio
    async def test_tool_loop_accepts_non_dataclass_result(self, client):
        """测试工具执行器可以返回普通值而非 ToolResult"""
        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield ToolCall(id="call_1", name="simple_tool", arguments={})
            else:
                yield "Done."

        with patch.object(
            client, "stream_chat_with_tools", side_effect=mock_stream
        ):

            async def executor(tc):
                return {"result": "raw data"}  # 返回原始数据而非 ToolResult

            results = []
            async for result in client.chat_with_tool_loop(
                [{"role": "user", "content": "test"}],
                [{"name": "simple_tool"}],
                executor,
            ):
                results.append(result)

            assert len(results) == 2
            tr = results[0].tool_results["call_1"]
            assert tr.success is True
            assert tr.data == {"result": "raw data"}

    @pytest.mark.asyncio
    async def test_tool_loop_iteration_counting(self, client):
        """测试迭代计数正确"""
        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield ToolCall(id="call_1", name="tool", arguments={})
            else:
                yield "Done."

        with patch.object(
            client, "stream_chat_with_tools", side_effect=mock_stream
        ):

            async def executor(tc):
                return ToolResult(success=True, data={})

            results = []
            async for result in client.chat_with_tool_loop(
                [{"role": "user", "content": "test"}],
                [{"name": "tool"}],
                executor,
                max_iterations=5,
            ):
                results.append(result)

            assert results[0].iteration == 1
            assert results[1].iteration == 2

    @pytest.mark.asyncio
    async def test_tool_loop_multiple_tools(self, client):
        """测试单次迭代返回多个工具调用"""
        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield ToolCall(id="call_1", name="tool_a", arguments={})
                yield ToolCall(id="call_2", name="tool_b", arguments={})
            else:
                yield "Both tools executed."

        with patch.object(
            client, "stream_chat_with_tools", side_effect=mock_stream
        ):

            async def executor(tc):
                return ToolResult(success=True, data={"tool": tc.name})

            results = []
            async for result in client.chat_with_tool_loop(
                [{"role": "user", "content": "test"}],
                [{"name": "tool_a"}, {"name": "tool_b"}],
                executor,
            ):
                results.append(result)

            assert len(results) == 2
            # First iteration: has tool calls
            assert len(results[0].tool_calls) == 2
            assert len(results[0].tool_results) == 2
            assert results[0].tool_results["call_1"].data == {"tool": "tool_a"}
            assert results[0].tool_results["call_2"].data == {"tool": "tool_b"}
            assert results[0].should_continue is True
            # Second iteration: no tool calls, ends loop
            assert results[1].stop_reason == "no_tool_calls"
            assert results[1].should_continue is False


# ============ Test Guard Integration ============


class TestGuardIntegration:
    """测试 InferenceGuard 与 LLMClient 的集成"""

    @pytest.fixture
    def client(self):
        with patch.dict("os.environ", {}, clear=True):
            return LLMClient(api_key=None)

    @pytest.mark.asyncio
    async def test_stream_chat_accepts_guard_param(self, client):
        """测试 stream_chat 接受 guard 参数"""
        from app.core.context.inference_guard import InferenceGuard

        guard = InferenceGuard(max_tokens_per_response=100, max_total_budget=200)

        # 无 API key 时应该降级，不使用 guard
        results = []
        async for chunk in client.stream_chat(
            [{"role": "user", "content": "test"}],
            guard=guard,
        ):
            results.append(chunk)

        assert len(results) == 1
        assert "AI 服务暂时不可用" in results[0]

    @pytest.mark.asyncio
    async def test_chat_with_tool_loop_accepts_guard_param(self, client):
        """测试 chat_with_tool_loop 接受 guard 参数"""
        from app.core.context.inference_guard import InferenceGuard

        guard = InferenceGuard(max_tokens_per_response=100, max_total_budget=200)

        results = []
        async for result in client.chat_with_tool_loop(
            [{"role": "user", "content": "test"}],
            [{"name": "tool"}],
            lambda tc: ToolResult(success=True, data={}),
            guard=guard,
        ):
            results.append(result)

        assert len(results) >= 1


# ============ Test Export ============


class TestExports:
    """测试包导出"""

    def test_llm_package_exports(self):
        """测试 llm 包正确导出"""
        from app.core.llm import LLMClient, ToolCall, ToolResult, ToolCallResult

        assert LLMClient is not None
        assert ToolCall is not None
        assert ToolResult is not None
        assert ToolCallResult is not None

    def test_core_package_exports(self):
        """测试 core 包正确导出"""
        from app.core import ToolResult, ToolCallResult

        assert ToolResult is not None
        assert ToolCallResult is not None
