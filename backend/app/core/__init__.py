"""Agent Core 包

Agent Core 是整个 Agent 系统的核心基础设施，提供：
- LLM 客户端封装（支持 Function Calling）
- 错误处理和降级策略
- 工具系统
- 提示词构建
- 工具调用执行（先工具后 LLM）
- 记忆管理
- 上下文管理
- Coordinator 和 Worker（多 Agent 协调）
- 槽位提取（意图识别）
"""

from .errors import AgentError, DegradationLevel, DegradationStrategy
from .llm import LLMClient, ToolCall, ToolResult, ToolCallResult
from .tools import Tool, ToolInput, ToolMetadata, ToolRegistry, global_registry
from .prompts import PromptLayer, PromptLayerDef, PromptBuilder, DEFAULT_SYSTEM_PROMPT
from .query_engine import QueryEngine, get_global_engine, set_global_engine
from .context import ContextCompressor, ContextManager, TokenEstimator
from .memory import (
    MemoryHierarchy,
    MemoryHierarchyFactory,
    MemoryItem,
    MemoryLevel,
    MemoryType,
    WorkingMemoryEntry,
)
from .coordinator import (
    Coordinator,
    Worker,
    WorkerStatus,
    WorkerResult,
    create_worker,
)
from .intent import SlotExtractor, SlotResult, DateRange
from .session import (
    SessionInitializer,
    SessionState,
    ErrorCategory,
    RecoveryStrategy,
    ErrorClassifier,
    RetryManager,
    RetryPolicy,
    FallbackHandler,
    FallbackResponse,
)

__all__ = [
    "AgentError",
    "DegradationLevel",
    "DegradationStrategy",
    "LLMClient",
    "ToolCall",
    "ToolResult",
    "ToolCallResult",
    "Tool",
    "ToolInput",
    "ToolMetadata",
    "ToolRegistry",
    "global_registry",
    "PromptLayer",
    "PromptLayerDef",
    "PromptBuilder",
    "DEFAULT_SYSTEM_PROMPT",
    "QueryEngine",
    "get_global_engine",
    "set_global_engine",
    "ContextCompressor",
    "ContextManager",
    "TokenEstimator",
    "MemoryHierarchy",
    "MemoryHierarchyFactory",
    "MemoryItem",
    "MemoryLevel",
    "MemoryType",
    "WorkingMemoryEntry",
    "Coordinator",
    "Worker",
    "WorkerStatus",
    "WorkerResult",
    "create_worker",
    "SlotExtractor",
    "SlotResult",
    "DateRange",
    # session
    "SessionInitializer",
    "SessionState",
    "ErrorCategory",
    "RecoveryStrategy",
    "ErrorClassifier",
    "RetryManager",
    "RetryPolicy",
    "FallbackHandler",
    "FallbackResponse",
]
