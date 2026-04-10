"""QueryEngine 集成测试

测试 Function Calling 功能与 QueryEngine 的集成。
"""

import pytest
from app.core import QueryEngine, Tool, ToolCall, global_registry


# 测试工具
class MockWeatherTool(Tool):
    @property
    def name(self):
        return "get_weather"

    @property
    def description(self):
        return "获取指定城市的天气信息"

    @property
    def is_readonly(self):
        return True

    @property
    def is_concurrency_safe(self):
        return True

    async def execute(self, city: str):
        return f"{city} 今天晴天，25°C"


class MockAttractionTool(Tool):
    @property
    def name(self):
        return "get_attractions"

    @property
    def description(self):
        return "获取指定城市的景点推荐"

    @property
    def is_readonly(self):
        return True

    @property
    def is_concurrency_safe(self):
        return True

    async def execute(self, city: str):
        return f"{city} 的热门景点：故宫、长城、天坛"


@pytest.mark.asyncio
async def test_query_engine_basic():
    """测试 QueryEngine 基本功能"""
    # 创建模拟 LLM 客户端
    class MockLLMClient:
        async def stream_chat(self, messages, system_prompt=None):
            yield "这是 LLM 的响应"

        async def chat_with_tools(self, messages, tools, system_prompt=None):
            return ("这是 LLM 的响应", [])

    engine = QueryEngine(llm_client=MockLLMClient())

    result = []
    async for chunk in engine.process("你好", "test-conv"):
        result.append(chunk)

    output = "".join(result)
    assert "LLM" in output or "响应" in output


@pytest.mark.asyncio
async def test_query_engine_with_tools():
    """测试 QueryEngine 处理工具调用"""
    # 注册测试工具
    global_registry.register(MockWeatherTool())
    global_registry.register(MockAttractionTool())

    # 创建模拟 LLM 客户端，模拟工具调用
    class MockLLMClient:
        def __init__(self):
            self.call_count = 0

        async def stream_chat(self, messages, system_prompt=None):
            yield "这是 LLM 的响应"

        async def chat_with_tools(self, messages, tools, system_prompt=None):
            self.call_count += 1
            # 模拟返回工具调用请求
            if self.call_count == 1:
                # 第一次调用返回工具调用
                tool_call = ToolCall(
                    id="call_123",
                    name="get_weather",
                    arguments={"city": "北京"}
                )
                return ("", [tool_call])
            else:
                # 第二次调用（带工具结果）返回最终响应
                return ("根据工具结果，北京今天晴天，25°C", [])

    engine = QueryEngine(llm_client=MockLLMClient())

    result = []
    async for chunk in engine.process("北京今天天气怎么样？", "test-conv"):
        result.append(chunk)

    output = "".join(result)
    assert len(output) > 0


@pytest.mark.asyncio
async def test_query_engine_conversation_history():
    """测试对话历史管理"""
    # 创建 Mock LLM 客户端
    class MockLLMClient:
        async def stream_chat(self, messages, system_prompt=None):
            yield "收到消息"

        async def chat_with_tools(self, messages, tools, system_prompt=None):
            return ("收到消息", [])

    engine = QueryEngine(llm_client=MockLLMClient())

    # 发送多条消息
    async def send_and_collect(msg):
        result = []
        async for chunk in engine.process(msg, "test-conv-history"):
            result.append(chunk)
        return "".join(result)

    await send_and_collect("你好")
    await send_and_collect("我是小明")
    await send_and_collect("我喜欢去北京旅游")

    # 检查历史记录
    history = engine._get_conversation_history("test-conv-history")
    assert len(history) >= 3  # 至少有3次对话


@pytest.mark.asyncio
async def test_query_engine_reset_conversation():
    """测试重置对话"""
    # 创建 Mock LLM 客户端
    class MockLLMClient:
        async def stream_chat(self, messages, system_prompt=None):
            yield "收到消息"

        async def chat_with_tools(self, messages, tools, system_prompt=None):
            return ("收到消息", [])

    engine = QueryEngine(llm_client=MockLLMClient())

    # 发送消息
    await send_and_collect(engine, "你好")

    # 检查历史存在
    history = engine._get_conversation_history("test-conv-reset")
    assert len(history) > 0

    # 重置
    engine.reset_conversation("test-conv-reset")

    # 检查历史已清空
    history = engine._get_conversation_history("test-conv-reset")
    assert len(history) == 0


async def send_and_collect(engine, msg):
    result = []
    async for chunk in engine.process(msg, "test-conv-reset"):
        result.append(chunk)
    return "".join(result)


# =============================================================================
# Intent Enhancement Tests - 4 New Intent Types
# =============================================================================

from app.core.context import RequestContext
from app.core.intent import IntentRouter, RuleStrategy


@pytest.mark.asyncio
async def test_intent_classification_hotel():
    """Test hotel intent classification."""
    router = IntentRouter(strategies=[RuleStrategy()])
    context = RequestContext(message="帮我找北京的酒店", user_id="test")

    result = await router.classify(context)

    assert result.intent == "hotel"
    assert result.confidence >= 0.3


@pytest.mark.asyncio
async def test_intent_classification_food():
    """Test food intent classification."""
    router = IntentRouter(strategies=[RuleStrategy()])
    context = RequestContext(message="成都有什么好吃的", user_id="test")

    result = await router.classify(context)

    assert result.intent == "food"
    assert result.confidence >= 0.3


@pytest.mark.asyncio
async def test_intent_classification_budget():
    """Test budget intent classification."""
    router = IntentRouter(strategies=[RuleStrategy()])
    context = RequestContext(message="去北京大概多少钱", user_id="test")

    result = await router.classify(context)

    assert result.intent == "budget"
    assert result.confidence >= 0.3


@pytest.mark.asyncio
async def test_intent_classification_transport():
    """Test transport intent classification."""
    router = IntentRouter(strategies=[RuleStrategy()])
    context = RequestContext(message="怎么去上海", user_id="test")

    result = await router.classify(context)

    assert result.intent == "transport"
    assert result.confidence >= 0.3


@pytest.mark.asyncio
async def test_query_engine_fallback_no_tools():
    """测试没有工具时的回退行为"""
    # 清空注册表
    for tool in list(global_registry._tools.keys()):
        del global_registry._tools[tool]

    class MockLLMClient:
        async def stream_chat(self, messages, system_prompt=None):
            yield "没有工具时的普通响应"

        async def chat_with_tools(self, messages, tools, system_prompt=None):
            return ("没有工具时的普通响应", [])

    engine = QueryEngine(llm_client=MockLLMClient())

    result = []
    async for chunk in engine.process("你好", "test-conv-fallback"):
        result.append(chunk)

    output = "".join(result)
    assert "普通响应" in output


@pytest.mark.asyncio
async def test_query_engine_tool_registration():
    """测试工具注册到 QueryEngine"""
    # 创建新的工具注册表
    from app.core.tools import ToolRegistry

    registry = ToolRegistry()
    registry.register(MockWeatherTool())

    class MockLLMClient:
        async def stream_chat(self, messages, system_prompt=None):
            yield "响应"

        async def chat_with_tools(self, messages, tools, system_prompt=None):
            # 验证工具定义格式正确
            assert isinstance(tools, list)
            if tools:
                assert "name" in tools[0]
                assert "description" in tools[0]
            return ("响应", [])

    engine = QueryEngine(llm_client=MockLLMClient(), tool_registry=registry)

    result = []
    async for chunk in engine.process("测试", "test-conv-registry"):
        result.append(chunk)

    assert len(result) > 0
