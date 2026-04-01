"""Tests for Context Management (compressor and manager)

Tests cover:
- ContextCompressor compression logic
- ContextManager message management
- Token counting integration
- Auto-compression behavior
"""

import pytest

from app.core.context import (
    ContextCompressor,
    ContextManager,
    TokenEstimator,
)


class TestContextCompressor:
    """测试 ContextCompressor 类"""

    def test_init_default_params(self):
        """测试默认参数初始化"""
        compressor = ContextCompressor()

        assert compressor.max_tokens == ContextCompressor.DEFAULT_MAX_TOKENS
        assert (
            compressor.compression_threshold
            == ContextCompressor.DEFAULT_COMPRESSION_THRESHOLD
        )
        assert compressor.keep_recent == ContextCompressor.DEFAULT_KEEP_RECENT

    def test_init_custom_params(self):
        """测试自定义参数初始化"""
        compressor = ContextCompressor(
            max_tokens=5000,
            compression_threshold=0.7,
            keep_recent=5,
            summary_tokens=200,
        )

        assert compressor.max_tokens == 5000
        assert compressor.compression_threshold == 0.7
        assert compressor.keep_recent == 5
        assert compressor.summary_tokens == 200

    def test_init_invalid_threshold(self):
        """测试无效的压缩阈值"""
        with pytest.raises(ValueError, match="compression_threshold must be between 0 and 1"):
            ContextCompressor(compression_threshold=0)

        with pytest.raises(ValueError, match="compression_threshold must be between 0 and 1"):
            ContextCompressor(compression_threshold=1.5)

    def test_needs_compaction_empty_messages(self):
        """测试空消息列表不需要压缩"""
        compressor = ContextCompressor(max_tokens=1000)
        assert not compressor.needs_compaction([])

    def test_needs_compaction_below_threshold(self):
        """测试低于阈值时不需要压缩"""
        compressor = ContextCompressor(max_tokens=1000, compression_threshold=0.8)

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        assert not compressor.needs_compaction(messages)

    def test_needs_compaction_at_threshold(self):
        """测试达到阈值时需要压缩"""
        # 使用低阈值确保消息触发压缩
        compressor = ContextCompressor(max_tokens=10, compression_threshold=0.5)

        # 添加足够多的消息以触发压缩
        messages = [{"role": "user", "content": "This is a longer message that should trigger compression"}]

        assert compressor.needs_compaction(messages)

    def test_compress_no_change_when_not_needed(self):
        """测试不需要压缩时不改变消息"""
        compressor = ContextCompressor(max_tokens=10000)

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        result = compressor.compress(messages)
        assert result == messages

    def test_compress_preserves_system_messages(self):
        """测试压缩时保留 system 消息"""
        compressor = ContextCompressor(max_tokens=50, keep_recent=2)

        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Message 3"},
            {"role": "assistant", "content": "Response 3"},
        ]

        result = compressor.compress(messages)

        # 应该保留所有 system 消息
        system_messages = [m for m in result if m.get("role") == "system"]
        assert len(system_messages) == 2

    def test_compress_keeps_recent_messages(self):
        """测试压缩时保留最近的消息"""
        compressor = ContextCompressor(max_tokens=50, keep_recent=3)

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Old message 1"},
            {"role": "assistant", "content": "Old response 1"},
            {"role": "user", "content": "Old message 2"},
            {"role": "assistant", "content": "Old response 2"},
            {"role": "user", "content": "Recent message"},
            {"role": "assistant", "content": "Recent response"},
        ]

        result = compressor.compress(messages)

        # 保留最近的 3 条非 system 消息
        non_system = [m for m in result if m.get("role") != "system"]
        assert len(non_system) == 3

        # 验证是最新的消息
        assert non_system[-1]["content"] == "Recent response"

    def test_compress_with_summary(self):
        """测试带摘要的压缩"""
        compressor = ContextCompressor(max_tokens=50, keep_recent=2)

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Old message"},
            {"role": "assistant", "content": "Old response"},
            {"role": "user", "content": "Recent message"},
            {"role": "assistant", "content": "Recent response"},
        ]

        custom_summary = "This is a custom summary of the conversation"

        result = compressor.compress(messages, llm_summary=custom_summary)

        # 应该包含摘要
        summary_messages = [m for m in result if "历史对话摘要" in m.get("content", "")]
        assert len(summary_messages) == 1
        assert custom_summary in summary_messages[0]["content"]

    def test_compress_with_summary_function(self):
        """测试使用摘要函数的压缩"""
        compressor = ContextCompressor(max_tokens=50, keep_recent=2)

        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Answer 2"},
            {"role": "user", "content": "Recent question"},
            {"role": "assistant", "content": "Recent answer"},
        ]

        def summary_func(msgs):
            return f"Summary of {len(msgs)} messages"

        result, summary = compressor.compress_with_summary(messages, summary_func)

        # 6条消息，保留最近2条，所以有4条被摘要
        assert summary == "Summary of 4 messages"
        assert len(result) < len(messages)

    def test_get_compression_stats(self):
        """测试获取压缩统计信息"""
        compressor = ContextCompressor(max_tokens=1000, compression_threshold=0.8)

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        stats = compressor.get_compression_stats(messages)

        assert stats["current_tokens"] > 0
        assert stats["max_tokens"] == 1000
        assert stats["threshold"] == 800
        assert not stats["needs_compaction"]
        assert 0 < stats["usage_ratio"] < 1
        assert stats["message_count"] == 2


