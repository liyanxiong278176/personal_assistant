"""测试 ContextGuard 主类

测试上下文守卫的前置清理、后置管理、压缩判断等核心功能。
"""

import pytest

from app.core.context.config import ContextConfig
from app.core.context.tokenizer import TokenEstimator


# Test data fixtures
def _make_messages(count: int, role: str = "user") -> list:
    """Helper: create N messages with placeholder content."""
    return [
        {"role": role, "content": f"Message {i} " + "x" * 100}
        for i in range(count)
    ]


def _make_tool_message(content: str, timestamp: float | None = None) -> dict:
    """Helper: create a tool message."""
    msg = {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "test_tool",
        "content": content,
    }
    if timestamp is not None:
        msg["_timestamp"] = timestamp
    return msg


class TestContextGuardInit:
    """测试 ContextGuard 初始化"""

    def test_init_with_default_config(self):
        """测试默认配置初始化"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        assert guard.config is not None
        assert guard.config.window_size == 128000
        assert guard.config.compress_threshold == 0.75

    def test_init_with_custom_config(self):
        """测试自定义配置初始化"""
        from app.core.context.guard import ContextGuard

        config = ContextConfig(
            window_size=64000,
            compress_threshold=0.5,
        )
        guard = ContextGuard(config=config)
        assert guard.config.window_size == 64000
        assert guard.config.compress_threshold == 0.5

    def test_init_creates_sub_components(self):
        """测试子组件被正确创建"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        assert guard.cleaner is not None
        assert guard.compressor is not None
        assert guard.reinjector is not None


class TestShouldCompress:
    """测试压缩判断功能"""

    def test_under_threshold_not_compress(self):
        """测试低于阈值时不触发压缩"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard(config=ContextConfig(compress_threshold=0.75))

        # 很少的消息，应该不会触发压缩
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        assert guard.should_compress(messages) is False

    def test_over_threshold_should_compress(self):
        """测试超过阈值时触发压缩"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard(config=ContextConfig(compress_threshold=0.75, window_size=128000))

        # 创建足够多的消息以超过 75% 阈值
        # 每个消息约 25-30 tokens, 75% of 128000 = 96000
        # 需要约 3200+ 条消息（太慢，改用小 window）
        config = ContextConfig(window_size=1000, compress_threshold=0.3)
        guard = ContextGuard(config=config)

        # 100 chars per msg ~ 25 tokens each; 40 msgs ~ 1000 tokens > 300 threshold
        messages = _make_messages(40, "user")
        assert guard.should_compress(messages) is True

    def test_exactly_at_threshold(self):
        """测试刚好在阈值边界"""
        from app.core.context.guard import ContextGuard

        # 使用小阈值来精确控制
        config = ContextConfig(window_size=1000, compress_threshold=0.2)
        guard = ContextGuard(config=config)

        # 约 20 msgs ~ 500 tokens, threshold 200 -> should compress
        messages = _make_messages(20, "user")
        # 20 * 25 = 500 tokens, 75% of 1000 = 750... actually 20 might not reach
        # Let's check: 20 msgs with 100 char content each
        # Estimate: each msg ~4 + 25 = 29 tokens, 20*29 = 580, threshold = 200
        # Actually 0.2 * 1000 = 200, so 580 > 200 -> should compress
        assert guard.should_compress(messages) is True

    def test_empty_messages_not_compress(self):
        """测试空消息列表不触发压缩"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        assert guard.should_compress([]) is False


class TestPreProcess:
    """测试前置处理功能"""

    @pytest.mark.asyncio
    async def test_pre_process_calls_cleaner(self):
        """测试前置处理调用清理器"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        messages = [
            {"role": "user", "content": "Hello"},
            _make_tool_message("Tool result"),
        ]

        result = await guard.pre_process(messages)
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_pre_process_does_not_modify_original(self):
        """测试前置处理不修改原始列表"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        original = [
            {"role": "user", "content": "Hello"},
            _make_tool_message("Tool result"),
        ]
        original_copy = [m.copy() for m in original]

        await guard.pre_process(original)
        assert original == original_copy

    @pytest.mark.asyncio
    async def test_pre_process_empty_list(self):
        """测试前置处理空列表"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        result = await guard.pre_process([])
        assert result == []


class TestPostProcess:
    """测试后置处理功能"""

    @pytest.mark.asyncio
    async def test_post_process_compresses_when_needed(self):
        """测试后置处理在需要时压缩"""
        from app.core.context.guard import ContextGuard

        config = ContextConfig(window_size=1000, compress_threshold=0.3)
        guard = ContextGuard(config=config)

        messages = _make_messages(40, "user")

        result = await guard.post_process(messages)
        assert isinstance(result, list)
        # 压缩后消息数量应该减少
        assert len(result) < len(messages)

    @pytest.mark.asyncio
    async def test_post_process_no_compress_when_not_needed(self):
        """测试后置处理在不需要时不压缩"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        result = await guard.post_process(messages)
        # 小列表不会被压缩
        assert result == messages

    @pytest.mark.asyncio
    async def test_post_process_injects_rules_after_compress(self):
        """测试压缩后注入规则"""
        from app.core.context.guard import ContextGuard

        config = ContextConfig(
            window_size=1000,
            compress_threshold=0.3,
            rules_cache={"AGENTS.md": "Agent rules content"},
            rules_files=["AGENTS.md"],
        )
        guard = ContextGuard(config=config)

        messages = _make_messages(40, "user")

        result = await guard.post_process(messages)
        # 检查是否有规则被注入
        has_rules = any(
            m.get("_rules_reinjected") for m in result
        )
        assert has_rules is True

    @pytest.mark.asyncio
    async def test_post_process_empty_list(self):
        """测试后置处理空列表"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        result = await guard.post_process([])
        assert result == []


