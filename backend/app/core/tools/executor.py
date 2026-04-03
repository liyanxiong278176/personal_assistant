"""工具执行器

支持并行工具执行和错误处理。
"""

import asyncio
import logging
from typing import Any, Dict

from .registry import ToolRegistry
from .base import Tool

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """工具执行错误"""

    def __init__(self, tool_name: str, original_error: Exception):
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' execution failed: {original_error}")


class ToolExecutor:
    """工具执行器

    负责执行工具调用，支持并行执行和错误处理。
    """

    def __init__(self, registry: ToolRegistry):
        """初始化工具执行器

        Args:
            registry: 工具注册表
        """
        self._registry = registry
        logger.info("[ToolExecutor] Initialized")

    async def execute(self, tool_name: str, **kwargs) -> Any:
        """执行单个工具

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            工具执行结果

        Raises:
            ToolExecutionError: 工具执行失败
            ValueError: 工具不存在
        """
        tool = self._registry.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool '{tool_name}' not found in registry")

        try:
            logger.debug(f"[ToolExecutor] Executing tool: {tool_name} with kwargs: {kwargs}")
            result = await tool.execute(**kwargs)
            logger.debug(f"[ToolExecutor] Tool {tool_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"[ToolExecutor] Tool {tool_name} failed: {e}")
            raise ToolExecutionError(tool_name, e) from e

    async def execute_parallel(self, calls: list["ToolCall"]) -> Dict[str, Any]:
        """并行执行工具调用

        Args:
            calls: 工具调用列表，ToolCall 对象列表

        Returns:
            工具名称到执行结果的映射，格式为:
            {
                "tool_name": result,  # 成功执行的工具
                "tool_name": {"error": error_message, "original_error": exception},  # 失败的工具
            }

        Example:
            >>> executor = ToolExecutor(registry)
            >>> from app.core.llm import ToolCall
            >>> calls = [
            ...     ToolCall(id="1", name="search_weather", arguments={"city": "北京"}),
            ...     ToolCall(id="2", name="search_poi", arguments={"keyword": "景点"}),
            ... ]
            >>> results = await executor.execute_parallel(calls)
        """
        if not calls:
            return {}

        tasks = [self._execute_call(call) for call in calls]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: Dict[str, Any] = {}
        for i, result in enumerate(results_list):
            tool_name = calls[i].name
            if isinstance(result, Exception):
                logger.error(f"[ToolExecutor] Parallel execution error for {tool_name}: {result}")
                original_error = result
                if isinstance(result, ToolExecutionError):
                    original_error = result.original_error
                results[tool_name] = {
                    "error": str(result),
                    "original_error": original_error,
                }
            else:
                results[tool_name] = result

        return results

    async def _execute_call(self, call: "ToolCall") -> Any:
        """执行单个工具调用

        Args:
            call: ToolCall 对象

        Returns:
            工具执行结果
        """
        tool_name = call.name
        try:
            return await self.execute(tool_name, **call.arguments)
        except (ToolExecutionError, ValueError) as e:
            raise e
        except Exception as e:
            logger.exception(f"[ToolExecutor] Unexpected error executing {tool_name}")
            raise ToolExecutionError(tool_name, e) from e
