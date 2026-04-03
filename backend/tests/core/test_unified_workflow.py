"""统一流程集成测试

验证 QueryEngine 的 6 步工作流程：
1. 意图 & 槽位识别
2. 消息基础存储
3. 按需并行调用工具
4. 上下文构建
5. LLM 生成响应
6. 异步记忆���新
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.query_engine import QueryEngine
from app.core.llm import LLMClient, ToolCall
from app.core.intent import intent_classifier


class MockLLMClient(LLMClient):
    """模拟 LLM 客户端"""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0

    async def stream_chat(self, messages, system_prompt=None):
        """模拟流式响应"""
        for chunk in self.responses:
            yield chunk

    async def chat(self, messages, system_prompt=None):
        """模拟非流式响应"""
        return self.responses[0] if self.responses else "模拟响应"

    async def chat_with_tools(self, messages, tools, system_prompt=None):
        """模拟工具调用"""
        # 默认不调用工具，直接返回响应
        return ("模拟响应", [])

    async def close(self):
        """清理资源"""
        pass


@pytest.fixture
def mock_llm_client():
    """创建模拟 LLM 客户端"""
    client = MockLLMClient(responses=["这是", "模拟的", "响应"])
    return client


@pytest.fixture
def query_engine(mock_llm_client):
    """创建带模拟客户端的 QueryEngine"""
    return QueryEngine(llm_client=mock_llm_client)


class TestUnifiedWorkflowChat:
    """测试: 普通对话流程"""

    @pytest.mark.asyncio
    async def test_unified_workflow_chat(self, query_engine):
        """测试普通对话流程"""
        chunks = []
        async for chunk in query_engine.process("你好在吗", "conv123", "user1"):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert "".join(chunks) == "这是模拟的响应"

    @pytest.mark.asyncio
    async def test_unified_workflow_conversation_history(self, query_engine):
        """测试对话历史记录"""
        async for _ in query_engine.process("你好", "conv456", "user1"):
            pass

        history = query_engine._get_conversation_history("conv456")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "你好"
        assert history[1]["role"] == "assistant"


class TestIntentClassification:
    """测试: 意图分类集成"""

    def test_intent_classification_itinerary(self):
        """测试行程规划意图识别"""
        result = intent_classifier.classify_sync("帮我规划北京三日游")
        assert result.intent == "itinerary"
        assert result.confidence >= 0.8
        assert result.method in ["keyword", "llm"]

    def test_intent_classification_query(self):
        """测试查询意图识别"""
        result = intent_classifier.classify_sync("北京今天天气怎么样")
        assert result.intent == "query"
        assert result.confidence >= 0.8

    def test_intent_classification_chat(self):
        """测试聊天意图识别"""
        result = intent_classifier.classify_sync("你好在吗")
        assert result.intent == "chat"
        # chat 意图可能置信度较低
        assert result.confidence > 0

    def test_intent_classification_image(self):
        """测试图片识别意图"""
        result = intent_classifier.classify_sync("识别这张图片", has_image=True)
        assert result.intent == "image"
        assert result.confidence == 1.0
        assert result.method == "attachment"


class TestSlotExtraction:
    """测试: 槽位提取集成"""

    def test_slot_extraction_destination(self, query_engine):
        """测试目的地提取"""
        slots = query_engine._slot_extractor.extract("我想去北京旅游")
        assert slots.destination == "北京"

    def test_slot_extraction_date_range(self, query_engine):
        """测试日期范围提取"""
        slots = query_engine._slot_extractor.extract("4月5日到4月10日去北京玩")
        assert slots.start_date is not None
        assert slots.end_date is not None

    def test_slot_extraction_holiday(self, query_engine):
        """测试节假日提取"""
        slots = query_engine._slot_extractor.extract("五一假期去哪里玩")
        assert slots.start_date is not None
        assert slots.end_date is not None


class TestToolExecution:
    """测试: 工具执行集成"""

    @pytest.mark.asyncio
    async def test_tool_execution_by_intent(self, query_engine, mock_llm_client):
        """测试基于意图的工具执行"""
        # 模拟 LLM 返回工具调用
        tool_call = ToolCall(
            id="1",
            name="search_weather",
            arguments={"city": "北京"}
        )

        async def mock_chat_with_tools(messages, tools, system_prompt=None):
            return ("让我查询一下", [tool_call])

        mock_llm_client.chat_with_tools = mock_chat_with_tools

        # 注册模拟工具（需要创建 Tool 子类）
        from app.core.tools.base import Tool

        class MockWeatherTool(Tool):
            @property
            def name(self) -> str:
                return "search_weather"

            @property
            def description(self) -> str:
                return "查询天气"

            async def execute(self, city: str) -> dict:
                return {"city": city, "temperature": 25, "condition": "晴"}

        query_engine._tool_registry.register(MockWeatherTool())

        # 处理查询意图的请求
        chunks = []
        async for chunk in query_engine.process("北京今天天气怎么样", "conv789"):
            chunks.append(chunk)

        # 验证有响应
        assert len(chunks) > 0


class TestContextBuilding:
    """测试: 上下文构建集成"""

    @pytest.mark.asyncio
    async def test_context_building_with_slots(self, query_engine):
        """测试带槽位的上下文构建"""
        from app.core.intent import SlotResult

        slots = SlotResult(
            destination="北京",
            start_date="2026-05-01",
            end_date="2026-05-03"
        )

        context = await query_engine._build_context(
            user_id="user1",
            tool_results={},
            slots=slots,
            stage_log=None
        )

        # 验证上下文包含槽位信息
        assert "北京" in context or "destination" in context.lower()


class TestMemoryUpdate:
    """测试: 异步记忆更新"""

    @pytest.mark.asyncio
    async def test_memory_update_task(self, query_engine):
        """测试异步记忆更新任务"""
        from app.core.intent import SlotResult

        slots = SlotResult(destination="北京")

        # 创建记忆更新任务
        task = asyncio.create_task(
            query_engine._update_memory_async(
                user_id="user1",
                conversation_id="conv888",
                user_input="我想去北京",
                assistant_response="好的，我可以帮您规划北京行程",
                slots=slots
            )
        )

        # 等待任务完成
        await task

        # 任务应该正常完成，不抛出异常
        assert task.done()


class TestWorkflowIntegration:
    """测试: 完整工作流集成"""

    @pytest.mark.asyncio
    async def test_full_workflow_itinerary_intent(self, query_engine):
        """测试行程规划意图的完整流程"""
        # 测试行程规划类查询
        chunks = []
        async for chunk in query_engine.process("帮我规划北京三日游", "conv001"):
            chunks.append(chunk)

        response = "".join(chunks)
        assert len(response) > 0

        # 验证对话历史已更新
        history = query_engine._get_conversation_history("conv001")
        assert len(history) >= 2

    @pytest.mark.asyncio
    async def test_full_workflow_query_intent(self, query_engine):
        """测试查询意图的完整流程"""
        chunks = []
        async for chunk in query_engine.process("北京今天天气怎么样", "conv002"):
            chunks.append(chunk)

        response = "".join(chunks)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_full_workflow_chat_intent(self, query_engine):
        """测试聊天意图的完整流程"""
        chunks = []
        async for chunk in query_engine.process("你好在吗", "conv003"):
            chunks.append(chunk)

        response = "".join(chunks)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_workflow_with_conversation_context(self, query_engine):
        """测试带对话上下文的工作流"""
        # 第一轮对话
        async for _ in query_engine.process("我想去北京旅游", "conv004"):
            pass

        # 第二轮对话（应该有上下文）
        chunks = []
        async for chunk in query_engine.process("有什么推荐的景点吗", "conv004"):
            chunks.append(chunk)

        response = "".join(chunks)
        assert len(response) > 0

        # 验证历史记录
        history = query_engine._get_conversation_history("conv004")
        assert len(history) >= 4  # 两轮对话，每轮2条


class TestErrorHandling:
    """测试: 错误处理"""

    @pytest.mark.asyncio
    async def test_workflow_without_llm_client(self):
        """测试没有 LLM 客户端时的错误处理"""
        engine = QueryEngine(llm_client=None)

        with pytest.raises(Exception) as exc_info:
            async for _ in engine.process("你好", "conv999"):
                pass

        assert "LLM" in str(exc_info.value) or "客户端" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_workflow_tool_execution_failure(self, query_engine, mock_llm_client):
        """测试工具执行失败时的降级处理"""
        # 模拟工具调用但执行失败
        tool_call = ToolCall(
            id="1",
            name="nonexistent_tool",
            arguments={}
        )

        async def mock_chat_with_tools(messages, tools, system_prompt=None):
            return ("让我查询", [tool_call])

        mock_llm_client.chat_with_tools = mock_chat_with_tools

        # 应该降级到普通聊天，不崩溃
        chunks = []
        async for chunk in query_engine.process("查询天气", "conv777"):
            chunks.append(chunk)

        # 应该仍然有响应
        assert len(chunks) > 0
