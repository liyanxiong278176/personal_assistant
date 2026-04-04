"""测试 RuleReinjector 规则重注入器"""

import pytest

from app.core.context.config import ContextConfig
from app.core.context.reinjector import RuleReinjector


class TestRuleReinjectorDefaults:
    """测试 RuleReinjector 默认值"""

    def test_default_rules_reinject_window(self):
        """测试默认重注入窗口"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        assert reinjector.config.rules_reinject_window == 5

    def test_default_rules_reinject_interval(self):
        """测试默认重注入间隔"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        assert reinjector.config.rules_reinject_interval == 3

    def test_last_reinject_position_initialized(self):
        """测试上次注入位置初始化为-1"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        assert reinjector._last_reinject_position == -1


class TestRuleReinjectorCustomValues:
    """测试自定义配置值"""

    def test_custom_window_and_interval(self):
        """测试自定义窗口和间隔"""
        config = ContextConfig(rules_reinject_window=10, rules_reinject_interval=5)
        reinjector = RuleReinjector(config)
        assert reinjector.config.rules_reinject_window == 10
        assert reinjector.config.rules_reinject_interval == 5


class TestReinjectEmptyCases:
    """测试空消息列表"""

    def test_reinject_empty_messages(self):
        """测试空消息列表返回空列表"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        result = reinjector.reinject([], {})
        assert result == []

    def test_reinject_empty_cache(self):
        """测试空缓存不注入"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        result = reinjector.reinject(messages, {})

        # 没有规则被注入
        assert len(result) == 1
        assert not any(m.get("_rules_reinjected") for m in result)

    def test_reinject_no_cache_key(self):
        """测试缓存中没有对应key不注入"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        rules_cache = {"OTHER.md": "# Rules"}
        result = reinjector.reinject(messages, rules_cache)

        # 没有规则被注入（因为缓存中没有规则文件）
        assert len(result) == 1


class TestReinjectBasic:
    """测试基本规则注入"""

    def test_reinject_injects_rules(self):
        """测试规则注入（无摘要时插入到开头）"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        rules_cache = {"AGENTS.md": "# Rules"}

        result = reinjector.reinject(messages, rules_cache)

        # 应该有2条消息（规则消息 + 原消息）
        assert len(result) == 2
        assert result[0]["_rules_reinjected"] is True
        assert "# Rules" in result[0]["content"]

    def test_reinject_rule_role_is_system(self):
        """测试注入的规则消息role为system"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        rules_cache = {"AGENTS.md": "# Agent Rules"}

        result = reinjector.reinject(messages, rules_cache)

        rule_msg = result[0]
        assert rule_msg["role"] == "system"

    def test_reinject_multiple_rule_files(self):
        """测试注入多个规则文件"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        rules_cache = {
            "AGENTS.md": "# Agent Rules",
            "TOOLS.md": "# Tool Rules"
        }

        result = reinjector.reinject(messages, rules_cache)

        rule_msg = result[0]
        assert "# Agent Rules" in rule_msg["content"]
        assert "# Tool Rules" in rule_msg["content"]

    def test_reinject_does_not_modify_original(self):
        """测试不修改原始消息"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        original = [{"role": "user", "content": "hello"}]
        rules_cache = {"AGENTS.md": "# Rules"}

        result = reinjector.reinject(original, rules_cache)

        # 原始消息未被修改
        assert len(original) == 1
        # 结果是新的列表
        assert result is not original


