"""测试 ContextConfig 配置类"""

import json
import os
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.core.context.config import (
    ContextConfig,
    load_config_from_env,
    get_default_config,
)


class TestContextConfigDefaults:
    """测试 ContextConfig 默认值"""

    def test_default_window_size(self):
        """测试默认窗口大小"""
        config = ContextConfig()
        assert config.window_size == 128000

    def test_default_soft_trim_ratio(self):
        """测试默认软修剪比例"""
        config = ContextConfig()
        assert config.soft_trim_ratio == 0.3

    def test_default_hard_clear_ratio(self):
        """测试默认硬清除比例"""
        config = ContextConfig()
        assert config.hard_clear_ratio == 0.5

    def test_default_compress_threshold(self):
        """测试默认压缩阈值"""
        config = ContextConfig()
        assert config.compress_threshold == 0.75

    def test_default_tool_result_ttl(self):
        """测试默认工具结果 TTL"""
        config = ContextConfig()
        assert config.tool_result_ttl_seconds == 300

    def test_default_max_tool_result_chars(self):
        """测试默认最大工具结果字符数"""
        config = ContextConfig()
        assert config.max_tool_result_chars == 4000

    def test_default_summary_model(self):
        """测试默认摘要模型"""
        config = ContextConfig()
        assert config.summary_model == "deepseek-chat"

    def test_default_max_summary_retries(self):
        """测试默认最大摘要重试次数"""
        config = ContextConfig()
        assert config.max_summary_retries == 3

    def test_default_rules_files(self):
        """测试默认规则文件列表"""
        config = ContextConfig()
        assert config.rules_files == ["AGENTS.md", "TOOLS.md"]

    def test_default_rules_cache(self):
        """测试默认规则缓存为空字典"""
        config = ContextConfig()
        assert config.rules_cache == {}

    def test_default_protected_message_types(self):
        """测试默认保护的消息类型"""
        config = ContextConfig()
        assert config.protected_message_types == ["user", "system", "image"]


class TestContextConfigImmutability:
    """测试 ContextConfig 不可变性"""

    def test_frozen_dataclass(self):
        """测试 dataclass 为 frozen，不可修改"""
        config = ContextConfig()
        with pytest.raises(FrozenInstanceError):
            config.window_size = 64000

    def test_cannot_modify_rules_cache(self):
        """测试不能修改 rules_cache 字段本身"""
        config = ContextConfig(rules_cache={"test": "content"})
        with pytest.raises(FrozenInstanceError):
            config.rules_cache = {}

    def test_can_modify_cache_contents(self):
        """测试可以修改缓存字典的内容（非冻结字段）"""
        config = ContextConfig(rules_cache={"test": "content"})
        # 字典本身不是 frozen，可以修改内容
        config.rules_cache["new_key"] = "new_value"
        assert config.rules_cache["new_key"] == "new_value"


class TestContextConfigCustomValues:
    """测试自定义配置值"""

    def test_custom_window_size(self):
        """测试自定义窗口大小"""
        config = ContextConfig(window_size=64000)
        assert config.window_size == 64000

    def test_custom_ratios(self):
        """测试自定义比例"""
        config = ContextConfig(
            soft_trim_ratio=0.2,
            hard_clear_ratio=0.4,
            compress_threshold=0.8
        )
        assert config.soft_trim_ratio == 0.2
        assert config.hard_clear_ratio == 0.4
        assert config.compress_threshold == 0.8

    def test_custom_rules_files(self):
        """测试自定义规则文件列表"""
        config = ContextConfig(rules_files=["CUSTOM.md"])
        assert config.rules_files == ["CUSTOM.md"]

    def test_custom_protected_types(self):
        """测试自定义保护的消息类型"""
        config = ContextConfig(protected_message_types=["user", "system"])
        assert config.protected_message_types == ["user", "system"]
        assert "image" not in config.protected_message_types