class TestContextManager:
    """测试 ContextManager 类"""

    def test_init_default(self):
        """测试默认初始化"""
        manager = ContextManager()

        assert manager.get_message_count() == 0
        assert manager.get_token_count() == 0
        assert manager.auto_compress is True

    def test_add_message(self):
        """测试添加单条消息"""
        manager = ContextManager()

        manager.add_message("user", "Hello world")

        assert manager.get_message_count() == 1
        assert manager.get_token_count() > 0

    def test_add_message_with_name(self):
        """测试添���带名称的消息"""
        manager = ContextManager()

        manager.add_message("user", "Hello", name="Alice")

        messages = manager.get_messages()
        assert messages[0]["name"] == "Alice"

    def test_add_messages_batch(self):
        """测试批量添加消息"""
        manager = ContextManager()

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        manager.add_messages(messages)

        assert manager.get_message_count() == 2

    def test_get_messages_default(self):
        """测试获取消息（默认包含 system）"""
        manager = ContextManager()

        manager.add_message("system", "You are helpful")
        manager.add_message("user", "Hello")

        messages = manager.get_messages()
        assert len(messages) == 2

    def test_get_messages_exclude_system(self):
        """测试获取消息（排除 system）"""
        manager = ContextManager()

        manager.add_message("system", "You are helpful")
        manager.add_message("user", "Hello")

        messages = manager.get_messages(include_system=False)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_get_messages_max_count(self):
        """测试限制返回消息数量"""
        manager = ContextManager()

        for i in range(10):
            manager.add_message("user", f"Message {i}")

        messages = manager.get_messages(max_count=5)
        assert len(messages) == 5
        # 应该是最新的消息
        assert messages[-1]["content"] == "Message 9"

    def test_get_messages_returns_copy(self):
        """测试返回的是消息副本"""
        manager = ContextManager()

        manager.add_message("user", "Hello")

        messages = manager.get_messages()
        messages[0]["content"] = "Modified"

        # 原始消息不应被修改
        original = manager.get_messages()
        assert original[0]["content"] == "Hello"

    def test_get_token_count(self):
        """测试获取 token 计数"""
        manager = ContextManager()

        manager.add_message("user", "Hello world")

        count = manager.get_token_count()
        assert count > 0

        # 与 TokenEstimator 结果一致
        messages = manager.get_messages()
        assert count == TokenEstimator.estimate_messages(messages)

    def test_get_message_count(self):
        """测试获取消息数量"""
        manager = ContextManager()

        assert manager.get_message_count() == 0

        manager.add_message("user", "Hello")
        assert manager.get_message_count() == 1

        manager.add_message("assistant", "Hi")
        assert manager.get_message_count() == 2

    def test_manual_compress(self):
        """测试手动压缩"""
        # 禁用自动压缩，以便测试手动压缩
        manager = ContextManager(max_tokens=30, keep_recent=2, auto_compress=False)

        # 添加足够长的消息以触发压缩
        for i in range(10):
            manager.add_message("user", f"This is a longer message number {i} with more content to exceed token limit")

        original_count = manager.get_message_count()

        manager.compress()

        assert manager.get_message_count() < original_count
        assert manager.get_message_count() <= 2  # keep_recent

    def test_auto_compress_enabled(self):
        """测试自动压缩启用"""
        # 使用低阈值触发自动压缩
        manager = ContextManager(
            max_tokens=50,
            compression_threshold=0.5,
            keep_recent=2,
            auto_compress=True,
        )

        # 添加足够多的消息触发压缩
        for i in range(10):
            manager.add_message("user", f"This is a longer message {i} that will trigger compression")

        # 应该自动压缩
        assert manager.get_message_count() <= 4  # system + keep_recent

    def test_auto_compress_disabled(self):
        """测试禁用自动压缩"""
        manager = ContextManager(auto_compress=False)

        for i in range(100):
            manager.add_message("user", f"Message {i}")

        # 不应自动压缩
        assert manager.get_message_count() == 100

    def test_clear_all(self):
        """测试清空所有消息"""
        manager = ContextManager()

        manager.add_message("system", "You are helpful")
        manager.add_message("user", "Hello")

        manager.clear(keep_system=False)

        assert manager.get_message_count() == 0

    def test_clear_keep_system(self):
        """测试清空时保留 system 消息"""
        manager = ContextManager()

        manager.add_message("system", "You are helpful")
        manager.add_message("user", "Hello")

        manager.clear(keep_system=True)

        messages = manager.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "system"

    def test_get_stats(self):
        """测试获取统计信息"""
        manager = ContextManager(max_tokens=1000)

        manager.add_message("system", "You are helpful")
        manager.add_message("user", "Hello")
        manager.add_message("assistant", "Hi there")

        stats = manager.get_stats()

        assert stats["message_count"] == 3
        assert stats["token_count"] > 0
        assert stats["max_tokens"] == 1000
        assert stats["role_counts"]["system"] == 1
        assert stats["role_counts"]["user"] == 1
        assert stats["role_counts"]["assistant"] == 1
        assert stats["compression_count"] == 0

    def test_get_compression_history(self):
        """测试获取压缩历史"""
        manager = ContextManager(max_tokens=50, keep_recent=2)

        for i in range(10):
            manager.add_message("user", f"Message {i}")

        # 手动触发压缩
        manager.compress()

        history = manager.get_compression_history()
        assert len(history) > 0
        assert "original_count" in history[0]
        assert "compressed_count" in history[0]

    def test_export_import_state(self):
        """测试导出和导入状态"""
        manager1 = ContextManager()

        manager1.add_message("system", "You are helpful")
        manager1.add_message("user", "Hello")
        manager1.add_message("assistant", "Hi")

        state = manager1.export_state()

        manager2 = ContextManager()
        manager2.import_state(state)

        assert manager2.get_message_count() == manager1.get_message_count()
        assert manager2.get_messages() == manager1.get_messages()

    def test_set_max_tokens(self):
        """测试设置最大 token 限制"""
        manager = ContextManager(max_tokens=1000)

        manager.set_max_tokens(500)

        assert manager.max_tokens == 500
        assert manager._compressor.max_tokens == 500

    def test_set_compression_threshold(self):
        """测试设置压缩阈值"""
        manager = ContextManager()

        manager.set_compression_threshold(0.7)

        assert manager.compression_threshold == 0.7
        assert manager._compressor.compression_threshold == 0.7

    def test_set_compression_threshold_invalid(self):
        """测试设置无效的压缩阈值"""
        manager = ContextManager()

        with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
            manager.set_compression_threshold(0)

        with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
            manager.set_compression_threshold(1.5)

    def test_set_keep_recent(self):
        """测试设置保留消息数量"""
        manager = ContextManager()

        manager.set_keep_recent(20)

        assert manager.keep_recent == 20
        assert manager._compressor.keep_recent == 20

    def test_compress_with_summary(self):
        """测试带摘要函数的压缩"""
        # 禁用自动压缩，以便测试手动压缩
        manager = ContextManager(max_tokens=30, keep_recent=2, auto_compress=False)

        for i in range(10):
            manager.add_message("user", f"This is a longer message {i} with enough content to trigger compression")

        def summary_func(msgs):
            return f"Compressed {len(msgs)} messages"

        messages, summary = manager.compress_with_summary(summary_func)

        assert summary is not None
        assert "Compressed" in summary
        assert manager.get_message_count() < 10

    def test_full_conversation_workflow(self):
        """测试完整的对话工作流"""
        manager = ContextManager(
            max_tokens=200,
            compression_threshold=0.7,
            keep_recent=5,
        )

        # 添加系统提示
        manager.add_message("system", "You are a helpful travel assistant")

        # 模拟对话
        manager.add_message("user", "我想去北京旅游")
        manager.add_message("assistant", "北京是个很棒的旅游目的地")

        for i in range(20):
            manager.add_message("user", f"问题 {i}")
            manager.add_message("assistant", f"回答 {i}")

        # 验证状态
        stats = manager.get_stats()
        assert stats["message_count"] > 0
        assert stats["role_counts"]["system"] == 1
        assert "user" in stats["role_counts"]
        assert "assistant" in stats["role_counts"]

        # 获取最近消息
        recent = manager.get_messages(max_count=5)
        assert len(recent) == 5

    def test_compression_preserves_integrity(self):
        """测试压缩保持消息完整性"""
        manager = ContextManager(max_tokens=50, keep_recent=3)

        messages_to_add = [
            ("system", "System prompt"),
            ("user", "Question 1"),
            ("assistant", "Answer 1"),
            ("user", "Question 2"),
            ("assistant", "Answer 2"),
            ("user", "Question 3"),
            ("assistant", "Answer 3"),
            ("user", "Latest question"),
            ("assistant", "Latest answer"),
        ]

        for role, content in messages_to_add:
            manager.add_message(role, content)

        original_system = [m for m in manager.get_messages() if m["role"] == "system"]
        manager.compress()

        # 验证 system 消息保留
        compressed_system = [m for m in manager.get_messages() if m["role"] == "system"]
        assert len(compressed_system) == len(original_system)

        # 验证最新消息保留
        messages = manager.get_messages()
        assert messages[-1]["content"] == "Latest answer"