class TestForceCompress:
    """测试强制压缩功能"""

    @pytest.mark.asyncio
    async def test_force_compress_reduces_messages(self):
        """测试强制压缩减少消息数量"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        messages = _make_messages(30, "user")

        result = await guard.force_compress(messages)
        assert isinstance(result, list)
        assert len(result) < len(messages)

    @pytest.mark.asyncio
    async def test_force_compress_empty_list(self):
        """测试强制压缩空列表"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        result = await guard.force_compress([])
        assert result == []

    @pytest.mark.asyncio
    async def test_force_compress_injects_rules(self):
        """测试强制压缩后注入规则"""
        from app.core.context.guard import ContextGuard

        config = ContextConfig(
            rules_cache={"TOOLS.md": "Tool usage rules"},
            rules_files=["TOOLS.md"],
        )
        guard = ContextGuard(config=config)

        messages = _make_messages(30, "user")

        result = await guard.force_compress(messages)
        has_rules = any(
            m.get("_rules_reinjected") for m in result
        )
        assert has_rules is True


class TestSimpleCompress:
    """测试简单压缩方法"""

    def test_simple_compress_preserves_system(self):
        """测试简单压缩保留系统消息"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        messages = [
            {"role": "system", "content": "System prompt"},
            *_make_messages(20, "user"),
        ]

        result = guard._simple_compress_with_summary(messages)
        assert any(m["role"] == "system" for m in result)

    def test_simple_compress_adds_summary(self):
        """测试简单压缩添加摘要消息"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        messages = [
            {"role": "system", "content": "System prompt"},
            *_make_messages(20, "user"),
        ]

        result = guard._simple_compress_with_summary(messages)
        # 应该有一条包含 _compressed 标记的消息
        has_compressed = any(m.get("_compressed") for m in result)
        assert has_compressed is True

    def test_simple_compress_keeps_recent_messages(self):
        """测试简单压缩保留最近消息"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        # 创建消息，标记最后几条
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Message 0"},
            {"role": "assistant", "content": "Reply 0"},
            {"role": "user", "content": "Message 10"},
            {"role": "assistant", "content": "Reply 10"},
            {"role": "user", "content": "RECENT_MESSAGE"},
        ]

        result = guard._simple_compress_with_summary(messages)
        # 最近的消息应该保留
        assert any("RECENT_MESSAGE" in m.get("content", "") for m in result)

    def test_simple_compress_empty_list(self):
        """测试简单压缩空列表"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        result = guard._simple_compress_with_summary([])
        assert result == []


class TestGetStats:
    """测试统计信息功能"""

    def test_get_stats_returns_dict(self):
        """测试 get_stats 返回字典"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()
        stats = guard.get_stats()
        assert isinstance(stats, dict)

    def test_stats_contains_expected_keys(self):
        """测试统计信息包含预期键"""
        from app.core.context.guard import ContextGuard

        config = ContextConfig(window_size=64000, compress_threshold=0.5)
        guard = ContextGuard(config=config)

        stats = guard.get_stats()
        assert "window_size" in stats
        assert "compress_threshold" in stats
        assert "sub_components" in stats

    def test_stats_reflects_config(self):
        """测试统计信息反映配置"""
        from app.core.context.guard import ContextGuard

        config = ContextConfig(window_size=64000, compress_threshold=0.5)
        guard = ContextGuard(config=config)

        stats = guard.get_stats()
        assert stats["window_size"] == 64000
        assert stats["compress_threshold"] == 0.5


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_pre_then_post_process(self):
        """测试先预处理再后处理"""
        from app.core.context.guard import ContextGuard

        guard = ContextGuard()

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            *_make_messages(5, "user"),
        ]

        # 先预处理
        pre_result = await guard.pre_process(messages)
        assert pre_result is not None

        # 后处理
        post_result = await guard.post_process(pre_result)
        assert post_result is not None

    @pytest.mark.asyncio
    async def test_full_workflow_with_large_context(self):
        """测试大上下文完整工作流"""
        from app.core.context.guard import ContextGuard

        config = ContextConfig(window_size=1000, compress_threshold=0.3)
        guard = ContextGuard(config=config)

        # 模拟长对话历史
        messages = [
            {"role": "system", "content": "You are a travel assistant."},
        ]
        for i in range(50):
            messages.append({"role": "user", "content": f"User question {i} " + "x" * 50})
            messages.append({"role": "assistant", "content": f"Response {i} " + "y" * 50})

        # 预处理
        pre_result = await guard.pre_process(messages)

        # 检查是否需要压缩
        if guard.should_compress(pre_result):
            post_result = await guard.post_process(pre_result)
            assert len(post_result) < len(pre_result)
        else:
            post_result = pre_result

        # 统计
        stats = guard.get_stats()
        assert "window_size" in stats
        assert "compress_threshold" in stats
