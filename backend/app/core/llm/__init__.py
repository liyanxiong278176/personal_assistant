"""LLM 客户端

支持 Function Calling（工���调用）功能。
"""

from .client import LLMClient, ToolCall

__all__ = ["LLMClient", "ToolCall"]
