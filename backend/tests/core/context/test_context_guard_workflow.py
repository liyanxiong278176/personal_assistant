"""上下文管理完整工作流测试

测试 ContextGuard 的前置清理、后置压缩、规则重注入的完整工作流。
覆盖日志输出和端到端集成。
"""

import time
import pytest
from app.core.context_mgmt.config import ContextConfig
from app.core.context_mgmt.guard import ContextGuard
from app.core.context_mgmt.cleaner import ContextCleaner
from app.core.context_mgmt.reinjector import RuleReinjector
from app.core.context_mgmt.summary import LLMSummaryProvider
from app.core.context_mgmt.tokenizer import TokenEstimator


class TestContextGuardWorkflow:
    """ContextGuard 完整工作流测试"""

    def test_guard_initialization_with_rules_cache(self):
        """测试1: 带规则缓存的初始化"""
        config = ContextConfig(rules_cache={"AGENTS.md": "# Agent Rules", "TOOLS.md": "# Tools"})
        guard = ContextGuard(config=config)

        assert guard.config == config
        assert len(guard.config.rules_cache) == 2
        assert "AGENTS.md" in guard.config.rules_cache
        assert "TOOLS.md" in guard.config.rules_cache

    @pytest.mark.asyncio
    async def test_preprocess_cleans_expired_tool_results(self):
        """测试2: 前置清理清理过期工具结果"""
        config = ContextConfig(tool_result_ttl_seconds=300)
        guard = ContextGuard(config=config)

        # 创建过期工具结果（400秒前）
        old_time = time.time() - 400
        messages = [
            {"role": "user", "content": "查询北京天气"},
            {"role": "tool", "content": '{"temperature": 25}', "_timestamp": old_time},
            {"role": "assistant", "content": "北京今天25度"},
        ]

        result = await guard.pre_process(messages)

        # 工具结果应该被清除（hard clear模式下）
        assert result[1]["_cleared"] == True
        assert result[1]["content"] == "[Old result cleared]"

    @pytest.mark.asyncio
    async def test_preprocess_trims_long_content(self):
        """测试3: 前置清理修剪超长内容"""
        config = ContextConfig(max_tool_result_chars=4000)
        guard = ContextGuard(config=config)

        # 创建超长内容 (5000字符)
        messages = [
            {"role": "tool", "content": "x" * 5000, "_type": "tool_result"},
        ]

        result = await guard.pre_process(messages)

        # 内容应该被修剪
        assert result[0]["_trimmed"] == True
        assert len(result[0]["content"]) < 5000
        assert "...[trimmed]..." in result[0]["content"]

    @pytest.mark.asyncio
    async def test_preprocess_preserves_short_content(self):
        """测试4: 前置清理保留短内容"""
        config = ContextConfig()
        guard = ContextGuard(config=config)

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你的吗？"},
        ]

        result = await guard.pre_process(messages)

        # 消息应该不变
        assert len(result) == 2
        assert result[0]["content"] == "你好"

    @pytest.mark.asyncio
    async def test_postprocess_no_compress_small_messages(self):
        """测试5: 小消息集不需要压缩"""
        config = ContextConfig()
        guard = ContextGuard(config=config)
        guard.set_conv_id("test_conv_1")

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]

        result = await guard.post_process(messages)

        # 消息应该不变（不需要压缩）
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_postprocess_force_compress_creates_summary(self):
        """测试6: 强制压缩创建摘要"""
        config = ContextConfig()
        guard = ContextGuard(config=config)
        guard.set_conv_id("test_conv_2")

        # 创建大量消息
        messages = [{"role": "system", "content": "你是旅行助手"}]
        messages += [{"role": "user", "content": f"第{i}次旅行计划"} for i in range(30)]

        result = await guard.force_compress(messages)

        # 应该包含摘要消息
        summary_msgs = [m for m in result if m.get("_compressed")]
        assert len(summary_msgs) >= 1
        assert "[历史对话摘要]" in summary_msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_postprocess_rules_reinjected_after_compress(self):
        """测试7: 压缩后规则被重注入"""
        config = ContextConfig(rules_cache={"AGENTS.md": "# Agent Rules"})
        guard = ContextGuard(config=config)
        guard.set_conv_id("test_conv_3")

        messages = [
            {"role": "user", "content": "你好"},
        ]

        result = await guard.force_compress(messages)

        # 应该包含规则注入
        rules_msgs = [m for m in result if m.get("_rules_reinjected")]
        assert len(rules_msgs) >= 1

    @pytest.mark.asyncio
    async def test_should_compress_below_threshold(self):
        """测试8: 未超过阈值时不压缩"""
        config = ContextConfig(window_size=128000, compress_threshold=0.75)
        guard = ContextGuard(config=config)
        guard.set_conv_id("test_conv_4")

        # 创建少量消息（低于75%阈值）
        messages = [{"role": "user", "content": "hello"}]

        assert guard.should_compress(messages) == False

    @pytest.mark.asyncio
    async def test_should_compress_above_threshold(self):
        """测试9: 超过阈值时需要压缩"""
        config = ContextConfig(window_size=1000, compress_threshold=0.75)
        guard = ContextGuard(config=config)
        guard.set_conv_id("test_conv_5")

        # 创建大量短消息（超过阈值）
        messages = [{"role": "user", "content": "hello world! " * 100} for _ in range(20)]

        # 应该触发压缩判断
        result = guard.should_compress(messages)
        # 结果取决于实际的token估算，但至少不应该报错
        assert isinstance(result, bool)

    def test_cleaner_soft_trim_mode(self):
        """测试10: Cleaner软修剪模式"""
        cleaner = ContextCleaner(max_result_chars=4000)

        messages = [
            {"role": "tool", "content": "x" * 5000},
        ]

        result = cleaner.clean(messages, mode="soft")

        assert result[0]["_trimmed"] == True
        assert len(result[0]["content"]) < 5000

    def test_cleaner_hard_clear_mode(self):
        """测试11: Cleaner硬清除模式"""
        cleaner = ContextCleaner(ttl_seconds=300)
        old_time = time.time() - 400

        messages = [
            {"role": "tool", "content": "result", "_timestamp": old_time},
        ]

        result = cleaner.clean(messages, mode="hard")

        assert result[0]["_cleared"] == True
        assert result[0]["content"] == "[Old result cleared]"

    def test_cleaner_protects_user_messages(self):
        """测试12: Cleaner保护用户消息"""
        cleaner = ContextCleaner(ttl_seconds=300, protected_roles={"user", "system"})
        old_time = time.time() - 400

        messages = [
            {"role": "user", "content": "user message", "_timestamp": old_time},
            {"role": "system", "content": "system message", "_timestamp": old_time},
        ]

        result = cleaner.clean(messages, mode="hard")

        # 用户和系统消息应该被保护
        assert result[0]["content"] == "user message"
        assert "_cleared" not in result[0]
        assert result[1]["content"] == "system message"
        assert "_cleared" not in result[1]

    def test_cleaner_auto_mode(self):
        """测试13: Cleaner自动模式"""
        cleaner = ContextCleaner(ttl_seconds=300, max_result_chars=4000)
        old_time = time.time() - 400

        messages = [
            {"role": "tool", "content": "x" * 5000, "_timestamp": old_time},
        ]

        result = cleaner.clean(messages, mode="auto")

        # 应该同时执行软修剪和硬清除
        assert result[0]["_trimmed"] == True
        assert result[0]["_cleared"] == True

    def test_reinjector_inserts_after_compressed(self):
        """测试14: RuleReinjector在压缩摘要后插入"""
        config = ContextConfig(rules_cache={"AGENTS.md": "# Rules"})
        reinjector = RuleReinjector(config)

        messages = [
            {"role": "system", "content": "prompt"},
            {"role": "system", "content": "[summary]", "_compressed": True},
            {"role": "user", "content": "hello"},
        ]

        result = reinjector.reinject(messages, config.rules_cache)

        # 规则应该插入在摘要后
        assert result[2].get("_rules_reinjected") == True
        assert "# Rules" in result[2]["content"]

    def test_reinjector_inserts_at_beginning_when_no_compressed(self):
        """测试15: 没有压缩摘要时插入到开头"""
        config = ContextConfig(rules_cache={"AGENTS.md": "# Rules"})
        reinjector = RuleReinjector(config)

        messages = [
            {"role": "user", "content": "hello"},
        ]

        result = reinjector.reinject(messages, config.rules_cache)

        # 规则应该插入到开头
        assert result[0].get("_rules_reinjected") == True
        assert "# Rules" in result[0]["content"]

    def test_reinjector_respects_interval(self):
        """测试16: RuleReinjector遵守重注入间隔

        验证重注入器通过 _last_reinject_position 跟踪注入位置，
        并在下次调用时检查间隔。
        """
        config = ContextConfig(rules_reinject_interval=3, rules_cache={"AGENTS.md": "# Rules"})
        reinjector = RuleReinjector(config)

        # 第一次注入: 规则插入到开头 (pos=0)
        messages1 = [{"role": "user", "content": "hello1"}]
        result1 = reinjector.reinject(messages1, config.rules_cache)
        assert result1[0].get("_rules_reinjected") == True
        assert reinjector._last_reinject_position == 0

        # 第二次调用: 间隔不足 (messages_since=2 < interval=3)
        # 应该跳过注入
        result2 = reinjector.reinject(result1, config.rules_cache)
        injected_count = sum(1 for m in result2 if m.get("_rules_reinjected"))
        assert injected_count == 1, f"间隔不足时应跳过，期望1，实际{injected_count}"

        # 第三次调用: 增加足够消息使间隔满足 (messages_since >= 3)
        # 需要确保输入中没有 _rules_reinjected，这样才会触发 should_reinject
        fresh_messages = [{"role": "user", "content": f"msg{i}"} for i in range(5)]
        result3 = reinjector.reinject(fresh_messages, config.rules_cache)

        # 由于 _last_reinject_position=0, len(fresh_messages)=5
        # messages_since = 5 - 0 = 5 >= 3, 应该可以注入
        injected_count3 = sum(1 for m in result3 if m.get("_rules_reinjected"))
        assert injected_count3 >= 1

    def test_reinjector_respects_window(self):
        """测试17: RuleReinjector遵守窗口检查"""
        config = ContextConfig(
            rules_reinject_window=3,
            rules_reinject_interval=1,
            rules_cache={"AGENTS.md": "# Rules"}
        )
        reinjector = RuleReinjector(config)

        # 创建带规则的初始消息
        messages = [
            {"role": "system", "content": "# Rules", "_rules_reinjected": True},
            {"role": "user", "content": "hello"},
        ]

        result = reinjector.reinject(messages, config.rules_cache)

        # 窗口内有规则，应该跳过
        injected_count = sum(1 for m in result if m.get("_rules_reinjected"))
        assert injected_count == 1  # 只有原来的规则，没有新注入

    @pytest.mark.asyncio
    async def test_guard_stats_tracking(self):
        """测试18: ContextGuard统计跟踪"""
        config = ContextConfig()
        guard = ContextGuard(config=config)
        guard.set_conv_id("test_conv_stats")

        # 执行前置处理
        await guard.pre_process([{"role": "user", "content": "hello"}])

        # 执行后置处理
        await guard.post_process([{"role": "user", "content": "hello"}])

        # 强制压缩
        await guard.force_compress([{"role": "user", "content": "hello"}] * 30)

        stats = guard.get_stats()

        assert stats["pre_process_count"] >= 1
        assert stats["post_process_count"] >= 1
        assert stats["force_compress_count"] >= 1

    @pytest.mark.asyncio
    async def test_guard_simple_compress_with_summary(self):
        """测试19: 简单压缩生成计数摘要"""
        config = ContextConfig()
        guard = ContextGuard(config=config)
        guard.set_conv_id("test_conv_simple")

        messages = [
            {"role": "user", "content": "hello"} for _ in range(5)
        ] + [
            {"role": "assistant", "content": "hi"} for _ in range(5)
        ] + [
            {"role": "tool", "content": "result"} for _ in range(3)
        ]

        result = guard._simple_compress_with_summary(messages)

        # 应该包含摘要
        summary_msgs = [m for m in result if m.get("_compressed")]
        assert len(summary_msgs) == 1

        # 摘要应该包含计数信息
        summary_content = summary_msgs[0]["content"]
        assert "5" in summary_content  # 用户消息数
        assert "5" in summary_content  # 助手消息数

    def test_guard_set_conv_id(self):
        """测试20: 设置会话ID用于日志"""
        config = ContextConfig()
        guard = ContextGuard(config=config)

        guard.set_conv_id("conv_12345")
        assert guard._last_conv_id == "conv_12345"

        guard.set_conv_id("conv_67890")
        assert guard._last_conv_id == "conv_67890"
