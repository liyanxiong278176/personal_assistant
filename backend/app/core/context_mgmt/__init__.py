"""Context 上下文管理包

提供上下文管理相关功能：
- Token 估算器
- 上下文压缩器（分块+持久化）
- 上下文配置
- 上下文清理器（软硬修剪）
- 规则重注入器
- 摘要生成器
- 上下文守卫（统一入口）
- 工具结果守卫（实时监控）
- 推理守卫（流式兜底）
"""

from .tokenizer import (
    TokenEstimator,
    estimate_tokens,
    estimate_message_tokens,
)
from .compressor import (
    ContextCompressor,
    CompressionStats,
    ChunkConfig,
    SummaryEntry,
    SummaryPersistence,
    BASE_CHUNK_RATIO,
    MIN_CHUNK_RATIO,
    CHUNK_BUFFER,
)
from .config import (
    ContextConfig,
    load_config_from_env,
    get_default_config,
)
from .cleaner import (
    ContextCleaner,
    CleanStats,
    ContextUsageInfo,
    HEAD_CHARS,
    TAIL_CHARS,
    TRIM_INDICATOR,
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
from .tool_result_guard import (
    ToolResultGuard,
    ToolResultStats,
    BudgetInfo,
    SINGLE_TOOL_RESULT_CONTEXT_SHARE,
    CONTEXT_BUDGET_BUFFER,
    COMPACTED_PLACEHOLDER,
)
from .inference_guard import InferenceGuard, OverlimitStrategy
from .enhancement_config import AgentEnhancementConfig

__all__ = [
    # Token估算
    "TokenEstimator",
    "estimate_tokens",
    "estimate_message_tokens",
    # 压缩器（分块+持久化）
    "ContextCompressor",
    "CompressionStats",
    "ChunkConfig",
    "SummaryEntry",
    "SummaryPersistence",
    "BASE_CHUNK_RATIO",
    "MIN_CHUNK_RATIO",
    "CHUNK_BUFFER",
    # 配置
    "ContextConfig",
    "load_config_from_env",
    "get_default_config",
    # 清理器（软硬修剪）
    "ContextCleaner",
    "CleanStats",
    "ContextUsageInfo",
    "HEAD_CHARS",
    "TAIL_CHARS",
    "TRIM_INDICATOR",
    "CLEARED_PLACEHOLDER",
    "CleanMode",
    # 规则重注入
    "RuleReinjector",
    # 摘要
    "LLMSummaryProvider",
    "create_summary_provider",
    "DEFAULT_SUMMARY_PROMPT",
    # 守卫
    "ContextGuard",
    "AgentEnhancementConfig",
    # 工具结果守卫（实时监控）
    "ToolResultGuard",
    "ToolResultStats",
    "BudgetInfo",
    "SINGLE_TOOL_RESULT_CONTEXT_SHARE",
    "CONTEXT_BUDGET_BUFFER",
    "COMPACTED_PLACEHOLDER",
    # 推理守卫（流式兜底）
    "InferenceGuard",
    "OverlimitStrategy",
]
