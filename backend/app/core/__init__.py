"""Agent Core 包

Agent Core 是整个 Agent 系统的核心基础设施，提供：
- LLM 客户端封装
- 错误处理和降级策略
- 工具系统
- 记忆管理
- 上下文管理
"""

from .errors import AgentError, DegradationLevel, DegradationStrategy
from .llm import LLMClient

__all__ = [
    "AgentError",
    "DegradationLevel",
    "DegradationStrategy",
    "LLMClient",
]
