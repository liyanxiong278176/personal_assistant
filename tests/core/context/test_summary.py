"""测试 LLMSummaryProvider 摘要生成器"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.context.summary import (
    LLMSummaryProvider,
    create_summary_provider,
)
from app.core.errors import AgentError


class TestLLMSummaryProviderInit:
    """测试 LLMSummaryProvider 初始化"""

    def test_default_init(self):
        """测试默认初始化"""
        provider = LLMSummaryProvider()
        assert provider.model == "deepseek-chat"
        assert provider.max_retries == 3
        assert provider.max_chars_per_message == 500
        assert provider.timeout == 30.0

    def test_custom_init(self):
        """测试自定义初始化"""
        provider = LLMSummaryProvider(
            model="gpt-4",
            max_retries=5,
            max_chars_per_message=1000,
            timeout=60.0
        )
        assert provider.model == "gpt-4"
        assert provider.max_retries == 5
        assert provider.max_chars_per_message == 1000
        assert provider.timeout == 60.0

    def test_init_with_api_key(self):
        """测试带 API key 初始化"""
        provider = LLMSummaryProvider(api_key="test-key-123")
        assert provider.api_key == "test-key-123"


class TestFormatMessagesForSummary:
    """测试消息格式化"""

    def test_empty_messages(self):
        """测试空消息列表"""
        provider = LLMSummaryProvider()
        result = provider._format_messages_for_summary([])
        assert result == ""

    def test_single_short_message(self):
        """测试单条短消息"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user", "content": "Hello, how are you?"}
        ]
        result = provider._format_messages_for_summary(messages)
        assert "user:" in result
        assert "Hello, how are you?" in result

    def test_long_message_truncation(self):
        """测试长消息截断"""
        provider = LLMSummaryProvider(max_chars_per_message=50)
        long_content = "x" * 1000
        messages = [
            {"role": "user", "content": long_content}
        ]
        result = provider._format_messages_for_summary(messages)
        # 截断后应该加上省略号
        assert len(result) < 1100  # 50 chars + "user:" + "..."
        assert "..." in result

    def test_multiple_messages(self):
        """测试多条消息格式化"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Answer 2"},
        ]
        result = provider._format_messages_for_summary(messages)
        assert "user: Question 1" in result
        assert "assistant: Answer 1" in result
        assert "user: Question 2" in result
        assert "assistant: Answer 2" in result

    def test_tool_message_formatting(self):
        """测试工具消息格式化"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user", "content": "What's the weather?"},
            {"role": "tool", "name": "get_weather", "content": "Sunny, 25°C"},
        ]
        result = provider._format_messages_for_summary(messages)
        assert "user: What's the weather?" in result
        assert "tool[get_weather]:" in result or "get_weather" in result

    def test_system_message_excluded(self):
        """测试 system 消息默认被排除"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"},
        ]
        result = provider._format_messages_for_summary(messages)
        # system 消息应该被排除
        assert "helpful assistant" not in result
        assert "user: Hello" in result


class TestFallbackSummary:
    """测试降级摘要"""

    def test_empty_messages_fallback(self):
        """测试空消息的降级摘要"""
        provider = LLMSummaryProvider()
        result = provider._fallback_summary([])
        assert result == "No conversation history."

    def test_single_user_message_fallback(self):
        """测试单条用户消息的降级摘要"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user", "content": "Hello"}
        ]
        result = provider._fallback_summary(messages)
        assert "1" in result
        assert "user" in result.lower()

    def test_mixed_messages_fallback(self):
        """测试混合消息的降级摘要"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "tool", "name": "search", "content": "result"},
        ]
        result = provider._fallback_summary(messages)
        assert "2" in result  # 2 user messages
        assert "assistant" in result.lower()
        assert "tool" in result.lower()

    def test_tool_counting_in_fallback(self):
        """测试工具调用计数"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user", "content": "Search"},
            {"role": "tool", "name": "search", "content": "Result 1"},
            {"role": "tool", "name": "search", "content": "Result 2"},
        ]
        result = provider._fallback_summary(messages)
        assert "2" in result  # 2 tool messages


