"""AgentEnhancementConfig - 增强功能配置

定义工具循环、推理守卫、偏好提取等功能的配置参数。
所有新功能默认关闭（except inference_guard），确保向后兼容。
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentEnhancementConfig:
    """Agent功能增强配置

    所有新功能默认关闭（except inference_guard），确保向后兼容。
    通过环境变量或字典加载配置。
    """

    # 工具循环配置
    enable_tool_loop: bool = field(
        default_factory=lambda: os.getenv("ENABLE_TOOL_LOOP", "false").lower() == "true"
    )
    max_tool_iterations: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOOL_ITERATIONS", "5"))
    )
    tool_loop_token_limit: int = field(
        default_factory=lambda: int(os.getenv("TOOL_LOOP_TOKEN_LIMIT", "16000"))
    )

    # 推理守卫配置
    enable_inference_guard: bool = field(
        default_factory=lambda: os.getenv("ENABLE_INFERENCE_GUARD", "true").lower() == "true"
    )
    max_tokens_per_response: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOKENS_PER_RESPONSE", "4000"))
    )
    max_total_token_budget: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOTAL_TOKEN_BUDGET", "16000"))
    )
    inference_warning_threshold: float = field(
        default_factory=lambda: float(os.getenv("INFERENCE_WARNING_THRESHOLD", "0.8"))
    )
    overlimit_strategy: str = field(
        default_factory=lambda: os.getenv("OVERLIMIT_STRATEGY", "truncate")
    )

    # 偏好提取配置
    enable_preference_extraction: bool = field(
        default_factory=lambda: os.getenv("ENABLE_PREFERENCE_EXTRACTION", "true").lower() == "true"
    )
    preference_confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("PREFERENCE_CONFIDENCE_THRESHOLD", "0.7"))
    )

    @classmethod
    def load(cls) -> "AgentEnhancementConfig":
        """从环境变量加载配置"""
        return cls()

    @classmethod
    def load_from_dict(cls, config_dict: dict) -> "AgentEnhancementConfig":
        """从字典加载配置（用于测试）"""
        valid_fields = {
            k: v for k, v in config_dict.items()
            if k in cls.__dataclass_fields__
        }
        return cls(**valid_fields)


__all__ = ["AgentEnhancementConfig"]
