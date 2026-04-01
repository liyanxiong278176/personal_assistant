"""工具执行器

支持并行工具执行和错误处理。
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
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

    async def execute_parallel(self, tool_calls: List[Dict]) -> Dict[str, Any]:
        """并行执行工具调用

        根据工具的 is_concurrency_safe 属性，分离可并行和串行工具：
        - 并行执行所有 is_concurrency_safe=True 的工具
        - 串行执行所有 is_concurrency_safe=False 的工具

        Args:
            tool_calls: 工具调用列表，每个元素为字典，包含:
                - "tool": 工具名称
                - "args": 工具参数字典 (可选)

        Returns:
            工具名称到执行结果的映射，格式为:
            {
                "tool_name": result,  # 成功执行的工具
                "tool_name": {"error": error_message, "original_error": exception},  # 失败的工具
            }

        Example:
            >>> executor = ToolExecutor(registry)
            >>> calls = [
            ...     {"tool": "search_weather", "args": {"city": "北京"}},
            ...     {"tool": "search_poi", "args": {"keyword": "景点"}},
            ... ]
            >>> results = await executor.execute_parallel(calls)
        """
        if not tool_calls:
            return {}

        # 分离可并行和串行工具
        parallel_calls: List[Dict] = []
        sequential_calls: List[Dict] = []

        for call in tool_calls:
            tool_name = call.get("tool")
            if not tool_name:
                logger.warning("[ToolExecutor] Skipping call without tool name")
                continue

            tool = self._registry.get(tool_name)
            if tool is None:
                logger.warning(f"[ToolExecutor] Tool '{tool_name}' not found, will error during execution")
                # 仍然尝试执行，让 execute 方法处理错误

            if tool and tool.metadata.is_concurrency_safe:
                parallel_calls.append(call)
            else:
                sequential_calls.append(call)

        logger.info(
            f"[ToolExecutor] Parallel execution: {len(parallel_calls)} parallel, "
            f"{len(sequential_calls)} sequential"
        )

        results: Dict[str, Any] = {}

        # 并行执行安全工具
        if parallel_calls:
            parallel_tasks = [
                self._safe_execute_with_result(call) for call in parallel_calls
            ]
            parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

            for result in parallel_results:
                if isinstance(result, Exception):
                    logger.error(f"[ToolExecutor] Parallel execution error: {result}")
                elif result:
                    # result is {tool_name: result_value}
                    results.update(result)

        # 串行执行不安全工具
        for call in sequential_calls:
            result = await self._safe_execute_with_result(call)
            if result:
                # result is {tool_name: result_value}
                results.update(result)

        return results

    async def execute_sequence(self, tool_calls: List[Dict]) -> List[Any]:
        """按顺序串行执行工具调用

        Args:
            tool_calls: 工具调用列表，每个元素为字典，包含:
                - "tool": 工具名称
                - "args": 工具参数字典 (可选)

        Returns:
            执行结果列表，按调用顺序排列

        Example:
            >>> executor = ToolExecutor(registry)
            >>> calls = [
            ...     {"tool": "search_weather", "args": {"city": "北京"}},
            ...     {"tool": "search_poi", "args": {"keyword": "景点"}},
            ... ]
            >>> results = await executor.execute_sequence(calls)
        """
        results: List[Any] = []

        for call in tool_calls:
            tool_name = call.get("tool")
            if not tool_name:
                logger.warning("[ToolExecutor] Skipping call without tool name")
                continue

            args = call.get("args", {})

            try:
                result = await self.execute(tool_name, **args)
                results.append(result)
            except ToolExecutionError as e:
                logger.error(f"[ToolExecutor] Sequential execution failed for {tool_name}: {e}")
                results.append({"error": str(e), "tool": tool_name})

        return results

    async def _safe_execute_with_result(self, call: Dict) -> Optional[Dict[str, Any]]:
        """安全执行工具并返回格式化结果

        Args:
            call: 工具调用字典

        Returns:
            格式化的结果字典: {"tool_name": result} 或 {"tool_name": {"error": ...}}
        """
        tool_name = call.get("tool", "")
        args = call.get("args", {})

        try:
            result = await self.execute(tool_name, **args)
            return {tool_name: result}
        except (ToolExecutionError, ValueError) as e:
            return {
                tool_name: {
                    "error": str(e),
                    "original_error": e.original_error if isinstance(e, ToolExecutionError) else e
                }
            }
        except Exception as e:
            logger.exception(f"[ToolExecutor] Unexpected error executing {tool_name}")
            return {
                tool_name: {
                    "error": f"Unexpected error: {str(e)}",
                    "original_error": e
                }
            }

    async def batch_execute(
        self,
        tool_calls: List[Dict],
        parallel_safe: bool = True
    ) -> Dict[str, Any]:
        """批量执行工具调用

        Args:
            tool_calls: 工具调用列表
            parallel_safe: 是否使用并行执行（默认 True）

        Returns:
            工具名称到执行结果的映射
        """
        if parallel_safe:
            return await self.execute_parallel(tool_calls)
        else:
            # 使用串行执行 - 逐个调用 _safe_execute_with_result
            results: Dict[str, Any] = {}
            for call in tool_calls:
                result = await self._safe_execute_with_result(call)
                if result:
                    results.update(result)
            return results