class TestGenerateSummary:
    """测试异步摘要生成"""

    @pytest.mark.asyncio
    async def test_generate_summary_with_llm_success(self):
        """测试 LLM 成功生成摘要"""
        provider = LLMSummaryProvider(api_key="test-key")
        messages = [
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is artificial intelligence."},
        ]

        # Mock the LLM client
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value="Summary: User asked about AI and assistant explained it.")

        with patch.object(provider, '_get_llm_client', return_value=mock_client):
            summary = await provider.generate_summary(messages)
            assert "Summary:" in summary
            mock_client.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_summary_llm_failure_fallback(self):
        """测试 LLM 失败时使用降级摘要"""
        provider = LLMSummaryProvider(api_key="test-key")
        messages = [
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Answer"},
        ]

        # Mock LLM client that raises error
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(provider, '_get_llm_client', return_value=mock_client):
            summary = await provider.generate_summary(messages)
            # 应该回退到计数摘要
            assert "user" in summary.lower() or "1" in summary

    @pytest.mark.asyncio
    async def test_generate_summary_no_api_key_fallback(self):
        """测试无 API key 时使用降级摘要"""
        provider = LLMSummaryProvider(api_key=None)
        messages = [
            {"role": "user", "content": "Test"},
        ]

        summary = await provider.generate_summary(messages)
        # 应该直接使用降级摘要
        assert "user" in summary.lower() or "conversation" in summary.lower()

    @pytest.mark.asyncio
    async def test_generate_summary_with_retries(self):
        """测试摘要生成重试机制"""
        provider = LLMSummaryProvider(api_key="test-key", max_retries=3)
        messages = [{"role": "user", "content": "Test"}]

        mock_client = AsyncMock()
        # 前两次失败，第三次成功
        mock_client.chat = AsyncMock(
            side_effect=[Exception("Error 1"), Exception("Error 2"), "Success summary"]
        )

        with patch.object(provider, '_get_llm_client', return_value=mock_client):
            summary = await provider.generate_summary(messages)
            assert summary == "Success summary"
            assert mock_client.chat.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_summary_all_retries_fail(self):
        """测试所有重试都失败时使用降级摘要"""
        provider = LLMSummaryProvider(api_key="test-key", max_retries=2)
        messages = [
            {"role": "user", "content": "Test"},
        ]

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(side_effect=Exception("Always fails"))

        with patch.object(provider, '_get_llm_client', return_value=mock_client):
            summary = await provider.generate_summary(messages)
            # 应该回退到降级摘要
            assert "user" in summary.lower() or "conversation" in summary.lower()

    @pytest.mark.asyncio
    async def test_generate_summary_empty_messages(self):
        """测试空消息列表的摘要"""
        provider = LLMSummaryProvider(api_key="test-key")
        summary = await provider.generate_summary([])
        assert summary == "No conversation history."

    @pytest.mark.asyncio
    async def test_generate_summary_custom_system_prompt(self):
        """测试自定义系统提示词"""
        provider = LLMSummaryProvider(api_key="test-key")
        messages = [{"role": "user", "content": "Test"}]

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value="Summary")

        with patch.object(provider, '_get_llm_client', return_value=mock_client):
            await provider.generate_summary(
                messages,
                system_prompt="Custom instructions"
            )
            # 验证系统提示词被包含在用户消息中（实现方式）
            call_args = mock_client.chat.call_args
            messages_arg = call_args[1].get("messages", [])
            assert len(messages_arg) > 0
            assert "Custom instructions" in messages_arg[0]["content"]


class TestCreateSummaryFunc:
    """测试创建同步摘要函数"""

    def test_create_summary_func_returns_callable(self):
        """测试返回可调用对象"""
        provider = LLMSummaryProvider()
        func = provider.create_summary_func()
        assert callable(func)

    def test_summary_func_is_sync(self):
        """测试摘要函数是同步的"""
        provider = LLMSummaryProvider()
        func = provider.create_summary_func()
        # 同步函数不应该返回 coroutine
        result = func([])
        assert not asyncio.iscoroutine(result)

    def test_summary_func_with_messages(self):
        """测试摘要函数处理消息"""
        provider = LLMSummaryProvider()
        func = provider.create_summary_func()
        messages = [
            {"role": "user", "content": "Test message"},
        ]
        result = func(messages)
        # 同步降级应该返回计数摘要
        assert "user" in result.lower() or "1" in result

    def test_summary_func_empty_messages(self):
        """测试摘要函数处理空消息"""
        provider = LLMSummaryProvider()
        func = provider.create_summary_func()
        result = func([])
        assert result == "No conversation history."


class TestCreateSummaryProvider:
    """测试工厂函数"""

    def test_create_with_defaults(self):
        """测试使用默认值创建"""
        provider = create_summary_provider()
        assert isinstance(provider, LLMSummaryProvider)
        assert provider.model == "deepseek-chat"

    def test_create_with_api_key(self):
        """测试使用 API key 创建"""
        provider = create_summary_provider(api_key="test-key")
        assert provider.api_key == "test-key"

    def test_create_with_custom_model(self):
        """测试使用自定义模型创建"""
        provider = create_summary_provider(model="gpt-4")
        assert provider.model == "gpt-4"


class TestLLMSummaryProviderIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_summary_workflow(self):
        """测试完整的摘要工作流"""
        provider = LLMSummaryProvider(api_key="test-key")
        messages = [
            {"role": "user", "content": "What's the weather in Beijing?"},
            {"role": "assistant", "content": "Let me check the weather for you."},
            {"role": "tool", "name": "get_weather", "content": "Beijing: Sunny, 22°C"},
            {"role": "assistant", "content": "The weather in Beijing is sunny and 22°C."},
        ]

        # 格式化测试
        formatted = provider._format_messages_for_summary(messages)
        assert "Beijing" in formatted
        assert "weather" in formatted.lower()

        # 降级摘要测试
        fallback = provider._fallback_summary(messages)
        assert "user" in fallback.lower()
        assert "tool" in fallback.lower()

    @pytest.mark.asyncio
    async def test_long_conversation_summary(self):
        """测试长对话摘要"""
        provider = LLMSummaryProvider(max_chars_per_message=100)
        messages = []
        for i in range(20):
            messages.append({"role": "user", "content": f"Question {i}: " + "x" * 200})
            messages.append({"role": "assistant", "content": f"Answer {i}: " + "y" * 200})

        # 格式化应该截断长消息
        formatted = provider._format_messages_for_summary(messages)
        # 每条消息最多 100 字符，40 条消息最多约 5000 字符（加前缀）
        assert len(formatted) < 8000

        # 降级摘要应该正确计数
        fallback = provider._fallback_summary(messages)
        assert "20" in fallback  # 20 user messages


class TestLLMSummaryProviderEdgeCases:
    """边界情况测试"""

    def test_message_without_content(self):
        """测试没有 content 字段的消息"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user"},  # 没有 content
            {"role": "assistant", "content": "Hello"},
        ]
        result = provider._format_messages_for_summary(messages)
        # 应该优雅处理，不崩溃
        assert "assistant: Hello" in result

    def test_message_with_empty_content(self):
        """测试空 content 的消息"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "Hi"},
        ]
        result = provider._format_messages_for_summary(messages)
        # 空内容也应该被处理
        assert "assistant: Hi" in result

    def test_unicode_characters(self):
        """测试 Unicode 字符处理"""
        provider = LLMSummaryProvider(max_chars_per_message=50)
        messages = [
            {"role": "user", "content": "你好世界" * 100},  # 中文字符
        ]
        result = provider._format_messages_for_summary(messages)
        # 应该正确处理 Unicode 字符
        assert "你好" in result or "..." in result

    def test_special_characters_in_content(self):
        """测试特殊字符处理"""
        provider = LLMSummaryProvider()
        messages = [
            {"role": "user", "content": "Test with <script>alert('xss')</script>"},
        ]
        result = provider._format_messages_for_summary(messages)
        # 应该包含特殊字符（不转义，因为只是内部使用）
        assert "<script>" in result

    def test_very_long_single_message(self):
        """测试非常长的单条消息"""
        provider = LLMSummaryProvider(max_chars_per_message=100)
        messages = [
            {"role": "user", "content": "x" * 10000},
        ]
        result = provider._format_messages_for_summary(messages)
        # 应该被截断
        assert len(result) < 200  # 100 + prefix + "..."

    @pytest.mark.asyncio
    async def test_generate_summary_timeout(self):
        """测试超时处理"""
        provider = LLMSummaryProvider(api_key="test-key", timeout=0.01)
        messages = [{"role": "user", "content": "Test"}]

        mock_client = AsyncMock()
        # 模拟超时 - 使用 httpx.TimeoutException
        async def timeout_chat(*args, **kwargs):
            await asyncio.sleep(0.001)  # 非常短的延迟
            raise httpx.TimeoutException("Request timeout", request=None)

        mock_client.chat = timeout_chat

        with patch.object(provider, '_get_llm_client', return_value=mock_client):
            summary = await provider.generate_summary(messages)
            # 超时后应该回退到降级摘要
            assert "user" in summary.lower() or "conversation" in summary.lower()


__all__ = [
    "TestLLMSummaryProviderInit",
    "TestFormatMessagesForSummary",
    "TestFallbackSummary",
    "TestGenerateSummary",
    "TestCreateSummaryFunc",
    "TestCreateSummaryProvider",
    "TestLLMSummaryProviderIntegration",
    "TestLLMSummaryProviderEdgeCases",
]
