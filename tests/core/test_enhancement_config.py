import os
import pytest
from app.core.context.enhancement_config import AgentEnhancementConfig


def test_default_config():
    """测试默认配置"""
    config = AgentEnhancementConfig()
    assert config.enable_tool_loop is False  # 默认关闭
    assert config.max_tool_iterations == 5
    assert config.enable_inference_guard is True  # 默认开启
    assert config.max_tokens_per_response == 4000
    assert config.enable_preference_extraction is True


def test_config_from_env(monkeypatch):
    """测试从环境变量加载"""
    monkeypatch.setenv("ENABLE_TOOL_LOOP", "true")
    monkeypatch.setenv("MAX_TOOL_ITERATIONS", "10")
    config = AgentEnhancementConfig.load()
    assert config.enable_tool_loop is True
    assert config.max_tool_iterations == 10


def test_config_from_dict():
    """测试从字典加载"""
    config = AgentEnhancementConfig.load_from_dict({
        "enable_tool_loop": True,
        "max_tool_iterations": 3
    })
    assert config.enable_tool_loop is True
    assert config.max_tool_iterations == 3
    assert config.enable_inference_guard is True  # 未指定的使用默认值