class TestLoadRulesAtStartup:
    """测试启动时加载规则文件"""

    def test_load_single_file(self):
        """测试加载单个规则文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_file = Path(tmpdir) / "AGENTS.md"
            rules_file.write_text("# Agent Rules\n\nRule 1: Be helpful")

            cache = ContextConfig.load_rules_at_startup(Path(tmpdir))
            assert "AGENTS.md" in cache
            assert "Agent Rules" in cache["AGENTS.md"]

    def test_load_multiple_files(self):
        """测试加载多个规则文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_file = Path(tmpdir) / "AGENTS.md"
            tools_file = Path(tmpdir) / "TOOLS.md"
            agents_file.write_text("# Agent Rules")
            tools_file.write_text("# Tool Rules")

            config = ContextConfig(
                rules_files=["AGENTS.md", "TOOLS.md"],
                rules_cache=ContextConfig.load_rules_at_startup(Path(tmpdir))
            )
            assert "AGENTS.md" in config.rules_cache
            assert "TOOLS.md" in config.rules_cache

    def test_load_nonexistent_file(self):
        """测试加载不存在的文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ContextConfig.load_rules_at_startup(Path(tmpdir))
            # 不存在的文件应该被跳过
            assert cache == {}

    def test_load_with_config_instance(self):
        """测试使用配置实例加载规则"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_file = Path(tmpdir) / "AGENTS.md"
            rules_file.write_text("# Rules")

            cache = ContextConfig.load_rules_at_startup(Path(tmpdir))
            config = ContextConfig(rules_cache=cache)
            assert config.rules_cache["AGENTS.md"] == "# Rules"


class TestGetInjectedRules:
    """测试获取注入的规则"""

    def test_empty_cache_returns_empty_string(self):
        """测试空缓存返回空字符串"""
        config = ContextConfig(rules_cache={})
        assert config.get_injected_rules() == ""

    def test_single_rule_file(self):
        """测试单个规则文件注入"""
        config = ContextConfig(rules_cache={"AGENTS.md": "# Agent Rules"})
        injected = config.get_injected_rules()
        assert "Agent Rules" in injected
        assert "AGENTS.md" in injected

    def test_multiple_rule_files(self):
        """测试多个规则文件注入"""
        config = ContextConfig(
            rules_files=["AGENTS.md", "TOOLS.md"],
            rules_cache={
                "AGENTS.md": "# Agent Rules",
                "TOOLS.md": "# Tool Rules"
            }
        )
        injected = config.get_injected_rules()
        assert "Agent Rules" in injected
        assert "Tool Rules" in injected

    def test_injection_format(self):
        """测试注入格式包含文件名"""
        config = ContextConfig(
            rules_files=["AGENTS.md"],
            rules_cache={"AGENTS.md": "# Rules"}
        )
        injected = config.get_injected_rules()
        # 应该包含文件名作为分隔符
        assert "AGENTS.md" in injected
        assert "# Rules" in injected


class TestLoadConfigFromEnv:
    """测试从环境变量加载配置"""

    def test_load_window_size_from_env(self):
        """测试从环境变量加载窗口大小"""
        os.environ["CONTEXT_WINDOW_SIZE"] = "64000"
        try:
            config = load_config_from_env()
            assert config.window_size == 64000
        finally:
            del os.environ["CONTEXT_WINDOW_SIZE"]

    def test_load_compress_threshold_from_env(self):
        """测试从环境变量加载压缩阈值"""
        os.environ["COMPRESS_THRESHOLD"] = "0.8"
        try:
            config = load_config_from_env()
            assert config.compress_threshold == 0.8
        finally:
            del os.environ["COMPRESS_THRESHOLD"]

    def test_load_ttl_from_env(self):
        """测试从环境变量加载 TTL"""
        os.environ["TOOL_RESULT_TTL"] = "600"
        try:
            config = load_config_from_env()
            assert config.tool_result_ttl_seconds == 600
        finally:
            del os.environ["TOOL_RESULT_TTL"]

    def test_env_missing_uses_defaults(self):
        """测试环境变量缺失时使用默认值"""
        # 确保环境变量不存在
        for key in ["CONTEXT_WINDOW_SIZE", "COMPRESS_THRESHOLD", "TOOL_RESULT_TTL"]:
            os.environ.pop(key, None)

        config = load_config_from_env()
        assert config.window_size == 128000
        assert config.compress_threshold == 0.75
        assert config.tool_result_ttl_seconds == 300

    def test_invalid_env_value_uses_default(self):
        """测试无效的环境变量值使用默认值"""
        os.environ["CONTEXT_WINDOW_SIZE"] = "invalid"
        try:
            config = load_config_from_env()
            # 无效值应该回退到默认值
            assert config.window_size == 128000
        finally:
            del os.environ["CONTEXT_WINDOW_SIZE"]


