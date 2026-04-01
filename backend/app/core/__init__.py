"""Agent Core 包

Agent Core 是整个 Agent 系统的核心基础设施，提供：
- LLM 客户端封装
- 错误处理和降级策略
- 工具系统
- 提示词构建
- 意图路由（Slash 命令、Skill 触发）
- 记忆管理
- 上下文管理
- Coordinator 和 Worker（多 Agent 协调）
"""

from .errors import AgentError, DegradationLevel, DegradationStrategy
from .llm import LLMClient
from .tools import Tool, ToolInput, ToolMetadata, ToolRegistry, global_registry
from .prompts import PromptLayer, PromptLayerDef, PromptBuilder, DEFAULT_SYSTEM_PROMPT
from .query_engine import QueryEngine, get_global_engine, set_global_engine
from .intent import CommandResult, SlashCommand, SlashCommandRegistry, get_slash_registry
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

__all__ = [
    "AgentError",
    "DegradationLevel",
    "DegradationStrategy",
    "LLMClient",
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
    "CommandResult",
    "SlashCommand",
    "SlashCommandRegistry",
    "get_slash_registry",
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
]
