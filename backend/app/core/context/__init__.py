"""Context 上下文管理包

提供上下文管理相关功能：
- Token 估算器
- 上下文压缩器
- 上下文管理器
- 上下文配置
- 上下文清理器
- 规则重注入器
- 摘要生成器
- 上下文守卫
"""

from .tokenizer import (
    TokenEstimator,
    estimate_tokens,
    estimate_message_tokens,
)
from .compressor import ContextCompressor
from .manager import ContextManager
from .config import (
    ContextConfig,
    load_config_from_env,
    get_default_config,
)
from .cleaner import (
    ContextCleaner,
    TRIM_KEEP_CHARS,
    CLEARED_PLACEHOLDER,
    CleanMode,
)
from .reinjector import RuleReinjector
from .summary import (
    LLMSummaryProvider,
    create_summary_provider,
    DEFAULT_SUMMARY_PROMPT,
)
from .guard import ContextGuard
from .enhancement_config import AgentEnhancementConfig
from .inference_guard import InferenceGuard, OverlimitStrategy

__all__ = [
    "TokenEstimator",
    "estimate_tokens",
    "estimate_message_tokens",
    "ContextCompressor",
    "ContextManager",
    "ContextConfig",
    "load_config_from_env",
    "get_default_config",
    "ContextCleaner",
    "TRIM_KEEP_CHARS",
    "CLEARED_PLACEHOLDER",
    "CleanMode",
    "RuleReinjector",
    "LLMSummaryProvider",
    "create_summary_provider",
    "DEFAULT_SUMMARY_PROMPT",
    "ContextGuard",
    "AgentEnhancementConfig",
    "InferenceGuard",
    "OverlimitStrategy",
]