class TestGetDefaultConfig:
    """测试获取默认配置"""

    def test_returns_context_config_instance(self):
        """测试返回 ContextConfig 实例"""
        config = get_default_config()
        assert isinstance(config, ContextConfig)

    def test_has_all_defaults(self):
        """测试包含所有默认值"""
        config = get_default_config()
        assert config.window_size == 128000
        assert config.soft_trim_ratio == 0.3
        assert config.compress_threshold == 0.75

    def test_empty_rules_cache(self):
        """测试默认配置规则缓存为空"""
        config = get_default_config()
        assert config.rules_cache == {}


class TestContextConfigValidation:
    """测试配置验证"""

    def test_soft_trim_less_than_hard_clear(self):
        """测试软修剪比例应该小于硬清除比例"""
        config = ContextConfig(soft_trim_ratio=0.2, hard_clear_ratio=0.4)
        # 这是有效配置
        assert config.soft_trim_ratio < config.hard_clear_ratio

    def test_hard_clear_less_than_compress(self):
        """测试硬清除比例应该小于压缩阈值"""
        config = ContextConfig(hard_clear_ratio=0.4, compress_threshold=0.7)
        # 这是有效配置
        assert config.hard_clear_ratio < config.compress_threshold

    def test_ratios_within_valid_range(self):
        """测试比例值在有效范围内 (0-1)"""
        config = ContextConfig()
        assert 0 < config.soft_trim_ratio <= 1
        assert 0 < config.hard_clear_ratio <= 1
        assert 0 < config.compress_threshold <= 1

    def test_positive_ttl(self):
        """测试 TTL 为正数"""
        config = ContextConfig()
        assert config.tool_result_ttl_seconds > 0

    def test_positive_max_chars(self):
        """测试最大字符数为正数"""
        config = ContextConfig()
        assert config.max_tool_result_chars > 0

    def test_positive_window_size(self):
        """测试窗口大小为正数"""
        config = ContextConfig()
        assert config.window_size > 0


class TestContextConfigEquality:
    """测试配置相等性"""

    def test_same_configs_equal(self):
        """测试相同配置相等"""
        config1 = ContextConfig(window_size=128000)
        config2 = ContextConfig(window_size=128000)
        assert config1 == config2

    def test_different_configs_not_equal(self):
        """测试不同配置不相等"""
        config1 = ContextConfig(window_size=128000)
        config2 = ContextConfig(window_size=64000)
        assert config1 != config2

    def test_rules_cache_affects_equality(self):
        """测试规则缓存影响相等性"""
        config1 = ContextConfig(rules_cache={"test": "content"})
        config2 = ContextConfig(rules_cache={})
        assert config1 != config2


class TestContextConfigHelperFunctions:
    """测试辅助函数"""

    def test_get_default_config_creates_new_instance(self):
        """测试每次调用创建新实例"""
        config1 = get_default_config()
        config2 = get_default_config()
        assert config1 is not config2

    def test_load_config_from_env_creates_new_instance(self):
        """测试从环境变量加载创建新实例"""
        config1 = load_config_from_env()
        config2 = load_config_from_env()
        assert config1 is not config2

    def test_load_config_without_env(self):
        """测试无环境变量时加载配置"""
        # 清除相关环境变量
        env_backup = {}
        for key in ["CONTEXT_WINDOW_SIZE", "COMPRESS_THRESHOLD", "TOOL_RESULT_TTL"]:
            if key in os.environ:
                env_backup[key] = os.environ[key]
                del os.environ[key]

        try:
            config = load_config_from_env()
            assert isinstance(config, ContextConfig)
        finally:
            # 恢复环境变量
            os.environ.update(env_backup)


class TestContextConfigEdgeCases:
    """测试边界情况"""

    def test_zero_window_size(self):
        """测试零窗口大小"""
        config = ContextConfig(window_size=0)
        assert config.window_size == 0

    def test_empty_rules_files(self):
        """测试空规则文件列表"""
        config = ContextConfig(rules_files=[])
        assert config.rules_files == []

    def test_empty_protected_types(self):
        """测试空保护类型列表"""
        config = ContextConfig(protected_message_types=[])
        assert config.protected_message_types == []

    def test_large_window_size(self):
        """测试大窗口大小"""
        config = ContextConfig(window_size=2000000)
        assert config.window_size == 2000000

    def test_zero_ratios(self):
        """测试零比例值"""
        config = ContextConfig(soft_trim_ratio=0, hard_clear_ratio=0)
        assert config.soft_trim_ratio == 0
        assert config.hard_clear_ratio == 0

    def test_ratio_equal_to_one(self):
        """测试比例等于 1"""
        config = ContextConfig(compress_threshold=1.0)
        assert config.compress_threshold == 1.0
