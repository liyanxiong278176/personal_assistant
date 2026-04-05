"""工具系统包

提供统一的工具管理基础设施，包括：
- Tool: 工具基类，所有工具必须继承此类
- ToolRegistry: 工具注册表，管理所有可用工具
- ToolExecutor: 工具执行器，支持并行执行和错误处理
- global_registry: 全局工具注册表实例
- builtin: 内置工具（天气、POI、路线）
"""

from .base import Tool, ToolInput, ToolMetadata
from .registry import ToolRegistry, global_registry
from .executor import ToolExecutor, ToolExecutionError

# 导入内置工具（会自动注册）
import app.core.tools.builtin  # noqa: F401

__all__ = [
    "Tool",
    "ToolInput",
    "ToolMetadata",
    "ToolRegistry",
    "ToolExecutor",
    "ToolExecutionError",
    "global_registry",
]