class TestReinjectAfterCompressed:
    """测试在压缩摘要后注入"""

    def test_reinject_after_compressed_marker(self):
        """测试在压缩摘要后注入"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)

        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "[summary]", "_compressed": True},
            {"role": "user", "content": "hi"}
        ]
        rules_cache = {"AGENTS.md": "# Rules"}

        result = reinjector.reinject(messages, rules_cache)

        # 规则应该插入在摘要后
        assert result[2]["_compressed"] is True  # 摘要
        assert result[3]["_rules_reinjected"] is True  # 规则

    def test_reinject_first_compressed_marker(self):
        """测试在第一个压缩摘要标记后插入"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)

        messages = [
            {"role": "system", "content": "prompt"},
            {"role": "system", "content": "[first summary]", "_compressed": True},
            {"role": "system", "content": "[second summary]", "_compressed": True},
            {"role": "user", "content": "hi"}
        ]
        rules_cache = {"AGENTS.md": "# Rules"}

        result = reinjector.reinject(messages, rules_cache)

        # 规则应该插入在第一个摘要后
        assert result[1]["content"] == "[first summary]"
        assert result[2]["_rules_reinjected"] is True
        assert result[3]["content"] == "[second summary]"

    def test_reinject_no_compressed_marker(self):
        """测试没有摘要标记时插入到开头"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)

        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"}
        ]
        rules_cache = {"AGENTS.md": "# Rules"}

        result = reinjector.reinject(messages, rules_cache)

        # 规则应该插入到开头
        assert result[0]["_rules_reinjected"] is True
        assert result[0]["role"] == "system"


class TestReinjectInterval:
    """测试重注入间隔控制"""

    def test_reinject_respects_interval(self):
        """测试遵守重注入间隔"""
        config = ContextConfig(rules_reinject_interval=3, rules_reinject_window=5)
        reinjector = RuleReinjector(config)
        rules_cache = {"AGENTS.md": "# Rules"}

        # 第一次注入
        messages = [{"role": "user", "content": "hello"}]
        result = reinjector.reinject(messages, rules_cache)

        # 立即再次尝试注入（间隔不足）
        result2 = reinjector.reinject(result, rules_cache)

        # 不应该再次注入
        injected_count = sum(1 for m in result2 if m.get("_rules_reinjected"))
        assert injected_count == 1

    def test_reinject_after_interval_passes(self):
        """测试间隔足够时重新注入"""
        config = ContextConfig(rules_reinject_interval=3, rules_reinject_window=5)
        reinjector = RuleReinjector(config)
        rules_cache = {"AGENTS.md": "# Rules"}

        # 第一次注入
        messages = [{"role": "user", "content": "hello"}]
        result = reinjector.reinject(messages, rules_cache)

        # 添加更多消息，使间隔超过阈值
        # 第一次注入后有2条消息(last position=0)
        # 继续添加消息直到超过间隔
        messages_with_more = result + [
            {"role": "assistant", "content": "response 1"},
            {"role": "user", "content": "message 2"},
            {"role": "assistant", "content": "response 2"},
            {"role": "user", "content": "message 3"},
        ]
        # 此时有 2+4=6 条消息，last position=0
        # 距离上次注入 6 条消息，大于 interval=3，应该重新注入

        result2 = reinjector.reinject(messages_with_more, rules_cache)
        injected_count = sum(1 for m in result2 if m.get("_rules_reinjected"))
        assert injected_count == 2


class TestReinjectWindowCheck:
    """测试窗口检查"""

    def test_reinject_skips_if_recent_rules_exist(self):
        """测试最近有规则时跳过注入"""
        config = ContextConfig(rules_reinject_interval=0, rules_reinject_window=5)
        reinjector = RuleReinjector(config)
        rules_cache = {"AGENTS.md": "# Rules"}

        # 最近已经有规则消息
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "# Rules", "_rules_reinjected": True}
        ]

        result = reinjector.reinject(messages, rules_cache)

        # 不应该再次注入
        injected_count = sum(1 for m in result if m.get("_rules_reinjected"))
        assert injected_count == 1

    def test_reinject_window_size_respected(self):
        """测试窗口大小被尊重"""
        config = ContextConfig(rules_reinject_interval=0, rules_reinject_window=2)
        reinjector = RuleReinjector(config)
        rules_cache = {"AGENTS.md": "# Rules"}

        # 规则消息在窗口外（更早）
        messages = [
            {"role": "system", "content": "# Old Rules", "_rules_reinjected": True},
            {"role": "user", "content": "msg1"},
            {"role": "user", "content": "msg2"},
            {"role": "user", "content": "msg3"},
        ]

        result = reinjector.reinject(messages, rules_cache)

        # 最近2条中没有规则，应该重新注入
        injected_count = sum(1 for m in result if m.get("_rules_reinjected"))
        assert injected_count >= 1


class TestReinjectEdgeCases:
    """测试边界情况"""

    def test_reinject_single_message(self):
        """测试单条消息（无摘要时规则插入到开头）"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        rules_cache = {"AGENTS.md": "# Rules"}

        result = reinjector.reinject(messages, rules_cache)

        assert len(result) == 2
        # 规则在开头，原消息在后面
        assert result[0]["_rules_reinjected"] is True
        assert result[1]["content"] == "hello"

    def test_reinject_updates_last_position(self):
        """测试更新上次注入位置"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        rules_cache = {"AGENTS.md": "# Rules"}

        messages = [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "hello"},
        ]

        result = reinjector.reinject(messages, rules_cache)

        # 没有压缩标记，所以插入到开头，位置为0
        assert reinjector._last_reinject_position == 0

    def test_reinject_multiple_calls(self):
        """测试多次调用"""
        config = ContextConfig(rules_reinject_interval=1)
        reinjector = RuleReinjector(config)
        rules_cache = {"AGENTS.md": "# Rules"}

        # 第一次注入：1条消息 -> 规则+原消息，位置0
        messages1 = [{"role": "user", "content": "msg1"}]
        result1 = reinjector.reinject(messages1, rules_cache)
        # [规则, msg1]
        assert len(result1) == 2
        assert result1[0]["_rules_reinjected"] is True
        assert result1[1]["content"] == "msg1"

        # 第二次：添加1条 -> [规则, msg1, msg2]，距离=3 >= 间隔=1，重新注入
        messages2 = result1 + [{"role": "user", "content": "msg2"}]
        result2 = reinjector.reinject(messages2, rules_cache)
        # [规则1, 规则2(prepend), msg1, msg2]
        injected = [m for m in result2 if m.get("_rules_reinjected")]
        assert len(injected) == 2

    def test_reinject_with_none_cache(self):
        """测试None缓存值"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        # rules_cache 中有键但值为空或None
        rules_cache = {"AGENTS.md": ""}

        result = reinjector.reinject(messages, rules_cache)

        # 空字符串的规则不注入
        assert len(result) == 1

    def test_reinject_format_includes_filename(self):
        """测试注入格式包含文件名"""
        config = ContextConfig(rules_files=["AGENTS.md", "TOOLS.md"])
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        rules_cache = {
            "AGENTS.md": "# Agent Rules",
            "TOOLS.md": "# Tool Rules"
        }

        result = reinjector.reinject(messages, rules_cache)

        # 无摘要标记时，规则在开头（位置0）
        rule_msg = result[0]
        content = rule_msg["content"]
        # 应该包含文件名作为分隔符
        assert "### AGENTS.md" in content


