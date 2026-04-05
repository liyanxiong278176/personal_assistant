"""LLM 客户端

支持 Function Calling（工具调用）功能。
"""

from .client import LLMClient, ToolCall, ToolResult, ToolCallResult

__all__ = ["LLMClient", "ToolCall", "ToolResult", "ToolCallResult"]
