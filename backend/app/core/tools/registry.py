"""工具注册表"""

import logging
from typing import Dict, List, Optional
from .base import Tool, ToolMetadata

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表

    管理所有可用工具，提供注册、查找、列出功能。
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具

        Args:
            tool: 工具实例

        Raises:
            ValueError: 工具名称已存在
        """
        name = tool.name
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")

        self._tools[name] = tool
        logger.info(f"[ToolRegistry] Registered tool: {name}")

    def get(self, name: str) -> Optional[Tool]:
        """获取工具

        Args:
            name: 工具名称

        Returns:
            工具实例，不存在返回 None
        """
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        """列出所有工具

        Returns:
            工具列表
        """
        return list(self._tools.values())

    def get_descriptions(self) -> str:
        """获取 AI 可用的工具描述

        Returns:
            格式化的工具描述字符串
        """
        descriptions = []
        for tool in self._tools.values():
            meta = tool.metadata
            desc = f"- {meta.name}: {meta.description}"
            if meta.is_readonly:
                desc += " (只读)"
            descriptions.append(desc)
        return "\n".join(descriptions)

    def get_parallel_safe_tools(self) -> List[Tool]:
        """获取可并行的工具

        Returns:
            可并行执行的工具列表
        """
        return [t for t in self._tools.values() if t.metadata.is_concurrency_safe]

    def get_readonly_tools(self) -> List[Tool]:
        """获取只读工具

        Returns:
            只读工具列表
        """
        return [t for t in self._tools.values() if t.metadata.is_readonly]


# 全局工具注册表实例
global_registry = ToolRegistry()