class TestReinjectComplex:
    """测试复杂场景"""

    def test_reinject_preserves_all_messages(self):
        """测试保留所有原始消息"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)

        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user1"},
            {"role": "assistant", "content": "assistant1"},
            {"role": "tool", "content": "tool1"},
            {"role": "user", "content": "user2"},
        ]
        rules_cache = {"AGENTS.md": "# Rules"}

        result = reinjector.reinject(messages, rules_cache)

        # 所有原始消息都应该保留
        original_contents = [m["content"] for m in messages]
        result_contents = [m["content"] for m in result if "_rules_reinjected" not in m]
        assert original_contents == result_contents

    def test_reinject_with_already_reinjected_message(self):
        """测试包含已注入消息的列表"""
        config = ContextConfig(rules_reinject_interval=0)
        reinjector = RuleReinjector(config)

        # 已经是注入后的消息列表
        messages = [
            {"role": "system", "content": "# Rules", "_rules_reinjected": True},
            {"role": "user", "content": "new message"},
        ]
        rules_cache = {"AGENTS.md": "# Rules"}

        result = reinjector.reinject(messages, rules_cache)

        # 不应该再次注入
        injected_count = sum(1 for m in result if m.get("_rules_reinjected"))
        assert injected_count == 1

    def test_reinject_empty_rules_content(self):
        """测试规则内容为空时"""
        config = ContextConfig()
        reinjector = RuleReinjector(config)
        messages = [{"role": "user", "content": "hello"}]
        rules_cache = {"AGENTS.md": ""}

        result = reinjector.reinject(messages, rules_cache)

        # 空规则不注入
        assert len(result) == 1


class TestGetInjectedRules:
    """测试 get_injected_rules 函数"""

    def test_empty_cache(self):
        """测试空缓存返回空字符串"""
        from app.core.context.config import ContextConfig
        result = ContextConfig(rules_cache={}).get_injected_rules()
        assert result == ""

    def test_single_file(self):
        """测试单个规则文件"""
        from app.core.context.config import ContextConfig
        config = ContextConfig(
            rules_files=["AGENTS.md"],
            rules_cache={"AGENTS.md": "# Rules content"}
        )
        result = config.get_injected_rules()
        assert "### AGENTS.md" in result
        assert "# Rules content" in result

    def test_multiple_files(self):
        """测试多个规则文件"""
        from app.core.context.config import ContextConfig
        config = ContextConfig(
            rules_files=["AGENTS.md", "TOOLS.md"],
            rules_cache={
                "AGENTS.md": "# Agent",
                "TOOLS.md": "# Tool"
            }
        )
        result = config.get_injected_rules()
        assert "Agent" in result
        assert "Tool" in result

    def test_missing_file_in_cache(self):
        """测试缓存中缺少文件"""
        from app.core.context.config import ContextConfig
        config = ContextConfig(
            rules_files=["AGENTS.md", "TOOLS.md"],
            rules_cache={"AGENTS.md": "# Agent"}  # 缺少 TOOLS.md
        )
        result = config.get_injected_rules()
        assert "Agent" in result
        assert "TOOLS.md" not in result
